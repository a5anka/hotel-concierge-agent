"""Shared plumbing for the traffic scripts.

The scripts' primary job is to generate labelled traffic for Agent Manager's
evaluators, not to grade it. Every request uses the case id as its session id,
so any result in the console traces back to exactly one fixture line.

Local judging (`--judge`) exists as a fallback for the case where the console
cannot aggregate by a custom category label. Prefer the platform's evaluators
and record the gap as a finding rather than quietly working around it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import httpx

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
EVALUATORS = ROOT / "evaluators"


def load_cases(name: str, categories: list[str] | None = None) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in (FIXTURES / name).read_text().splitlines() if line.strip()]
    if categories:
        cases = [c for c in cases if c["category"] in categories]
    return cases


def base_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--agent-url", default=os.environ.get("AGENT_URL", "http://localhost:8000/chat"),
                   help="Agent /chat endpoint. Also read from AGENT_URL.")
    p.add_argument("--token", default=os.environ.get("AGENT_TOKEN", ""),
                   help="OAuth2 bearer token for the agent endpoint. Also read from AGENT_TOKEN.")
    p.add_argument("--category", action="append", dest="categories",
                   help="Restrict to one category. Repeatable.")
    p.add_argument("--out", default="", help="Results JSONL path. Defaults next to the fixture.")
    p.add_argument("--delay", type=float, default=0.0,
                   help="Seconds between cases. Raise this if a rate limit is in play.")
    p.add_argument("--judge", action="store_true",
                   help="Grade locally with an LLM judge instead of relying on the console.")
    p.add_argument("--judge-model", default=os.environ.get("JUDGE_MODEL", "claude-sonnet-5"))
    return p


def send(client: httpx.Client, url: str, token: str, message: str, session_id: str,
         context: dict[str, Any]) -> tuple[str, int, float]:
    """One turn. Returns (reply, status, elapsed_ms). Never raises."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    started = time.perf_counter()
    try:
        r = client.post(url, headers=headers,
                        json={"message": message, "session_id": session_id, "context": context},
                        timeout=120.0)
        elapsed = (time.perf_counter() - started) * 1000
        if r.status_code != 200:
            return f"<HTTP {r.status_code}: {r.text[:300]}>", r.status_code, elapsed
        return r.json().get("response", ""), 200, elapsed
    except Exception as e:
        return f"<transport error: {e}>", 0, (time.perf_counter() - started) * 1000


def run_case(client: httpx.Client, args, case: dict[str, Any]) -> dict[str, Any]:
    """Run one case, single or multi turn. Session id is the case id."""
    context = {"guest_id": case.get("guest_id"), "guest_name": case.get("guest_name")}
    turns = case.get("turns") or [case["input"]]
    exchanges = []
    for i, message in enumerate(turns):
        reply, status, elapsed = send(client, args.agent_url, args.token, message, case["id"], context)
        exchanges.append({"turn": i + 1, "input": message, "reply": reply,
                          "status": status, "elapsed_ms": round(elapsed)})
        if args.delay:
            time.sleep(args.delay)
    return {**case, "exchanges": exchanges, "reply": exchanges[-1]["reply"]}


def iter_results(args, fixture: str) -> Iterator[dict[str, Any]]:
    cases = load_cases(fixture, args.categories)
    if not cases:
        sys.exit("No cases matched. Check --category against the fixture file.")
    print(f"{len(cases)} case(s) -> {args.agent_url}", file=sys.stderr)
    with httpx.Client() as client:
        for n, case in enumerate(cases, 1):
            result = run_case(client, args, case)
            failed = any(e["status"] != 200 for e in result["exchanges"])
            print(f"  [{n}/{len(cases)}] {case['id']} {case['category']}"
                  f"{'  TRANSPORT FAILURE' if failed else ''}", file=sys.stderr)
            yield result


def write_results(rows: list[dict[str, Any]], path: Path) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"\nWrote {len(rows)} result(s) to {path}", file=sys.stderr)


def judge(model: str, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Call an LLM judge. Requires ANTHROPIC_API_KEY."""
    try:
        import anthropic
    except ImportError:
        sys.exit("--judge needs the anthropic package: pip install anthropic")
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": json.dumps(payload, indent=2)}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"verdict": "unclear", "reasoning": f"judge returned non-JSON: {text[:200]}"}
