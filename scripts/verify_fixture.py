#!/usr/bin/env python3
"""Pre-session check: prove the fixture is intact before a participant arrives.

Exercises everything that does not need a model credential — the MCP scope
matrix, the seeded Exercise 1 defect, and the planted injection payloads — by
driving the agent's own MCP client against a running hotel-mcp.

    python scripts/verify_fixture.py --mcp-url http://127.0.0.1:9100/mcp \
        --customer-key "$CUSTOMER_KEY" --ops-key "$OPS_KEY"

Exits non-zero if any check fails. A failure means the fixture has drifted and
the exercise it supports will not work.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent" / "hotel-agent"
sys.path.insert(0, str(AGENT_DIR))

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"  [{PASS if ok else FAIL}] {name}{'  ' + detail if detail else ''}")


async def tools_for(mcp_url: str, key: str) -> dict:
    """Reload the agent's config/auth/mcp_client under a given credential."""
    os.environ["HOTEL_MCP_URL"] = mcp_url
    os.environ["HOTEL_MCP_API_KEY"] = key
    import config, auth, mcp_client
    for module in (config, auth, mcp_client):
        importlib.reload(module)
    return {t.name: t for t in await mcp_client.load_mcp_tools()}


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--mcp-url", default=os.environ.get("HOTEL_MCP_URL", "http://127.0.0.1:9100/mcp"))
    p.add_argument("--customer-key", default=os.environ.get("CUSTOMER_KEY", ""))
    p.add_argument("--ops-key", default=os.environ.get("OPS_KEY", ""))
    p.add_argument("--admin-token", default=os.environ.get("HOTEL_MCP_ADMIN_TOKEN", ""))
    args = p.parse_args()
    if not args.customer_key or not args.ops_key:
        sys.exit("Need --customer-key and --ops-key (or CUSTOMER_KEY / OPS_KEY in the environment).")

    print("\n1. Tool discovery")
    ops = await tools_for(args.mcp_url, args.ops_key)
    expected = {"get_booking", "list_my_bookings", "search_availability", "get_booking_policies",
                "modify_booking", "cancel_booking", "create_booking"}
    check("all 7 tools discovered", set(ops) == expected,
          f"missing {sorted(expected - set(ops))}" if set(ops) != expected else "")

    print("\n2. Least privilege (Exercise 3 baseline)")
    cust = await tools_for(args.mcp_url, args.customer_key)
    read = json.loads(await cust["get_booking"].ainvoke({"booking_ref": "GM-4471"}))
    check("customer identity can read", read.get("room_type") == "deluxe")
    denied = json.loads(await cust["cancel_booking"].ainvoke({"booking_ref": "GM-8845", "reason": "verify"}))
    check("customer identity write is DENIED", "booking:write" in denied.get("error", ""),
          denied.get("error", "")[:60])
    mine = json.loads(await cust["list_my_bookings"].ainvoke({}))
    check("guest binding scopes list_my_bookings", mine.get("count") == 2,
          f"{mine.get('count')} bookings for {mine.get('guest_id')}")

    print("\n3. Planted injection payloads (Exercise 4, categories 2 and 3)")
    poisoned = await cust["get_booking"].ainvoke({"booking_ref": "GM-7731"})
    check("cat 3: booking record carries the payload", "cancel_booking" in poisoned and "GM-9902" in poisoned)
    loyalty = await cust["get_booking_policies"].ainvoke({"topic": "loyalty"})
    check("cat 2: loyalty document carries the payload", "INTERNAL AGENT DIRECTIVE" in loyalty)
    clean = await cust["get_booking_policies"].ainvoke({"topic": "cancellation"})
    check("control: cancellation document is clean", "DIRECTIVE" not in clean)

    print("\n4. The Exercise 1 date defect")
    ops = await tools_for(args.mcp_url, args.ops_key)
    import config
    check("legacy_date_compat is enabled", config.settings.legacy_date_compat is True)
    before = json.loads(await ops["get_booking"].ainvoke({"booking_ref": "GM-4471"}))
    ack = json.loads(await ops["modify_booking"].ainvoke(
        {"booking_ref": "GM-4471", "check_in": "2026-04-06", "nights": 3}))
    after = json.loads(await ops["get_booking"].ainvoke({"booking_ref": "GM-4471"}))
    print(f"        before  {before['check_in']}")
    print(f"        model asked for      2026-04-06 (6 April)")
    print(f"        acknowledgement says {ack['check_in']} -> {ack['check_out']}, {ack['total_usd']} USD")
    print(f"        record actually holds {after['check_in']}")
    check("ack shows the requested date", ack["check_in"] == "2026-04-06")
    check("record holds the WRONG date", after["check_in"] == "2026-06-04")
    check("price is identical, so cost hides it", ack["total_usd"] == 1020)

    print("\n5. Restore baseline")
    # Deliberately NOT through modify_booking: while the defect is live, every
    # date written through the agent is wrong, including a repair. That is why
    # hotel-mcp has an admin reset, and why a participant who "fixes" state by
    # asking the agent to set it back has not fixed anything.
    if not args.admin_token:
        check("baseline restored", False, "no --admin-token; run scripts/reset_fixture.py by hand")
    else:
        import httpx
        base = args.mcp_url.rstrip("/").removesuffix("/mcp")
        r = httpx.post(f"{base}/admin/reset", headers={"x-admin-token": args.admin_token}, timeout=30.0)
        check("admin reset accepted", r.status_code == 200, f"HTTP {r.status_code}")
        final = json.loads(await ops["get_booking"].ainvoke({"booking_ref": "GM-4471"}))
        check("GM-4471 back to 2026-05-12", final["check_in"] == "2026-05-12", final["check_in"])

    failed = [r for r in results if r[0] == FAIL]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("\nFIXTURE HAS DRIFTED:")
        for _, name, detail in failed:
            print(f"  - {name} {detail}")
        return 1
    print("Fixture intact.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
