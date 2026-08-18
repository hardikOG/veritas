# Benchmark Report

Numbers below come from `POST /eval/run` (`eval/runner.py`), which scores the
golden Q&A set (`eval/golden_set.py`, 4 questions) by calling the exact same
retrieval and answer-generation path (`api.ask.answer_question`) that
production traffic uses — not a separate simulation of it. Per this project's
rule (`CLAUDE.md`, PERFORMANCE), nothing below is asserted ahead of an actual
measured run.

## Status: provisional

**Measured with Gemini 3.6 Flash (free tier), not the documented production
backend.** No funded `ANTHROPIC_API_KEY` was available (the LLM call is the
only step in this pipeline that costs money — retrieval, embedding, and the
verifier's similarity checks are all local/free). `CLAUDE.md` fixes Veritas's
LLM backend to Anthropic (`claude-sonnet-4-6`) specifically; these numbers are
real and honestly measured, but against a temporary stand-in, not the system
as actually documented/deployed. **To be re-verified against Claude once
funded** — see `MANUAL_TODO.md`.

## Environment

| | |
| --- | --- |
| Date | 2026-08-18 |
| CPU | 13th Gen Intel Core i5-13420H |
| RAM | 15.7 GB |
| OS | Windows 11 Home Single Language |
| Python version | 3.13.5 |
| LLM used this run | `gemini-3.6-flash` (temporary — see Status above) |
| `VERIFIER_THRESHOLD` | 0.62 |
| `VERIFIER_MAX_FAILED_RATIO` | 0.4 |
| `RERANK_TOP_K` / `RRF_K` | 8 / 60 |

## Results

| Metric | Value | Meaning |
| --- | --- | --- |
| `question_count` | 4 | Golden questions scored |
| `refused_count` | 3 | How many were refused outright |
| `mean_recall_at_k` | 1.0000 | Fraction of expected chunks retrieved in the top-8, averaged |
| `mrr` | 1.0000 | Mean Reciprocal Rank — rewards rank, not just presence |
| `mean_faithfulness` | 0.6250 | Mean fraction of an answer's claims that passed verification |
| `p95_latency_ms` | not meaningfully measured this run — see note below | 95th-percentile end-to-end `/ask` latency |

**Retrieval is perfect** (Recall@8 and MRR both 1.0) — every golden question's
expected chunk was retrieved and ranked first. **Faithfulness is lower than
retrieval**, and 3 of 4 answers were refused. This is a real, reproducible
finding, not noise: per-claim inspection showed the *first* sentence of each
multi-sentence answer scoring well (0.70-0.80 cosine similarity against its
cited chunk) while later sentences — equally accurate paraphrases of the same
chunk — scored notably lower (0.33-0.49), several points under the 0.62
threshold. The working hypothesis (see `docs/private/ARCHITECTURE_LEDGER.md`
if you have access to that file) is that comparing one claim sentence against
a whole multi-sentence chunk's embedding structurally disadvantages claims
about content later in the chunk, not that the claims are actually
unsupported. Untested with the real production LLM yet.

**`p95_latency_ms` is not reported** — this run's script added its own
retry-with-backoff around each Gemini call to survive repeated `503
UNAVAILABLE` ("high demand") responses from the free tier, and those waits are
included in `answer_question()`'s measured latency. Publishing that number
would misrepresent it as reflecting Veritas's own processing time, when most
of it was this run waiting out a free-tier rate limit that a paid Anthropic
key won't have. Latency will be measured for real once re-run against Claude.

## How to reproduce (against the real production backend)

```bash
cp .env.example .env   # add a funded ANTHROPIC_API_KEY
make up
make eval-seed
make eval-run
```

`make eval-run` hits `POST /eval/run` and pretty-prints the JSON response —
paste those five fields directly into the Results table above, replacing this
provisional Gemini-measured run.
