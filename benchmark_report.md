# Benchmark Report

Numbers below come from `POST /eval/run` (`eval/runner.py`), which scores the
golden Q&A set (`eval/golden_set.py`, 4 questions) by calling the exact same
retrieval and answer-generation path (`api.ask.answer_question`) that
production traffic uses — not a separate simulation of it. Per this project's
rule (`CLAUDE.md`, PERFORMANCE), nothing below is asserted ahead of an actual
measured run.

## Status

**Pending.** `POST /eval/run` requires a funded `ANTHROPIC_API_KEY` (the LLM
call is the only step that costs money — retrieval, embedding, and the
verifier's similarity checks are all local/free). No key has been available
in this environment yet. This report will be filled in with a real run once
one is.

## Environment (fill in at measurement time)

| | |
| --- | --- |
| Date | |
| CPU | |
| RAM | |
| OS | |
| Python version | |
| `LLM_MODEL` | |
| `VERIFIER_THRESHOLD` | |
| `VERIFIER_MAX_FAILED_RATIO` | |
| `RERANK_TOP_K` / `RRF_K` | |

## Results (fill in at measurement time)

| Metric | Value | Meaning |
| --- | --- | --- |
| `question_count` | | Golden questions scored |
| `refused_count` | | How many were refused outright |
| `mean_recall_at_k` | | Fraction of expected chunks retrieved in the top-8, averaged |
| `mrr` | | Mean Reciprocal Rank — rewards rank, not just presence |
| `mean_faithfulness` | | Mean fraction of an answer's claims that passed verification |
| `p95_latency_ms` | | 95th-percentile end-to-end `/ask` latency |

## How to reproduce

```bash
cp .env.example .env   # add a funded ANTHROPIC_API_KEY
make up
make eval-seed
make eval-run
```

`make eval-run` hits `POST /eval/run` and pretty-prints the JSON response —
paste those five fields directly into the Results table above.
