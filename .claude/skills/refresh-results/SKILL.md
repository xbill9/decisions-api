---
name: refresh-results
description: Re-run the Decisions API benchmark and/or scale test, rebuild the README results section from the new summary files, then commit and push. Use after changing tickets, questions, prompts or models.
disable-model-invocation: true
---

Re-run and publish results. `$ARGUMENTS` picks what to run: `bench`, `scale`, or empty for both.

1. **Preflight.**
   - `curl -fsS 127.0.0.1:8080/health` must print `{"status":"ok"}`. If it doesn't, start Gemma with
     `make gemma` in the background, wait for `listening on` in its log, then check again.
   - `pgrep -af 'bench.py|scale.py'` must be empty. Never start a second run while one is going.
   - `ruff check .` passes.
2. **Run, one at a time, in the background** (Gemma is CPU-only; wait for each to finish):
   - bench: `python3 -u bench.py` (about 6 minutes)
   - scale: `python3 -u scale.py --backends decisions,gemma,flashlite --reps 3` (about 10 minutes)
   If any backend shows `errors` > 0 in the summary, stop and report the error text from `rows.jsonl`
   instead of publishing.
3. **Update README.md** from the newest `results/<run>/summary.md` (bench) and
   `results/scale-<run>/summary.md` (scale):
   - Paste the generated tables as they are. Replace the absolute GGUF path with the model name only.
   - Any extra figure (miss direction, ratios, "N of M") is computed by a short Python snippet over
     `rows.jsonl` / `summary.json` and quoted from its output. No mental arithmetic.
   - Update the run id and date in the section heading, and rewrite any "So, Which One?" bullet whose
     numbers changed. Keep the Scope paragraph accurate (ticket count, languages, reps).
4. **Commit and push** straight to `main`: the README plus the new `results/` directory. The message
   says what was run and the headline numbers.
5. Report the new headline numbers to the user and what moved compared with the previous run.
