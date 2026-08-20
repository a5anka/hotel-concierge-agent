"""Caller identity and scope extraction for hotel-mcp.

Two credential shapes are accepted, matching the two stages of the
least-privilege exercise:

  Stage A  ``API-Key: <key>``          -> scopes looked up in HOTEL_MCP_API_KEYS
  Stage B  ``Authorization: Bearer``   -> scopes from the token's ``scope`` claim,
                                          subject from ``sub``, guest binding
                                          from ``guest_id``

In a real Agent Manager deployment the MCP Proxy in front of this server
validates the agent-identity token and enforces per-tool scopes. The checks
here are deliberate defence in depth, so the exercise is still demonstrable
without the platform in the loop (local rehearsal, CI) and so a facilitator
can prove a denial came from policy rather than from the model refusing.

Headers are read off the live Starlette request via the FastMCP ``Context``
rather than a ContextVar, because FastMCP runs tool calls in a separate task
group from the ASGI middleware chain and ContextVars do not survive that hop.

SECURITY NOTE: this module decodes the bearer token WITHOUT verifying its
signature. That is acceptable only because this is a disposable test fixture
sitting behind a gateway that has already verified the token. Never copy this
file into a production service.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("hotel-mcp.auth")

REQUIRE_AUTH = os.environ.get("HOTEL_MCP_REQUIRE_AUTH", "true").lower() != "false"

# Stage A static keys, semicolon-delimited fields because scope names contain
# colons: "key;scope1|scope2;subject[;guest_id]", comma separated. Fixture only.
_RAW_KEYS = os.environ.get("HOTEL_MCP_API_KEYS", "")

READ = "booking:read"
WRITE = "booking:write"

# Which scope each tool demands. Kept as data so the facilitator can show a
# participant the authorisation matrix without reading the tool bodies.
TOOL_SCOPES: dict[str, str] = {
    "get_booking": READ,
    "list_my_bookings": READ,
    "search_availability": READ,
    "get_booking_policies": READ,
    "modify_booking": WRITE,
    "cancel_booking": WRITE,
    "create_booking": WRITE,
}


@dataclass
class Caller:
    subject: str = "anonymous"
    scopes: set[str] = field(default_factory=set)
    guest_id: str | None = None
    credential: str = "none"

    def has(self, scope: str) -> bool:
        return scope in self.scopes


class ScopeDenied(Exception):
    """Raised when the caller's credential does not carry the required scope.

    FastMCP turns this into an MCP tool error, so the agent sees a refusal it
    did not author. That distinction matters: a denial in the trace proves the
    platform blocked the call, not that the model declined to make it.
    """


def _static_key_table() -> dict[str, tuple[set[str], str, str | None]]:
    table: dict[str, tuple[set[str], str, str | None]] = {}
    for entry in _RAW_KEYS.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(";")
        if len(parts) < 2:
            log.warning("ignoring malformed HOTEL_MCP_API_KEYS entry")
            continue
        key = parts[0]
        scopes = set(filter(None, parts[1].split("|")))
        subject = parts[2] if len(parts) > 2 and parts[2] else "static-key"
        guest_id = parts[3] if len(parts) > 3 and parts[3] else None
        table[key] = (scopes, subject, guest_id)
    return table


def _decode_jwt_claims(token: str) -> dict:
    """Read the payload segment of a JWT. See the SECURITY NOTE above."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        log.warning("bearer token is not a decodable JWT; treating as unscoped")
        return {}


def caller_from_headers(headers) -> Caller:
    """Build a Caller from inbound request headers.

    Bearer wins over API-Key so an agent that has been migrated to
    agent-identity auth is not silently downgraded by a stale static key still
    sitting in its environment.
    """
    auth = headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        claims = _decode_jwt_claims(auth.split(" ", 1)[1].strip())
        raw = claims.get("scope") or claims.get("scp") or ""
        scopes = set(raw.split()) if isinstance(raw, str) else set(raw)
        return Caller(
            subject=str(claims.get("sub") or claims.get("client_id") or "unknown"),
            scopes=scopes,
            guest_id=claims.get("guest_id"),
            credential="bearer",
        )

    api_key = headers.get("api-key") or headers.get("x-api-key")
    if api_key:
        scopes, subject, guest_id = _static_key_table().get(api_key, (set(), "unrecognised-key", None))
        return Caller(subject=subject, scopes=scopes, guest_id=guest_id, credential="api-key")

    return Caller(credential="none")


def caller_from_context(ctx) -> Caller:
    """Extract the caller from a FastMCP Context. Falls back to an anonymous
    caller for stdio or in-process invocation, which has no HTTP request."""
    request = getattr(getattr(ctx, "request_context", None), "request", None)
    if request is None:
        return Caller(credential="none")
    return caller_from_headers(request.headers)


def require_scope(ctx, scope: str) -> Caller:
    """Gate a tool on a scope. Every tool calls this as its first statement."""
    caller = caller_from_context(ctx)
    if not REQUIRE_AUTH:
        return caller
    if not caller.has(scope):
        log.warning(
            "DENY subject=%s required=%s held=%s credential=%s",
            caller.subject,
            scope,
            sorted(caller.scopes) or "-",
            caller.credential,
        )
        raise ScopeDenied(
            f"Authorisation denied. This agent identity does not hold '{scope}'. "
            f"Held scopes: {sorted(caller.scopes) or 'none'} (subject={caller.subject})."
        )
    log.info("ALLOW subject=%s scope=%s", caller.subject, scope)
    return caller
