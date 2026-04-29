"""Hotel concierge tools.

Each tool validates input defensively and returns either a result dict or
{"error": "<reason>"}. Tools never raise to the agent loop.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import tool

from hotel_data import (
    MENU,
    POOL_HOURS,
    RECOMMENDATIONS,
    ROOMS,
)

# Tool schemas for OpenAI tool-calling. Keep these in sync with the functions below.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "check_room_availability",
            "description": (
                "Check availability and price for hotel rooms. Use this whenever the "
                "guest asks about a specific room type, dates, prices, or comparisons."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "room_type": {
                        "type": "string",
                        "enum": list(ROOMS.keys()),
                        "description": (
                            "Which room type to check. Maps guest language to a key: "
                            "honeymoon suite -> honeymoon, deluxe suite -> deluxe, "
                            "standard room -> standard, junior suite -> junior, "
                            "presidential suite -> presidential."
                        ),
                    },
                    "check_in": {
                        "type": "string",
                        "description": "Check-in date in ISO format (YYYY-MM-DD) if known. Optional.",
                    },
                    "nights": {
                        "type": "integer",
                        "description": "Number of nights for the stay. Optional, defaults to 1.",
                    },
                },
                "required": ["room_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_room_service_menu",
            "description": (
                "Return the room service menu. Pass vegetarian_only=true if the guest "
                "asks for vegetarian options."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "vegetarian_only": {
                        "type": "boolean",
                        "description": "Filter to vegetarian items only.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_local_recommendations",
            "description": (
                "Return curated recommendations near the hotel by category."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": list(RECOMMENDATIONS.keys()),
                        "description": (
                            "Which kind of recommendations: restaurants, family, "
                            "nightlife, or outdoors."
                        ),
                    }
                },
                "required": ["category"],
            },
        },
    },
]


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_room_availability(
    room_type: str,
    check_in: str | None = None,
    nights: int | None = None,
) -> dict[str, Any]:
    """Check availability and price for hotel rooms.

    Use this whenever the guest asks about a specific room type, dates,
    prices, or comparisons.

    Args:
        room_type: Which room type to check. Must be one of:
            honeymoon, deluxe, standard, junior, presidential.
            Map guest language: "honeymoon suite" -> honeymoon,
            "deluxe suite" -> deluxe, "standard room" -> standard,
            "junior suite" -> junior, "presidential suite" -> presidential.
        check_in: Check-in date in ISO format (YYYY-MM-DD) if known. Optional.
        nights: Number of nights for the stay. Optional, defaults to 1.
    """
    if not isinstance(room_type, str) or room_type not in ROOMS:
        return {
            "error": f"Unknown room type. Available types: {', '.join(ROOMS.keys())}.",
        }
    if check_in is not None and not _ISO_DATE.match(check_in):
        return {
            "error": "Check-in date must be in YYYY-MM-DD format.",
        }
    n = 1 if nights is None else nights
    if not isinstance(n, int) or n < 1 or n > 30:
        return {"error": "Nights must be an integer between 1 and 30."}

    room = ROOMS[room_type]
    nightly = room["price_per_night_usd"]
    total = nightly * n
    return {
        "room_type": room_type,
        "name": room["name"],
        "price_per_night_usd": nightly,
        "nights": n,
        "total_usd": total,
        "size_sqft": room["size_sqft"],
        "description": room["description"],
        "available": True,
        "check_in": check_in,
    }


def get_room_service_menu(vegetarian_only: bool | None = None) -> dict[str, Any]:
    """Return the room service menu.

    Pass vegetarian_only=true if the guest asks for vegetarian options.

    Args:
        vegetarian_only: Filter to vegetarian items only. Optional, defaults to False.
    """
    veg = bool(vegetarian_only)
    items = [m for m in MENU if (not veg) or m["vegetarian"]]
    return {
        "items": items,
        "filtered": "vegetarian_only" if veg else "none",
        "count": len(items),
    }


def get_local_recommendations(category: str) -> dict[str, Any]:
    """Return curated recommendations near the hotel by category.

    Args:
        category: Which kind of recommendations. Must be one of:
            restaurants, family, nightlife, outdoors.
    """
    if not isinstance(category, str) or category not in RECOMMENDATIONS:
        return {
            "error": (
                f"No recommendations for that category. "
                f"Available: {', '.join(RECOMMENDATIONS.keys())}."
            )
        }
    return {
        "category": category,
        "recommendations": RECOMMENDATIONS[category],
        "count": len(RECOMMENDATIONS[category]),
    }


# Dispatch table used by the agent loop to execute a tool call by name.
TOOL_FUNCTIONS = {
    "check_room_availability": check_room_availability,
    "get_room_service_menu": get_room_service_menu,
    "get_local_recommendations": get_local_recommendations,
}


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool by name with caught exceptions returned as error dicts."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return fn(**arguments)
    except TypeError as e:
        return {"error": f"Invalid arguments for {name}: {e}"}
    except Exception as e:
        return {"error": f"{name} failed: {type(e).__name__}: {e}"}


# LangChain tool wrappers for the LangGraph agent. We wrap by calling tool(func)
# rather than using @tool as a decorator so the underlying functions remain
# directly callable (and the existing pytest suite keeps passing unchanged).
LANGCHAIN_TOOLS = [
    tool(check_room_availability),
    tool(get_room_service_menu),
    tool(get_local_recommendations),
]


# Re-export for convenience.
__all__ = [
    "TOOL_SCHEMAS",
    "TOOL_FUNCTIONS",
    "LANGCHAIN_TOOLS",
    "call_tool",
    "check_room_availability",
    "get_room_service_menu",
    "get_local_recommendations",
    "POOL_HOURS",
]
