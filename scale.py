#!/usr/bin/env python3
"""Latency as the number of questions grows: 1 -> 100 yes/no questions, one request.

The launch post says Decisions API latency stays nearly flat from 1 to 100
questions. A generative model writes one answer per question, so its time
should grow with the count. This measures both on the same ticket.

    python3 scale.py                       # decisions + gemma
    python3 scale.py --backends decisions,gemma,flashlite --reps 3
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
from pathlib import Path

from decide import BACKENDS

TICKET = ("Hi, I ordered the red blender (order #8812) on Monday with express shipping. It arrived "
          "today with a cracked jug and the receipt shows I was charged twice. I tried to log in to "
          "start a return but the reset email never came. I need this sorted before my mum's birthday "
          "on Saturday, otherwise I want my money back.")

TOPICS = [
    "a blender", "a toaster", "a laptop", "an order number", "express shipping", "standard shipping",
    "a cracked or broken item", "a missing item", "a duplicate charge", "a subscription", "a gift card",
    "a login problem", "a password reset", "two-factor authentication", "a deadline", "a birthday",
    "a wedding", "a refund", "an exchange", "a discount code", "a colour", "a size", "a store location",
    "a phone call", "an email that did not arrive", "a mobile app crash", "a website error",
    "a delivery to a neighbour", "a courier", "international shipping", "a warranty", "a receipt",
    "a bank dispute", "a complaint about staff", "praise for staff", "a product review",
    "a privacy request", "account deletion", "a business customer", "a charity", "a journalist",
    "a job application", "opening hours", "a family member", "a pet", "food", "furniture", "clothing",
    "electronics", "a weekend", "a Monday", "a payment card", "PayPal", "cash on delivery", "a coupon",
    "a loyalty programme", "a price increase", "a cancelled order", "a damaged box", "an empty box",
    "a late delivery", "a safety hazard", "a fire risk", "a recall", "a manual", "assembly instructions",
    "a spare part", "a cable", "a battery", "a charger", "a screen", "a camera", "headphones",
    "a jacket", "shoes", "a kitchen appliance", "a promise to pay", "a threat to leave",
    "a social media post", "a lawyer", "a second order", "a tracking number", "a customs fee",
    "a tax invoice", "a currency conversion", "a store credit", "an apology", "a supervisor",
    "a chat transcript", "a survey", "a newsletter", "an unsubscribe request", "a password",
    "a username", "an address change", "a phone number change", "a pre-order", "a backorder",
    "a bundle deal", "a student discount",
]
assert len(TOPICS) >= 100


def questions(n: int) -> dict:
    return {f"q{i:03d}": {"type": "noul", "instructions": f"Does the message mention {TOPICS[i]}?"}
            for i in range(n)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backends", default="decisions,gemma")
    ap.add_argument("--counts", default="1,10,25,50,100")
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    backends, counts = a.backends.split(","), [int(c) for c in a.counts.split(",")]
    for b in backends:
        BACKENDS[b](TICKET, questions(1))  # warm-up
    rows = []
    for rep in range(a.reps):
        for n in counts:
            for b in backends:
                try:
                    r = BACKENDS[b](TICKET, questions(n))
                    rows.append({"backend": b, "n": n, "rep": rep, "latency_s": r["latency_s"],
                                 "usage": r["usage"], "answered": len(r["answers"])})
                except Exception as e:  # noqa: BLE001
                    rows.append({"backend": b, "n": n, "rep": rep, "error": str(e)[:300]})
                print(b, n, rep, f"{rows[-1].get('latency_s', float('nan')):.2f}s", flush=True)

    out = Path("results") / f"scale-{dt.datetime.now().astimezone():%Y-%m-%d-%H%M%S}"
    out.mkdir(parents=True)
    (out / "rows.json").write_text(json.dumps(rows, indent=1))
    summary = {}
    lines = ["| questions | " + " | ".join(f"{b} median" for b in backends) + " |",
             "|---|" + "---|" * len(backends)]
    for n in counts:
        cells = []
        for b in backends:
            lat = [r["latency_s"] for r in rows if r["backend"] == b and r["n"] == n and "latency_s" in r]
            med = statistics.median(lat) if lat else None
            summary.setdefault(b, {})[n] = {"median_s": med, "runs": len(lat)}
            cells.append(f"{1000 * med:,.0f} ms" if med is not None else "error")
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    md = "\n".join(lines) + f"\n\nMedian of {a.reps} runs per cell.\n"
    (out / "summary.md").write_text(md)
    print(md)
    print(out)


if __name__ == "__main__":
    main()
