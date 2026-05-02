"""Minimal progress reporter for the demo.

Subscribes to crewai's event bus and prints one line per agent transition.
Replaces verbose=True (which dumps raw LLM frames) with a single status
stream that the analyst can read while the crew runs.
"""

import sys
from crewai.events import crewai_event_bus
from crewai.events.types.agent_events import (
    AgentExecutionStartedEvent,
    AgentExecutionCompletedEvent,
    AgentExecutionErrorEvent,
)


def _role(event) -> str:
    return (
        getattr(event, "agent_role", None)
        or getattr(getattr(event, "agent", None), "role", None)
        or "agent"
    )


def _line(symbol: str, role: str, msg: str = "") -> None:
    suffix = f" — {msg}" if msg else ""
    print(f"  {symbol} {role}{suffix}", flush=True)


@crewai_event_bus.on(AgentExecutionStartedEvent)
def _on_started(source, event):
    _line("→", _role(event), "working...")


@crewai_event_bus.on(AgentExecutionCompletedEvent)
def _on_completed(source, event):
    out = (event.output or "").strip().replace("\n", " ")
    if len(out) > 90:
        out = out[:87] + "..."
    _line("✓", _role(event), out)


@crewai_event_bus.on(AgentExecutionErrorEvent)
def _on_error(source, event):
    print(f"  ✗ {_role(event)} — error", file=sys.stderr, flush=True)
