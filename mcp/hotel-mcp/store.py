"""In-memory booking store, seeded from seed/bookings.json.

State is per-process and resets on restart, which is what you want between
test participants. `reset()` is exposed on the admin surface so a facilitator
can restore the baseline mid-session without a redeploy.
"""

from __future__ import annotations

import copy
import json
import threading
from datetime import date, timedelta
from pathlib import Path

SEED_PATH = Path(__file__).parent / "seed" / "bookings.json"

_LOCK = threading.Lock()
_SEED = json.loads(SEED_PATH.read_text())

RATES: dict[str, int] = _SEED["rates_per_night_usd"]
GUESTS: dict[str, dict] = _SEED["guests"]

_BOOKINGS: dict[str, dict] = {}
_AUDIT: list[dict] = []
_SEQ = [9000]


def reset() -> None:
    global _BOOKINGS, _AUDIT
    with _LOCK:
        _BOOKINGS = {b["booking_ref"]: copy.deepcopy(b) for b in _SEED["bookings"]}
        _AUDIT = []
        _SEQ[0] = 9000


reset()


def _check_out(check_in: str, nights: int) -> str:
    y, m, d = (int(p) for p in check_in.split("-"))
    return (date(y, m, d) + timedelta(days=nights)).isoformat()


def view(booking: dict) -> dict:
    """Public shape of a booking. Always emits canonical ISO dates."""
    guest = GUESTS.get(booking["guest_id"], {})
    return {
        "booking_ref": booking["booking_ref"],
        "guest_name": guest.get("name", "unknown"),
        "guest_tier": guest.get("tier"),
        "room_type": booking["room_type"],
        "check_in": booking["check_in"],
        "check_out": _check_out(booking["check_in"], booking["nights"]),
        "nights": booking["nights"],
        "total_usd": booking["total_usd"],
        "status": booking["status"],
        "rate_plan": booking["rate_plan"],
        "special_requests": booking["special_requests"],
    }


def get(ref: str) -> dict | None:
    return _BOOKINGS.get(ref.strip().upper())


def for_guest(guest_id: str) -> list[dict]:
    return [b for b in _BOOKINGS.values() if b["guest_id"] == guest_id]


def all_refs() -> list[str]:
    return sorted(_BOOKINGS)


def audit(action: str, subject: str, ref: str, detail: dict) -> None:
    with _LOCK:
        _AUDIT.append({"action": action, "subject": subject, "booking_ref": ref, **detail})


def audit_log() -> list[dict]:
    return list(_AUDIT)


def apply_update(ref: str, **changes) -> dict:
    with _LOCK:
        booking = _BOOKINGS[ref]
        booking.update({k: v for k, v in changes.items() if v is not None})
        booking["total_usd"] = RATES[booking["room_type"]] * booking["nights"]
        return copy.deepcopy(booking)


def insert(guest_id: str, room_type: str, check_in: str, nights: int, requests: str) -> dict:
    with _LOCK:
        _SEQ[0] += 1
        ref = f"GM-{_SEQ[0]}"
        booking = {
            "booking_ref": ref,
            "guest_id": guest_id,
            "room_type": room_type,
            "check_in": check_in,
            "nights": nights,
            "total_usd": RATES[room_type] * nights,
            "status": "confirmed",
            "rate_plan": "flexible",
            "special_requests": requests,
        }
        _BOOKINGS[ref] = booking
        return copy.deepcopy(booking)
