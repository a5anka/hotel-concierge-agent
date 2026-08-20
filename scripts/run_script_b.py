#!/usr/bin/env python3
"""Script B — adversarial traffic across all seven security categories.

Sends the 43 security cases, each labelled with exactly one primary category
and an expected safe outcome, and writes one result row per case.

    python scripts/run_script_b.py --agent-url https://<customer-agent>/chat --token <jwt>
    python scripts/run_script_b.py --deployment ops --category unauthorized-tool
    python scripts/run_script_b.py --judge      # local per-category grading

Cases marked deployment "both" run against whichever endpoint you pass; run
them twice, once per deployment, and compare. Identical agent, identical
attack, different blast radius, decided entirely by scope configuration — that
comparison is the clearest result this suite produces.

Every score reported here is RESILIENCE: higher is better, 100% means every
attack was withstood. Do not put it on a dashboard beside an attack-success
rate without saying which is which.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import EVALUATORS, FIXTURES, base_parser, iter_results, judge, write_results

JUDGE_FILES = {
    "direct-injection": "01-direct-injection.md",
    "indirect-retrieved": "02-indirect-retrieved.md",
    "indirect-mcp": "03-indirect-mcp.md",
    "cross-user": "04-cross-user.md",
    "role-manipulation": "05-role-manipulation.md",
    "unauthorized-tool": "06-unauthorized-tool.md",
    "policy-bypass": "07-policy-bypass.md",
}
RESILIENT = {"held", "blocked_by_platform"}


def _rubric(category: str) -> str:
    shared = (EVALUATORS / "security" / "shared-rubric.md").read_text()
    specific = (EVALUATORS / "security" / JUDGE_FILES[category]).read_text()
    return f"{specific}\n\n---\n\n{shared}"


def main() -> None:
    parser = base_parser(__doc__.split("\n")[0])
    parser.add_argument("--deployment", choices=["customer", "ops"], default="customer",
                        help="Which deployment the endpoint belongs to. Recorded on every row.")
    args = parser.parse_args()

    rows = []
    for row in iter_results(args, "script_b_cases.jsonl"):
        row["run_against"] = args.deployment
        rows.append(row)

    if args.judge:
        for row in rows:
            row["judgement"] = judge(args.judge_model, _rubric(row["category"]), {
                "input": row["input"],
                "output": row["reply"],
                "exchanges": row["exchanges"],
                "expected_safe": row["expected_safe_outcome"],
                "legitimate": row["legitimate"],
                "tool_calls": "NOT CAPTURED — see the trace in the console",
                "booking_state": "NOT CAPTURED — see GET /admin/audit on hotel-mcp",
            })

    out = Path(args.out) if args.out else FIXTURES / f"script_b_results_{args.deployment}.jsonl"
    write_results(rows, out)

    print(f"\nCoverage ({args.deployment} deployment):", file=sys.stderr)
    for cat, n in sorted(Counter(r["category"] for r in rows).items()):
        legit = sum(1 for r in rows if r["category"] == cat and r["legitimate"])
        print(f"  {cat:22} {n:3} cases ({legit} legitimate control)", file=sys.stderr)

    if not args.judge:
        print("\nNo local grading. Score this traffic with the console's evaluators,\n"
              "one per category (see evaluators/security/README.md).", file=sys.stderr)
        return

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_cat[row["category"]].append(row)

    print(f"\n{'category':<22}{'cases':>6}{'held':>6}{'blocked':>9}{'breached':>10}"
          f"{'unclear':>9}{'resilience':>12}", file=sys.stderr)
    for cat in sorted(by_cat):
        group = by_cat[cat]
        counts = Counter(r["judgement"].get("verdict", "unclear") for r in group)
        resilient = sum(counts[v] for v in RESILIENT)
        pct = f"{100 * resilient / len(group):.0f}%"
        print(f"{cat:<22}{len(group):>6}{counts['held']:>6}{counts['blocked_by_platform']:>9}"
              f"{counts['breached']:>10}{counts['unclear']:>9}{pct:>12}", file=sys.stderr)

    breaches = [r for r in rows if r["judgement"].get("verdict") == "breached"]
    if breaches:
        print(f"\n{len(breaches)} failed case(s):", file=sys.stderr)
        for r in breaches:
            print(f"  {r['id']} [{r['category']}] {r['judgement'].get('evidence', '')[:110]}",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
