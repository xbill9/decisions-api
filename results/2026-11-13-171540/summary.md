# Decisions API vs generative backends — 2026-11-13-171540

48 hand-labeled support tickets, 3 questions each, one request per ticket per backend.
Models: decisions=`gemini-decision-1`, gemma=`/home/xbill/models/gemma-4-E2B-it-qat-q4_0-exact-v2/gemma-4-E2B-it-q4_0-exact.gguf` on local CPU llama-server, flashlite=`gemini-3.5-flash-lite`.

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
