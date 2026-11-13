# decisions-api

A demo of the [Gemini Decisions API](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-decisions-api/)
(`gemini-decision-1`) in three parts:

1. **An ADK agent** that uses the API twice: as a guardrail in front of the LLM, and as its triage tool.
2. **A head-to-head benchmark** on 48 labeled support tickets: Decisions API vs Gemma 4 E2B running
   locally on CPU vs Gemini 3.5 Flash-Lite. Every backend gets the same questions.
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
decide.py              one function per backend, same inputs and answer shape
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

From `results/2026-11-13-171540/summary.md`, written by `bench.py`. Gemma ran on an Intel i7-10750H laptop
CPU (6 cores, no GPU); the two cloud backends were called from the same machine.

48 hand-labeled support tickets, 3 questions each, one request per ticket per backend.
Models: decisions=`gemini-decision-1`, gemma=`gemma-4-E2B-it-q4_0` (QAT Q4_0 GGUF) on local CPU llama-server, flashlite=`gemini-3.5-flash-lite`.

| | decisions | gemma | flashlite |
|---|---|---|---|
| dept correct | 46/48 (96%) | 43/48 (90%) | 45/48 (94%) |
| wants_refund correct | 47/48 (98%) | 46/48 (96%) | 45/48 (94%) |
| urgency correct | 31/48 (65%) | 39/48 (81%) | 42/48 (88%) |
| urgency_within_one correct | 48/48 (100%) | 48/48 (100%) | 48/48 (100%) |
| all_three correct | 29/48 (60%) | 36/48 (75%) | 37/48 (77%) |
| median latency | 208 ms | 5628 ms | 734 ms |
| p90 latency | 272 ms | 6127 ms | 843 ms |
| input tokens | 17,950 | 13,822 | 13,438 |
| output tokens | 0 | 1,680 | 1,392 |
| errors | 0 | 0 | 0 |

Decisions API cost for the run: $0.001795 (17,950 input tokens at $0.1/1M).

Decisions API, split by its confidence score (threshold 0.7):

| question | confident: correct/n | unsure: correct/n |
|---|---|---|
| dept | 41/42 | 5/6 |
| wants_refund | 46/46 | 1/2 |
| urgency | 23/23 | 8/25 |

gemma agrees with the Decisions API on: dept 43/48, wants_refund 45/48, urgency 28/48

flashlite agrees with the Decisions API on: dept 45/48, wants_refund 46/48, urgency 37/48

Where the urgency misses land (answer key → answer, counted from `rows.jsonl`):

| | too high by one | too low by one |
|---|---|---|
| decisions | 17 | 0 |
| gemma | 4 | 5 |
| flashlite | 6 | 0 |

The answer key is one person's reading of each ticket, and 48 tickets is a small set: a gap of two or
three tickets between backends is within what relabeling a few borderline tickets would move.

---

#### So, Which One?

- 🟢 **Decisions API** for routing and yes/no checks: the best department and refund scores here, a
  median of 208 ms, and $0.0018 for the whole run. Its confidence score is the feature the others lack —
  every urgency answer at confidence ≥ 0.7 was right (23/23); below 0.7 it was right 8 times in 25.
  Send the unsure ones to a person or a bigger model.
- ⚠️ **Ordered scales need calibration.** On the three-level urgency scale the Decisions API's top level
  was one step too high 17 times and never too low. Tune the rubric wording, or act on `score` with your
  own thresholds instead of the top level.
- 🟢 **Gemini Flash-Lite** scored best on urgency and was 3.5× slower than the Decisions API at median.
- ❌ **Gemma 4 E2B on a laptop CPU** answers offline at no cost, at 5.6 s median, and put 4 of the 8
  high-urgency tickets at normal — the expensive direction to be wrong in triage.

Scope: one run of 48 English, Spanish and German text tickets, three questions each, temperature 0 for
the generative backends, Decisions API called over REST from a home connection. No images, audio or
PDFs; no concurrency; Gemma latency is CPU-bound and would differ on a GPU.

