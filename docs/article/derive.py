#!/usr/bin/env python3
"""Compute every derived figure the article quotes, from the raw result files.

    python3 docs/article/derive.py > docs/article/evidence/derived.txt
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import scale  # noqa: E402
from tickets import TICKETS  # noqa: E402

BENCH = "results/2026-11-13-180410"
SCALE = "results/scale-2026-11-13-182530"
NAMES = ["decisions", "gemma", "flashlite", "flash", "hydrogen"]

rows = [json.loads(line) for line in (ROOT / BENCH / "rows.jsonl").open()]
s = json.loads((ROOT / BENCH / "summary.json").read_text())["backends"]
sc = json.loads((ROOT / SCALE / "summary.json").read_text())

print("# Derived figures for the article, computed by docs/article/derive.py from the files named.")
print(f"\n## From {BENCH}")
print("tickets", len(TICKETS), "hard block (last 18):", len(TICKETS[30:]))
med = {b: s[b]["latency_s"]["median"] for b in NAMES}
for b in NAMES:
    d = [r["pred"]["urgency"] - r["gold"]["urgency"] for r in rows if r["backend"] == b]
    hi = [r for r in rows if r["backend"] == b and r["gold"]["urgency"] == 2]
    print(f"{b}: urgency too high {sum(x > 0 for x in d)}, too low {sum(x < 0 for x in d)}; "
          f"high-urgency tickets rated normal: {sum(r['pred']['urgency'] == 1 for r in hi)} of {len(hi)}")
    print(f"{b}: median per ticket {med[b]:.1f} s; {med[b] / med['decisions']:.1f}x the Decisions API median")
    print(f"{b}: output tokens per ticket (mean) {s[b]['output_tokens_total'] / 48:.0f}; "
          f"input tokens per ticket (mean) {s[b]['input_tokens_total'] / 48:.0f}")
print(f"decisions cost ${s['decisions']['cost_usd']:.4f}")
for q, v in s["decisions"]["by_confidence"].items():
    hi, lo = v["conf>=0.7"], v["conf<0.7"]
    print(f"decisions {q} at or above 0.7 confidence: {hi['correct']} of {hi['n']} correct; "
          f"below 0.7 confidence: {lo['correct']} of {lo['n']} correct")
a = s["decisions"]["accuracy"]["urgency"]
print(f"decisions urgency correct: {a['correct']} of {a['of']}")

print(f"\n## From {SCALE}")
print("scale ticket words", len(scale.TICKET.split()))
m = {b: {n: sc[b][str(n)]["median_s"] for n in (1, 100)} for b in NAMES}
for b in NAMES:
    print(f"{b}: 1q {1000 * m[b][1]:.0f} ms, 100q {1000 * m[b][100]:.0f} ms ({m[b][100]:.1f} s), "
          f"growth {m[b][100] / m[b][1]:.1f}x; at 100q {m[b][100] / m['decisions'][100]:.1f}x the Decisions API")

print("\n## Run to run, decisions and gemma, previous run results/2026-11-13-171540")
prev = json.loads((ROOT / "results/2026-11-13-171540/summary.json").read_text())["backends"]
for b in ("decisions", "gemma"):
    same = all(prev[b]["accuracy"][q] == s[b]["accuracy"][q] for q in prev[b]["accuracy"])
    print(f"{b}: accuracy identical across runs: {same}; median {prev[b]['latency_s']['median']:.1f} s "
          f"then {s[b]['latency_s']['median']:.1f} s")

print("\n## Combined and relative figures")
for b in NAMES:
    acc = s[b]["accuracy"]
    print(f"{b}: team + refund {acc['dept']['correct'] + acc['wants_refund']['correct']}/96; "
          f"all three {acc['all_three']['correct']} of 48")
print(f"hydrogen output tokens / flash output tokens: "
      f"{s['hydrogen']['output_tokens_total'] / s['flash']['output_tokens_total']:.1f}x")

print("\n## Per-ticket answers, previous run vs this run")
prev_rows = [json.loads(line) for line in (ROOT / "results/2026-11-13-171540/rows.jsonl").open()]
for b in ("decisions", "gemma", "flashlite"):
    a = {r["ticket"]: r["pred"] for r in prev_rows if r["backend"] == b}
    c = {r["ticket"]: r["pred"] for r in rows if r["backend"] == b}
    diff = sum(a[t] != c[t] for t in a)
    print(f"{b}: tickets with any answer changed: {diff} of {len(a)}")
