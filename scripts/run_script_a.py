#!/usr/bin/env python3
"""Script A — representative traffic for hallucination and reasoning quality.

Sends the 36 quality cases and writes one result row per case. Point Agent
Manager's hallucination and reasoning-quality evaluators at the resulting
traffic; the `expected` and `ground_truth` fields in the fixture are the
reference answers.

    python scripts/run_script_a.py --agent-url https://<agent>/chat --token <jwt>
    python scripts/run_script_a.py --category out-of-corpus --judge

`--judge` grades the out-of-corpus slice locally with evaluators/quality/
grounded-refusal.md. Use it as a fallback, not as the primary path: the study
is partly about whether the console's own evaluators can do this.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import EVALUATORS, FIXTURES, base_parser, iter_results, judge, write_results


def main() -> None:
    args = base_parser(__doc__.split("\n")[0]).parse_args()
    rows = list(iter_results(args, "script_a_cases.jsonl"))

    if args.judge:
        rubric = (EVALUATORS / "quality" / "grounded-refusal.md").read_text()
        for row in rows:
            if row["category"] != "out-of-corpus":
                continue
            row["judgement"] = judge(args.judge_model, rubric, {
                "input": row["input"],
                "output": row["reply"],
                "expected": row["expected"],
            })

    out = Path(args.out) if args.out else FIXTURES / "script_a_results.jsonl"
    write_results(rows, out)

    print("\nCases by category:", file=sys.stderr)
    for cat, n in sorted(Counter(r["category"] for r in rows).items()):
        print(f"  {cat:22} {n:3}", file=sys.stderr)
    judged = [r for r in rows if "judgement" in r]
    if judged:
        print("\nLocal judgement (out-of-corpus only):", file=sys.stderr)
        for verdict, n in sorted(Counter(r["judgement"].get("verdict") for r in judged).items()):
            print(f"  {str(verdict):22} {n:3}", file=sys.stderr)
    print("\nHallucination and reasoning quality are scored in the console, not here.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
