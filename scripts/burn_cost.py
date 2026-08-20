#!/usr/bin/env python3
"""Drive model spend past a per-minute cost ceiling so the control is observable.

Exercise 2 asks for model expenditure to stay under 0.05 USD per minute and for
an observable enforcement result when the threshold is reached. A participant
cannot demonstrate that by chatting: normal traffic will not get near the
ceiling inside a session. This script gets there in about a minute.

    python scripts/burn_cost.py --agent-url https://<agent>/chat --token <jwt>
    python scripts/burn_cost.py --concurrency 8 --duration 180

It sends concurrent turns that ask for long, tool-heavy answers, and watches
for the moment responses stop looking normal: a non-200, a rate-limit shape, or
a block message in place of an answer. It prints when that first happened and
how far into the run.

It does NOT know the real cost. The console does. This produces the traffic and
timestamps the transition, so the participant can line it up against what the
platform reports.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from collections import Counter

import httpx

# Long, multi-tool answers. Each of these should fan out into several tool
# calls and a large completion, which is where the spend is.
PROMPTS = [
    "Compare every room type you offer for a seven-night stay: nightly rate, "
    "total, and who each one suits. Then walk through the cancellation and "
    "modification policy for each rate plan in full detail.",
    "I'm planning a long stay. Price out the standard, deluxe, junior, "
    "honeymoon and presidential for three, five and seven nights, and lay it "
    "all out with the differences explained.",
    "Give me the complete room service menu with descriptions and prices, then "
    "every local recommendation you have in all four categories, with why each "
    "one is worth going to.",
    "Explain every policy you have access to, in full, one section at a time: "
    "cancellation, modification, check-in, payment, loyalty and pets.",
]

BLOCK_HINTS = ("rate limit", "quota", "budget", "exceeded", "blocked", "policy",
               "too many requests", "unavailable")


def worker(idx: int, args, stop: threading.Event, results: list) -> None:
    with httpx.Client() as client:
        headers = {"Content-Type": "application/json"}
        if args.token:
            headers["Authorization"] = f"Bearer {args.token}"
        turn = 0
        while not stop.is_set():
            prompt = PROMPTS[(idx + turn) % len(PROMPTS)]
            started = time.perf_counter()
            try:
                r = client.post(
                    args.agent_url, headers=headers, timeout=120.0,
                    json={"message": prompt, "session_id": f"burn-{idx}-{turn}", "context": {}},
                )
                body = r.text
                status = r.status_code
            except Exception as e:
                body, status = f"<transport error: {e}>", 0
            results.append({
                "t": time.time(), "worker": idx, "turn": turn, "status": status,
                "chars": len(body), "elapsed_ms": round((time.perf_counter() - started) * 1000),
                "looks_blocked": status != 200 or any(h in body.lower() for h in BLOCK_HINTS),
            })
            turn += 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--agent-url", default=os.environ.get("AGENT_URL", "http://localhost:8000/chat"))
    p.add_argument("--token", default=os.environ.get("AGENT_TOKEN", ""))
    p.add_argument("--concurrency", type=int, default=6)
    p.add_argument("--duration", type=int, default=120, help="Seconds to run.")
    args = p.parse_args()

    print(f"Burning against {args.agent_url}", file=sys.stderr)
    print(f"{args.concurrency} workers for {args.duration}s. Watch the console's cost panel.\n",
          file=sys.stderr)

    results: list = []
    stop = threading.Event()
    started = time.time()
    threads = [threading.Thread(target=worker, args=(i, args, stop, results), daemon=True)
               for i in range(args.concurrency)]
    for t in threads:
        t.start()

    try:
        while time.time() - started < args.duration:
            time.sleep(5)
            done = len(results)
            blocked = sum(1 for r in results if r["looks_blocked"])
            print(f"  t+{int(time.time() - started):>3}s  {done:>4} turns  "
                  f"{blocked:>3} look blocked", file=sys.stderr)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=125)

    if not results:
        sys.exit("No responses at all. Check the URL and the token.")

    total = len(results)
    blocked = [r for r in results if r["looks_blocked"]]
    print(f"\n{total} turns in {int(time.time() - started)}s", file=sys.stderr)
    print(f"status codes: {dict(Counter(r['status'] for r in results))}", file=sys.stderr)

    if not blocked:
        print("\nNothing was refused. Either the ceiling was never reached, or it is not "
              "enforced on this deployment. Raise --concurrency or --duration and retry "
              "before concluding it is not enforced.", file=sys.stderr)
        return

    first = min(blocked, key=lambda r: r["t"])
    print(f"\nFirst refusal at t+{first['t'] - started:.0f}s "
          f"(turn {first['turn']}, worker {first['worker']}, status {first['status']})",
          file=sys.stderr)
    print(f"{len(blocked)}/{total} turns refused.", file=sys.stderr)
    print("\nLine that timestamp up against the console's cost panel. If the platform "
          "reports the ceiling being hit at a different moment, that gap is the finding.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
