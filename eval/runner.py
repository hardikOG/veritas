"""Runs the golden set through retrieval + the full answer pipeline, scoring both."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.ask import answer_question
from core.config import Settings
from core.constants import EVAL_RECALL_K
from embedding.base import Embedder
from eval.metrics import EvalReport, faithfulness_ratio, p95, recall_at_k, reciprocal_rank
from llm.base import LLMClient
from models import EvalGolden
from retrieval.hybrid import hybrid_search


def run_eval(
    db: Session, embedder: Embedder, llm_client: LLMClient, settings: Settings
) -> EvalReport:
    """Score the current golden set (eval_golden) on retrieval and answer quality.

    Purpose: Phase 4's harness — POST /eval/run's entire implementation. Runs each
        golden question through the same retrieval (retrieval/hybrid.py) and
        answer-generation (api.ask.answer_question) paths production traffic uses,
        so the reported numbers reflect the real system, not a simulation of it.
    Inputs: db, embedder, llm_client, settings — same dependencies
        api.ask.answer_question takes.
    Outputs: an EvalReport aggregating Recall@8, MRR, mean faithfulness (verifier
        confidence), and p95 latency across every golden question.
    Complexity: O(n) golden questions, each doing one retrieval call plus one full
        answer_question() call (itself one retrieval + one LLM call + one batched
        embedding call).
    Failure cases: raises ValueError if eval_golden is empty — an eval report over
        zero questions would silently read as "perfect score," which is worse than
        failing loudly; the caller (api/eval.py) turns this into a 4xx pointing at
        `python -m eval.seed`.
    """
    golden_rows = db.execute(select(EvalGolden)).scalars().all()
    if not golden_rows:
        raise ValueError("eval_golden is empty — run `python -m eval.seed` first")

    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    confidences: list[float] = []
    latencies: list[int] = []
    refused_count = 0

    for row in golden_rows:
        expected_chunk_ids = [str(chunk_id) for chunk_id in row.expected_chunk_ids]

        retrieved = hybrid_search(
            db, embedder, row.question, top_k=settings.rerank_top_k, rrf_k=settings.rrf_k
        )
        retrieved_chunk_ids = [result.chunk_id for result in retrieved]
        recalls.append(recall_at_k(retrieved_chunk_ids, expected_chunk_ids, k=EVAL_RECALL_K))
        reciprocal_ranks.append(reciprocal_rank(retrieved_chunk_ids, expected_chunk_ids))

        answer_result = answer_question(db, embedder, llm_client, settings, row.question)
        confidences.append(answer_result["confidence"])
        latencies.append(answer_result["latency_ms"])
        if answer_result["refused"]:
            refused_count += 1

    return EvalReport(
        question_count=len(golden_rows),
        refused_count=refused_count,
        mean_recall_at_k=sum(recalls) / len(recalls),
        mrr=sum(reciprocal_ranks) / len(reciprocal_ranks),
        mean_faithfulness=faithfulness_ratio(confidences),
        p95_latency_ms=p95(latencies),
    )
