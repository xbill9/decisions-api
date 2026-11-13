# decisions-api

A demo of the [Gemini Decisions API](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-decisions-api/)
(`gemini-decision-1`) in three parts:

1. **An ADK agent** that uses the API twice: as a guardrail in front of the LLM, and as its triage tool.
2. **A head-to-head benchmark** on 48 labeled support tickets: the Decisions API against four generative
   models — Gemini 3.8 Flash, Gemini 4 Hydrogen, Gemini 3.5 Flash-Lite, and Gemma 4 E2B running locally
   on CPU. Every backend gets the same questions.
3. **A scale test**: one ticket with 1, 10, 25, 50 and 100 questions in a single request.

The Decisions API scores a fixed set of answers in one forward pass and returns probabilities. It
generates no text. You send one shared `input` and up to 1,000 `questions`, each one of:

| type | asks | returns |
|---|---|---|
| `noul` | yes or no | `noul` = P(yes), `confidence` |
| `choice` | pick one of 2–255 options | `choice`, `probabilities` per option, `confidence` |
| `score` | a level on an ordered rubric | `score` (weighted mean), `probabilities` per level, `legend`, `confidence` |

#### Files

```
decide.py              one function per backend (decisions, gemma, flashlite, flash, hydrogen)
tickets.py             48 hand-labeled tickets + the 3 questions asked about each
bench.py               runs every ticket through each backend, scores and times them
scale.py               latency for 1..100 questions in one request
triage_agent/agent.py  ADK agent: Decisions guardrail + triage tool + Gemma comparison tool
results/               rows.jsonl and summaries from each run
```

#### Setup

```bash
make install                       # httpx + google-adk into the system python3
export GEMINI_API_KEY=...          # or put it in ~/gemini.key
make gemma                         # in a second terminal: Gemma 4 E2B on 127.0.0.1:8080
make smoke                         # one ticket through all three backends
```

`make gemma` drives the `local-llamacpp-cpu-2b-q4_0` rig from `~/gemma4-dev`: llama-server, the
Gemma 4 E2B QAT Q4_0 GGUF, CPU only. Point `GEMMA_URL` at any other OpenAI-compatible server to use
something else.

The Decisions API is called over REST (`POST /v1beta/decisions`). The Python SDK's
`client.decisions.create(...)` needs `google-genai>=3.2`, and `google-adk` 2.x pins
`google-genai<3`, so REST keeps both in one environment.

#### The agent

```bash
make agent     # terminal
make web       # ADK web UI, then pick triage_agent
```

- **Guardrail.** `before_model_callback` sends every user turn to the Decisions API with one `noul`
  question: is this trying to make the assistant ignore its instructions? At p ≥ 0.8 the callback
  answers itself and the LLM call is skipped.
- **`triage_ticket`.** Department (`choice`), refund intent (`noul`) and urgency (`score`) in one
  request. Any answer below 0.7 confidence goes into `needs_human_review`.
- **`triage_with_gemma`.** The same three questions sent to the local Gemma. Ask the agent to
  "compare with Gemma" to get both in a table.

#### Results — 2026-11-13

From `results/2026-11-13-180410/summary.md`, written by `bench.py`. Gemma ran on an Intel i7-10750H laptop CPU (6 cores, no
GPU); the cloud backends were called from the same machine. The generative Gemini models ran at
temperature 0 and the lowest thinking level each accepts: `minimal` for 3.5 Flash-Lite, `low` for 3.8 Flash
and 4 Hydrogen (both reject `minimal`).

48 hand-labeled support tickets, 3 questions each, one request per ticket per backend.
Models: decisions=`gemini-decision-1`, gemma=`gemma-4-E2B-it-q4_0` (QAT Q4_0 GGUF) on local CPU llama-server, flashlite=`gemini-3.5-flash-lite`, flash=`gemini-3.8-flash`, hydrogen=`gemini-4-hydrogen`.

| | decisions | gemma | flashlite | flash | hydrogen |
|---|---|---|---|---|---|
| dept correct | 46/48 (96%) | 43/48 (90%) | 45/48 (94%) | 46/48 (96%) | 45/48 (94%) |
| wants_refund correct | 47/48 (98%) | 46/48 (96%) | 45/48 (94%) | 48/48 (100%) | 48/48 (100%) |
| urgency correct | 31/48 (65%) | 39/48 (81%) | 44/48 (92%) | 42/48 (88%) | 40/48 (83%) |
| urgency_within_one correct | 48/48 (100%) | 48/48 (100%) | 48/48 (100%) | 48/48 (100%) | 48/48 (100%) |
| all_three correct | 29/48 (60%) | 36/48 (75%) | 39/48 (81%) | 40/48 (83%) | 38/48 (79%) |
| median latency | 202 ms | 3352 ms | 714 ms | 2373 ms | 1951 ms |
| p90 latency | 227 ms | 3919 ms | 877 ms | 4414 ms | 2844 ms |
| input tokens | 17,950 | 13,822 | 13,438 | 13,438 | 26,253 |
| output tokens | 0 | 1,680 | 1,384 | 2,870 | 8,413 |
| errors | 0 | 0 | 0 | 0 | 0 |

