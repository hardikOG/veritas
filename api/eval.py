"""POST /eval/run — scores the golden set (eval_golden) and returns metrics."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.ask import get_llm_client_dependency
from api.deps import get_db
from core.config import get_settings
from embedding.sentence_transformer import get_embedder
from eval.runner import run_eval
from llm.base import LLMClient

router = APIRouter()
settings = get_settings()


@router.post("/eval/run")
async def eval_run(
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client_dependency),
) -> dict[str, float | int]:
    """Run the eval harness over eval_golden, returning aggregate metrics.

    Purpose: Phase 4's API surface — the resume-facing numbers (Recall@8, MRR,
        faithfulness ratio, p95 latency) come from here, measured against the
        golden set, never asserted ahead of measurement.
    Inputs: db, llm_client — injected (llm_client shares POST /ask's override
        dependency, so tests can substitute FakeLLMClient here too).
    Outputs: EvalReport as a flat JSON object.
    Complexity: see eval.runner.run_eval.
    Failure cases: HTTPException(409) if eval_golden is empty — the caller must run
        `python -m eval.seed` (worker image) first; see eval/seed.py's module
        docstring for why seeding is a worker-side, not api-side, operation.
    """
    embedder = get_embedder(settings)
    try:
        report = run_eval(db, embedder, llm_client, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return asdict(report)
