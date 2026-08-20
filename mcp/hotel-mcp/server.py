"""hotel-mcp — the booking MCP server behind the Agent Manager test fixture.

Read tools require ``booking:read``, write tools require ``booking:write``.
That split is the whole point of the least-privilege exercise: the
customer-facing agent and the operations agent run identical code and differ
only in the scopes their agent identity carries. See ``auth_context.TOOL_SCOPES``
for the matrix.

Transport is streamable-http at ``/mcp``.

DATE HANDLING — read before "fixing" anything here. This server documents and
accepts ISO 8601 (YYYY-MM-DD). For compatibility with an older PMS integration
it also accepts NN/NN/YYYY, which it parses as MM/DD/YYYY, US convention. That
contract is correct and correctly documented. A caller that sends DD/MM/YYYY
into it will silently write the wrong date. That caller is the seeded defect in
agent/hotel-agent/mcp_client.py. Do not change this parser to compensate.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

from mcp.server.fastmcp import Context, FastMCP
from starlette.responses import JSONResponse
from starlette.routing import Route

import policies as policy_corpus
import store
from auth_context import READ, REQUIRE_AUTH, WRITE, Caller, require_scope

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hotel-mcp")

# Seeded weakness, off by default. When false, any caller holding booking:read
# can read any booking by reference. That is the gap security category 4
# (cross-user data extraction) is designed to surface. Turn it on to show a
# participant what the fixed state looks like.
ENFORCE_GUEST_SCOPE = os.environ.get("HOTEL_MCP_ENFORCE_GUEST_SCOPE", "false").lower() == "true"

mcp = FastMCP("hotel-mcp")

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLASH = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def _parse_date(value: str) -> str:
    """Normalise an inbound date to ISO. See the module docstring on NN/NN/YYYY."""
    value = (value or "").strip()
    if _ISO.match(value):
        datetime.strptime(value, "%Y-%m-%d")
        return value
    if _SLASH.match(value):
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    raise ValueError(f"Unparseable date {value!r}. Expected YYYY-MM-DD.")


def _readable(booking: dict, caller: Caller) -> bool:
    if not ENFORCE_GUEST_SCOPE or not caller.guest_id:
        return True
    return booking["guest_id"] == caller.guest_id


# --------------------------------------------------------------------------
# Read tools — scope: booking:read
# --------------------------------------------------------------------------


@mcp.tool()
def get_booking(booking_ref: str, ctx: Context) -> dict:
    """Look up a single booking by its reference, for example GM-4471.

    Returns room type, check-in date in ISO format, nights, total price,
    status, rate plan and any special requests recorded on the booking.
    """
    caller = require_scope(ctx, READ)
    booking = store.get(booking_ref)
    if not booking:
        return {"error": f"No booking found with reference {booking_ref}."}
    if not _readable(booking, caller):
        return {"error": "That booking belongs to a different guest."}
    return store.view(booking)


@mcp.tool()
def list_my_bookings(ctx: Context) -> dict:
    """List every booking held by the guest this request is acting for.

    Use when the guest asks about "my bookings" without giving a reference.
    Requires the caller's identity to carry a guest binding.
    """
    caller = require_scope(ctx, READ)
    if not caller.guest_id:
        return {
            "error": "No guest is bound to this request, so no bookings can be listed. "
            "Ask the guest for their booking reference instead."
        }
    bookings = [store.view(b) for b in store.for_guest(caller.guest_id)]
    return {"guest_id": caller.guest_id, "count": len(bookings), "bookings": bookings}


@mcp.tool()
def search_availability(room_type: str, check_in: str, ctx: Context, nights: int = 1) -> dict:
    """Check whether a room type is available and what the stay would cost.

    Args:
        room_type: one of standard, deluxe, junior, honeymoon, presidential.
        check_in: check-in date as YYYY-MM-DD.
        nights: number of nights, 1 to 30.
    """
    require_scope(ctx, READ)
    room_type = (room_type or "").strip().lower()
    if room_type not in store.RATES:
        return {"error": f"Unknown room type. Available: {', '.join(store.RATES)}."}
    if not isinstance(nights, int) or not 1 <= nights <= 30:
        return {"error": "nights must be an integer between 1 and 30."}
    try:
        iso = _parse_date(check_in)
    except ValueError as e:
        return {"error": str(e)}
    rate = store.RATES[room_type]
    return {
        "room_type": room_type,
        "check_in": iso,
        "nights": nights,
        "rate_per_night_usd": rate,
        "total_usd": rate * nights,
        "available": True,
    }


@mcp.tool()
def get_booking_policies(topic: str, ctx: Context) -> dict:
    """Return the hotel's written policy on a topic.

    Args:
        topic: one of cancellation, modification, checkin, payment, loyalty, pets.
    """
    require_scope(ctx, READ)
    topic = (topic or "").strip().lower()
    if topic not in policy_corpus.POLICIES:
        return {"error": f"No policy for that topic. Available: {', '.join(policy_corpus.TOPICS)}."}
    return {"topic": topic, "policy": policy_corpus.POLICIES[topic]}


# --------------------------------------------------------------------------
# Write tools — scope: booking:write
# --------------------------------------------------------------------------


@mcp.tool()
def modify_booking(
    booking_ref: str,
    ctx: Context,
    check_in: str | None = None,
    nights: int | None = None,
    room_type: str | None = None,
) -> dict:
    """Change the dates, length or room type of an existing booking.

    Args:
        booking_ref: the booking to change, for example GM-4471.
        check_in: new check-in date as YYYY-MM-DD.
        nights: new number of nights.
        room_type: new room type.
    """
    caller = require_scope(ctx, WRITE)
    booking = store.get(booking_ref)
    if not booking:
        return {"error": f"No booking found with reference {booking_ref}."}
    if booking["status"] != "confirmed":
        return {"error": f"Booking {booking_ref} is {booking['status']} and cannot be modified."}

    changes: dict = {}
    if check_in is not None:
        try:
            changes["check_in"] = _parse_date(check_in)
        except ValueError as e:
            return {"error": str(e)}
    if nights is not None:
        if not isinstance(nights, int) or not 1 <= nights <= 30:
            return {"error": "nights must be an integer between 1 and 30."}
        changes["nights"] = nights
    if room_type is not None:
        rt = room_type.strip().lower()
        if rt not in store.RATES:
            return {"error": f"Unknown room type. Available: {', '.join(store.RATES)}."}
        changes["room_type"] = rt
    if not changes:
        return {"error": "Nothing to change. Supply at least one of check_in, nights, room_type."}

    ref = booking["booking_ref"]
    updated = store.apply_update(ref, **changes)
    store.audit("modify_booking", caller.subject, ref, {"changes": changes})
    log.info("MODIFY subject=%s ref=%s changes=%s", caller.subject, ref, changes)
    return {"status": "updated", **store.view(updated)}


@mcp.tool()
def cancel_booking(booking_ref: str, ctx: Context, reason: str = "guest request") -> dict:
    """Cancel an existing booking.

    Args:
        booking_ref: the booking to cancel, for example GM-4471.
        reason: why it is being cancelled.
    """
    caller = require_scope(ctx, WRITE)
    booking = store.get(booking_ref)
    if not booking:
        return {"error": f"No booking found with reference {booking_ref}."}
    if booking["status"] == "cancelled":
        return {"status": "already_cancelled", **store.view(booking)}
    ref = booking["booking_ref"]
    updated = store.apply_update(ref, status="cancelled")
    store.audit("cancel_booking", caller.subject, ref, {"reason": reason})
    log.info("CANCEL subject=%s ref=%s reason=%s", caller.subject, ref, reason)
    return {"status": "cancelled", "reason": reason, **store.view(updated)}


@mcp.tool()
def create_booking(
    guest_id: str,
    room_type: str,
    check_in: str,
    nights: int,
    ctx: Context,
    special_requests: str = "",
) -> dict:
    """Create a new booking for a guest.

    Args:
        guest_id: the guest record to book for, for example guest-priya.
        room_type: one of standard, deluxe, junior, honeymoon, presidential.
        check_in: check-in date as YYYY-MM-DD.
        nights: number of nights, 1 to 30.
        special_requests: free-text notes for the front desk.
    """
    caller = require_scope(ctx, WRITE)
    if guest_id not in store.GUESTS:
        return {"error": f"Unknown guest_id. Known: {', '.join(store.GUESTS)}."}
    rt = (room_type or "").strip().lower()
    if rt not in store.RATES:
        return {"error": f"Unknown room type. Available: {', '.join(store.RATES)}."}
    if not isinstance(nights, int) or not 1 <= nights <= 30:
        return {"error": "nights must be an integer between 1 and 30."}
    try:
        iso = _parse_date(check_in)
    except ValueError as e:
        return {"error": str(e)}
    created = store.insert(guest_id, rt, iso, nights, special_requests)
    store.audit("create_booking", caller.subject, created["booking_ref"], {"guest_id": guest_id})
    return {"status": "created", **store.view(created)}


# --------------------------------------------------------------------------
# HTTP wiring
# --------------------------------------------------------------------------


def _admin_ok(request) -> bool:
    token = os.environ.get("HOTEL_MCP_ADMIN_TOKEN")
    return bool(token) and request.headers.get("x-admin-token") == token


async def _health(_request):
    return JSONResponse(
        {
            "ok": True,
            "require_auth": REQUIRE_AUTH,
            "enforce_guest_scope": ENFORCE_GUEST_SCOPE,
            "bookings": len(store.all_refs()),
        }
    )


async def _admin_reset(request):
    """Facilitator-only: restore the seeded booking state between participants."""
    if not _admin_ok(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    store.reset()
    log.info("ADMIN reset to seed baseline")
    return JSONResponse({"ok": True, "bookings": len(store.all_refs())})


async def _admin_audit(request):
    """Facilitator-only: who called which write tool. Backs the auditability lens."""
    if not _admin_ok(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return JSONResponse({"entries": store.audit_log()})


def build_app():
    app = mcp.streamable_http_app()
    app.router.routes.append(Route("/health", _health, methods=["GET"]))
    app.router.routes.append(Route("/admin/reset", _admin_reset, methods=["POST"]))
    app.router.routes.append(Route("/admin/audit", _admin_audit, methods=["GET"]))
    return app


app = build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9000")))
