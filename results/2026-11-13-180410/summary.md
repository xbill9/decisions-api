# Decisions API vs generative backends — 2026-11-13-180410

48 hand-labeled support tickets, 3 questions each, one request per ticket per backend.
Models: decisions=`gemini-decision-1`, gemma=`/home/xbill/models/gemma-4-E2B-it-qat-q4_0-exact-v2/gemma-4-E2B-it-q4_0-exact.gguf` on local CPU llama-server, flashlite=`gemini-3.5-flash-lite`, flash=`gemini-3.8-flash`, hydrogen=`gemini-4-hydrogen`.

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
