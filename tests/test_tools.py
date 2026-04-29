"""Unit tests for the 3 hotel concierge tools.

Covers happy path + invalid input + boundary values for each tool. These run
locally before each rehearsal and gate the deploy.
"""

from __future__ import annotations

import pytest

from tools import (
    check_room_availability,
    get_local_recommendations,
    get_room_service_menu,
)


class TestCheckRoomAvailability:
    def test_honeymoon_happy_path(self) -> None:
        r = check_room_availability(room_type="honeymoon")
        assert r["available"] is True
        assert r["price_per_night_usd"] == 420
        assert r["nights"] == 1
        assert r["total_usd"] == 420
        assert "Honeymoon Suite" == r["name"]

    def test_three_night_total(self) -> None:
        r = check_room_availability(room_type="presidential", nights=3)
        assert r["price_per_night_usd"] == 1200
        assert r["total_usd"] == 3600

    def test_iso_date_passthrough(self) -> None:
        r = check_room_availability(room_type="deluxe", check_in="2026-06-06", nights=2)
        assert r["check_in"] == "2026-06-06"
        assert r["total_usd"] == 680

    def test_unknown_room_type(self) -> None:
        r = check_room_availability(room_type="penthouse")
        assert "error" in r
        assert "Available types" in r["error"]

    def test_invalid_date_format(self) -> None:
        r = check_room_availability(room_type="standard", check_in="June 6")
        assert "error" in r
        assert "YYYY-MM-DD" in r["error"]

    def test_zero_nights_rejected(self) -> None:
        r = check_room_availability(room_type="standard", nights=0)
        assert "error" in r

    def test_excessive_nights_rejected(self) -> None:
        r = check_room_availability(room_type="standard", nights=100)
        assert "error" in r


class TestGetRoomServiceMenu:
    def test_full_menu(self) -> None:
        r = get_room_service_menu()
        assert r["count"] == 6
        assert r["filtered"] == "none"

    def test_vegetarian_filter(self) -> None:
        r = get_room_service_menu(vegetarian_only=True)
        assert r["count"] == 4
        assert r["filtered"] == "vegetarian_only"
        for item in r["items"]:
            assert item["vegetarian"] is True

    def test_falsy_filter_means_full_menu(self) -> None:
        r = get_room_service_menu(vegetarian_only=False)
        assert r["count"] == 6


class TestGetLocalRecommendations:
    def test_restaurants(self) -> None:
        r = get_local_recommendations(category="restaurants")
        assert r["count"] == 3
        assert all("walk_minutes" in rec for rec in r["recommendations"])

    def test_family(self) -> None:
        r = get_local_recommendations(category="family")
        assert r["count"] == 3

    def test_unknown_category(self) -> None:
        r = get_local_recommendations(category="elephants")
        assert "error" in r
        assert "Available" in r["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