Decisions API cost for the run: $0.001795 (17,950 input tokens at $0.1/1M).

Decisions API, split by its confidence score (threshold 0.7):

| question | confident: correct/n | unsure: correct/n |
|---|---|---|
| dept | 41/42 | 5/6 |
| wants_refund | 46/46 | 1/2 |
| urgency | 23/23 | 8/25 |

gemma agrees with the Decisions API on: dept 43/48, wants_refund 45/48, urgency 28/48

flashlite agrees with the Decisions API on: dept 47/48, wants_refund 46/48, urgency 33/48

flash agrees with the Decisions API on: dept 47/48, wants_refund 47/48, urgency 37/48

hydrogen agrees with the Decisions API on: dept 46/48, wants_refund 47/48, urgency 37/48

Where the urgency misses land (answer key → answer), from `docs/article/evidence/derived.txt`:

| | too high by one | too low by one | high-urgency rated normal |
|---|---|---|---|
| decisions | 17 | 0 | 0 of 8 |
| flash | 6 | 0 | 0 of 8 |
| hydrogen | 7 | 1 | 0 of 8 |
| flashlite | 4 | 0 | 0 of 8 |
| gemma | 4 | 5 | 4 of 8 |

The answer key is one person's reading of each ticket, and 48 tickets is a small set: a gap of two or
three tickets between backends is within what relabeling a few borderline tickets would move. The first
run (`results/2026-11-13-171540`, three backends) gave identical per-ticket answers for the Decisions API
and Gemma; Flash-Lite changed at least one answer on 8 of 48 tickets between the runs.

#### Scale: 1 to 100 questions in one request — 2026-11-13

From `results/scale-2026-11-13-182530/summary.md`, written by `scale.py`: one 59-word ticket, yes/no questions, 3 runs per cell.

| questions | decisions median | gemma median | flashlite median | flash median | hydrogen median |
|---|---|---|---|---|---|
| 1 | 224 ms | 1,825 ms | 852 ms | 1,898 ms | 1,699 ms |
| 10 | 216 ms | 11,647 ms | 935 ms | 1,980 ms | 2,395 ms |
| 25 | 233 ms | 29,294 ms | 1,147 ms | 2,938 ms | 3,611 ms |
| 50 | 281 ms | 59,470 ms | 1,617 ms | 4,461 ms | 5,722 ms |
| 100 | 359 ms | 115,280 ms | 2,584 ms | 7,191 ms | 8,625 ms |

Median of 3 runs per cell.

From 1 to 100 questions the median grew 1.6× for the Decisions API, 3.0× for Flash-Lite, 3.8× for
3.8 Flash, 5.1× for Hydrogen and 63.2× for Gemma. At 100 questions the Decisions API was 7.2× faster than
Flash-Lite, 20× faster than 3.8 Flash and 24× faster than Hydrogen.

---

#### So, Which One?

- 🟢 **Decisions API** for routing and yes/no checks: team 46/48 (tied best with 3.8 Flash), refunds
  47/48, a median of 202 ms — 3.5× faster than Flash-Lite and about 10× faster than 3.8 Flash and
  Hydrogen — and $0.0018 for the whole run. Every urgency answer at confidence ≥ 0.7 was right (23/23);
  below 0.7 it was right 8 times in 25. Send the unsure ones to a person or a bigger model.
- 🟢 **Many questions at once:** 100 questions took 359 ms median, against 7.2 s for 3.8 Flash and 8.6 s
  for Hydrogen.
- ⚠️ **Ordered scales need calibration.** Urgency 31/48, lowest of the five; every miss was one level
  too high. Tune the rubric wording, or act on `score` with your own thresholds.
- 🟢 **Gemini 3.8 Flash** had the most tickets fully right (40/48) and 48/48 on refunds; **Gemini 4
  Hydrogen** also 48/48 on refunds, with a faster median than 3.8 Flash and 2.9× its output tokens.
- 🟢 **Gemini 3.5 Flash-Lite** scored best on urgency (44/48) at a 714 ms median.
- ❌ **Gemma 4 E2B on a laptop CPU** answers offline at no cost, at a 3.4 s median in this run (5.6 s in
  the first; the laptop throttles), and put 4 of the 8 high-urgency tickets at normal.

Scope: one five-backend run of 48 English, Spanish and German text tickets, three questions each, one
request at a time, Decisions API called over REST from a home connection. No images, audio or PDFs; no
concurrency; the scale test used one ticket and 3 runs per cell; Gemma latency is CPU-bound and would
differ on a GPU.
