# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Demo of the Gemini Decisions API (`gemini-decision-1`): an ADK agent (`triage_agent/`), a 48-ticket
benchmark against Gemma 4 E2B and Gemini Flash-Lite (`bench.py`), and a 1→100-question latency test
(`scale.py`). `make help` lists the commands.

## Decisions API

- Call it over REST (`POST /v1beta/decisions`, header `x-goog-api-key`), as `decide.decisions()` does.
  Do **not** switch to `client.decisions.create()` and do **not** upgrade `google-genai`: the SDK method
  needs `google-genai>=3.2`, and `google-adk` 2.x pins `google-genai<3`, so upgrading breaks the agent.
- Key: `GEMINI_API_KEY`, else `GOOGLE_API_KEY`, else `~/gemini.key` (see `decide.api_key()`).
- Answer shapes: `noul` is P(yes) and is clamped to 0.01–0.99; `choice` returns `choice` (there is no
  "winner" field) plus `probabilities`; `score` is a probability-weighted mean, not a level. Compare
  backends through `decide.pick()`, which takes the most likely level for `score`.
- Question keys must match `[A-Za-z0-9_-]{1,64}`; 1–1,000 questions; 2–255 choice options.

## Gemma backend

- `decide.gemma()` expects llama-server at `GEMMA_URL` (default `http://127.0.0.1:8080`). Start it with
  `make gemma` (drives `~/gemma4-dev/local-llamacpp-cpu-2b-q4_0`) and check `curl 127.0.0.1:8080/health`
  before running anything that uses Gemma.
- It is CPU-only on a laptop that throttles: never run `bench.py` and `scale.py` at the same time, or
  anything else heavy while they run — Gemma latency will be wrong.

## Results and numbers

- Every number in README.md comes from a `results/<run>/summary.md|json` file or is computed by a
  script from `rows.jsonl`. Never hand-compute or type in a figure; never edit files under `results/`.
- The answer key in `tickets.py` is hand-written. Changing a label or a question invalidates earlier
  runs — re-run `make bench` and update the README from the new summary. `wants_refund` is True only
  for an explicit ask for money back or a chargeback threat.
- To re-run and publish results, use `/refresh-results`.

## Code

- Lint: `ruff check .` (config in `ruff.toml`). Do not run `ruff format` across the repo.
- Test: `make test` — offline only (httpx.MockTransport), no key, network or Gemma needed. Keep new tests offline;
  `test_tickets_are_unique_and_counted` pins the ticket count the README quotes.
