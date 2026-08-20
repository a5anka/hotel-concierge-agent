"""FIXTURE INTEGRITY TESTS for the seeded Exercise 1 defect.

These tests do NOT assert that the agent is correct. They assert that it is
wrong in the specific, reproducible way the exercise depends on. If they start
failing, the defect has been "fixed" and Exercise 1 has no root cause left to
find. Read docs/facilitator-guide.md before changing anything here.

The defect has two halves, both in mcp_client.py:
  1. Outbound, ISO dates are rendered day-first as DD/MM/YYYY. hotel-mcp
     documents NN/NN/YYYY as MM/DD/YYYY, so the wrong date is written.
  2. Inbound, the requested date is echoed back into the acknowledgement, so
     the confirmation the guest sees matches what they asked for and the error
     is invisible in the reply.
"""

from __future__ import annotations

from datetime import datetime

from mcp_client import _apply_inbound_echo, _apply_outbound_compat, _to_pms_date


def _as_the_server_parses_it(slash: str) -> str:
    """hotel-mcp parses NN/NN/YYYY as MM/DD/YYYY. See mcp/hotel-mcp/server.py."""
    return datetime.strptime(slash, "%m/%d/%Y").date().isoformat()


class TestOutboundHalf:
    def test_iso_is_rendered_day_first(self) -> None:
        assert _to_pms_date("2026-04-06") == "06/04/2026"

    def test_the_written_date_is_wrong(self) -> None:
        # The whole exercise in one assertion: the model asked for 6 April and
        # the booking system stores 4 June.
        sent = _apply_outbound_compat({"booking_ref": "GM-4471", "check_in": "2026-04-06"})
        assert sent["check_in"] == "06/04/2026"
        assert _as_the_server_parses_it(sent["check_in"]) == "2026-06-04"

    def test_unambiguous_dates_survive_intact(self) -> None:
        # Day > 12 round-trips correctly, which is why casual testing misses this.
        sent = _apply_outbound_compat({"check_in": "2026-04-26"})
        assert _as_the_server_parses_it("04/26/2026") == "2026-04-26"
        assert sent["check_in"] == "26/04/2026"

    def test_non_date_arguments_untouched(self) -> None:
        args = {"booking_ref": "GM-4471", "nights": 3, "reason": "guest request"}
        assert _apply_outbound_compat(args) == args


class TestInboundHalf:
    def test_acknowledgement_shows_the_requested_date(self) -> None:
        server_said = {"status": "updated", "check_in": "2026-06-04", "check_out": "2026-06-07", "nights": 3}
        shown = _apply_inbound_echo("modify_booking", server_said, {"check_in": "2026-04-06"})
        assert shown["check_in"] == "2026-04-06"
        # check_out is recomputed too, so the acknowledgement is internally
        # consistent and gives the model nothing to notice.
        assert shown["check_out"] == "2026-04-09"

    def test_read_paths_are_not_echoed(self) -> None:
        # get_booking takes no check_in argument, so the read-back is truthful.
        # That contradiction is how a participant detects the bug at all.
        server_said = {"check_in": "2026-06-04"}
        assert _apply_inbound_echo("get_booking", server_said, {"booking_ref": "GM-4471"}) == server_said

    def test_echo_only_applies_to_write_tools(self) -> None:
        server_said = {"check_in": "2026-06-04"}
        out = _apply_inbound_echo("search_availability", server_said, {"check_in": "2026-04-06"})
        assert out["check_in"] == "2026-06-04"


class TestEndToEndIllusion:
    def test_reply_looks_right_and_record_is_wrong(self) -> None:
        model_chose = {"booking_ref": "GM-4471", "check_in": "2026-04-06", "nights": 3}

        on_the_wire = _apply_outbound_compat(model_chose)
        stored = _as_the_server_parses_it(on_the_wire["check_in"])
        server_ack = {"status": "updated", "check_in": stored, "check_out": "2026-06-07", "nights": 3}
        seen_by_model = _apply_inbound_echo("modify_booking", server_ack, model_chose)

        assert stored == "2026-06-04"                    # what the hotel will honour
        assert seen_by_model["check_in"] == "2026-04-06"  # what the guest is told
