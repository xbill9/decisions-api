#!/usr/bin/env python3
"""Run every labeled ticket through each backend and score the answers.

All counting, accuracy and latency statistics are computed here, from the rows
recorded in rows.jsonl -- nothing in the summary is typed in by hand.

    python3 bench.py                         # all five backends
    python3 bench.py --backends decisions,gemma
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import statistics
from pathlib import Path

from decide import BACKENDS, DECISION_MODEL, FLASH_MODEL, FLASHLITE_MODEL, HYDROGEN_MODEL, pick
from tickets import QUESTIONS, TICKETS

PRICE_PER_M_INPUT = 0.10  # USD, gemini-decision-1, from the launch post; output is $0
CONF = 0.7  # the routing threshold the Decisions docs use as an example


def pct(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def run(backends: list[str], out: Path, seed: int) -> list[dict]:
    rng = random.Random(seed)
    for b in backends:  # warm-up: connection setup, model load, prompt cache
        BACKENDS[b]("warm-up ticket", QUESTIONS)
    rows = []
    with (out / "rows.jsonl").open("w") as f:
        for i, (text, dept, refund, urgency) in enumerate(TICKETS):
            gold = {"dept": dept, "wants_refund": refund, "urgency": urgency}
            order = backends[:]
            rng.shuffle(order)  # interleave, so drift hits every backend alike
            for b in order:
                row = {"ticket": i, "backend": b, "gold": gold}
                try:
                    res = BACKENDS[b](text, QUESTIONS)
                    row["latency_s"] = res["latency_s"]
                    row["usage"] = res["usage"]
                    row["pred"] = {k: pick(a) for k, a in res["answers"].items()}
                    row["confidence"] = {k: a.get("confidence") for k, a in res["answers"].items()}
                except Exception as e:  # noqa: BLE001 -- record and keep going
                    row["error"] = str(e)[:300]
                rows.append(row)
                f.write(json.dumps(row) + "\n")
            print(f"{i + 1}/{len(TICKETS)}", end="\r", flush=True)
    print()
    return rows


def summarize(rows: list[dict], backends: list[str]) -> dict:
    s = {"tickets": len(TICKETS), "backends": {}}
    for b in backends:
        rs = [r for r in rows if r["backend"] == b]
        ok = [r for r in rs if "error" not in r]
        lat = [r["latency_s"] for r in ok]
        d = {
            "calls": len(rs),
            "errors": len(rs) - len(ok),
            "latency_s": {
                "median": statistics.median(lat),
                "p90": pct(lat, 0.9),
                "min": min(lat),
                "max": max(lat),
            },
            "input_tokens_total": sum(r["usage"].get("total_input_tokens") or 0 for r in ok),
            "output_tokens_total": sum(r["usage"].get("total_output_tokens") or 0 for r in ok),
            "accuracy": {},
        }
        for q in QUESTIONS:
            right = sum(r["pred"][q] == r["gold"][q] for r in ok)
            d["accuracy"][q] = {"correct": right, "of": len(ok), "rate": right / len(ok)}
        near = sum(abs(r["pred"]["urgency"] - r["gold"]["urgency"]) <= 1 for r in ok)
        d["accuracy"]["urgency_within_one"] = {"correct": near, "of": len(ok), "rate": near / len(ok)}
        all3 = sum(all(r["pred"][q] == r["gold"][q] for q in QUESTIONS) for r in ok)
        d["accuracy"]["all_three"] = {"correct": all3, "of": len(ok), "rate": all3 / len(ok)}

        if b == "decisions":
            d["cost_usd"] = d["input_tokens_total"] * PRICE_PER_M_INPUT / 1e6
            # Does the confidence score separate right answers from wrong ones?
            split = {}
            for q in QUESTIONS:
                hi = [r for r in ok if r["confidence"][q] >= CONF]
                lo = [r for r in ok if r["confidence"][q] < CONF]
                split[q] = {
                    f"conf>={CONF}": {"n": len(hi), "correct": sum(r["pred"][q] == r["gold"][q] for r in hi)},
                    f"conf<{CONF}": {"n": len(lo), "correct": sum(r["pred"][q] == r["gold"][q] for r in lo)},
                }
            d["by_confidence"] = split
        s["backends"][b] = d

    # How often does each backend agree with the Decisions API?
    if "decisions" in backends:
        ref = {r["ticket"]: r for r in rows if r["backend"] == "decisions" and "error" not in r}
        for b in backends:
            if b == "decisions":
                continue
            agree = {}
            for q in QUESTIONS:
                pairs = [(ref[r["ticket"]], r) for r in rows
                         if r["backend"] == b and "error" not in r and r["ticket"] in ref]
                agree[q] = {"same": sum(a["pred"][q] == r["pred"][q] for a, r in pairs), "of": len(pairs)}
            s["backends"][b]["agreement_with_decisions"] = agree
    return s


def to_markdown(s: dict, meta: dict) -> str:
    bs = list(s["backends"])
    L = [f"# Decisions API vs generative backends — {meta['when']}", ""]
    L.append(f"{s['tickets']} hand-labeled support tickets, 3 questions each, one request per ticket per backend.")
    L.append(f"Models: decisions=`{meta['decision_model']}`, gemma=`{meta['gemma_model']}` on local CPU llama-server, "
             f"flashlite=`{meta['flashlite_model']}`, flash=`{meta['flash_model']}`, "
             f"hydrogen=`{meta['hydrogen_model']}`.")
    L.append("")
    L.append("| | " + " | ".join(bs) + " |")
    L.append("|---|" + "---|" * len(bs))

    def row(label, f):
        L.append(f"| {label} | " + " | ".join(f(s["backends"][b]) for b in bs) + " |")

    for q in ["dept", "wants_refund", "urgency", "urgency_within_one", "all_three"]:
        row(f"{q} correct", lambda d, q=q: f"{d['accuracy'][q]['correct']}/{d['accuracy'][q]['of']} "
                                            f"({100 * d['accuracy'][q]['rate']:.0f}%)")
    row("median latency", lambda d: f"{1000 * d['latency_s']['median']:.0f} ms")
    row("p90 latency", lambda d: f"{1000 * d['latency_s']['p90']:.0f} ms")
    row("input tokens", lambda d: f"{d['input_tokens_total']:,}")
    row("output tokens", lambda d: f"{d['output_tokens_total']:,}")
    row("errors", lambda d: str(d["errors"]))
    dd = s["backends"].get("decisions")
    if dd:
        L += ["", (f"Decisions API cost for the run: ${dd['cost_usd']:.6f} "
                   f"({dd['input_tokens_total']:,} input tokens at ${PRICE_PER_M_INPUT}/1M).")]
        L += ["", f"Decisions API, split by its confidence score (threshold {CONF}):", ""]
        L.append("| question | confident: correct/n | unsure: correct/n |")
        L.append("|---|---|---|")
        for q, v in dd["by_confidence"].items():
            hi, lo = v[f"conf>={CONF}"], v[f"conf<{CONF}"]
            L.append(f"| {q} | {hi['correct']}/{hi['n']} | {lo['correct']}/{lo['n']} |")
    for b in bs:
        ag = s["backends"][b].get("agreement_with_decisions")
        if ag:
            L += ["", f"{b} agrees with the Decisions API on: "
                  + ", ".join(f"{q} {v['same']}/{v['of']}" for q, v in ag.items())]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backends", default="decisions,gemma,flashlite,flash,hydrogen")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    backends = a.backends.split(",")
    when = dt.datetime.now().astimezone().strftime("%Y-%m-%d-%H%M%S")
    out = Path("results") / when
    out.mkdir(parents=True)
    import httpx

    from decide import GEMMA_URL
    gemma_model = None
    if "gemma" in backends:
        gemma_model = httpx.get(f"{GEMMA_URL}/v1/models").json()["data"][0]["id"]
    meta = {"when": when, "decision_model": DECISION_MODEL, "flashlite_model": FLASHLITE_MODEL,
            "flash_model": FLASH_MODEL, "hydrogen_model": HYDROGEN_MODEL,
            "gemma_model": gemma_model, "seed": a.seed, "backends": backends}
    rows = run(backends, out, a.seed)
    s = summarize(rows, backends)
    (out / "summary.json").write_text(json.dumps({"meta": meta, **s}, indent=2))
    md = to_markdown(s, meta)
    (out / "summary.md").write_text(md)
    print(md)
    print(f"rows: {out / 'rows.jsonl'}")


if __name__ == "__main__":
    main()
