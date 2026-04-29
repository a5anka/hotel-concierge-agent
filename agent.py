"""Hotel concierge agent — FastAPI service exposing POST /chat.

Implements the WSO2 Agent Manager standard chat interface:
  Request:  {message: string, session_id: string, context: JSON}
  Response: {response: string}

Conversation state is tracked server-side, keyed by session_id. The client
sends one user message per turn. Tool-calling loop uses the OpenAI SDK.
Defensive at every layer: rate limits and timeouts return a friendly fallback
message rather than 500-ing.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import APIError, OpenAI, RateLimitError
from pydantic import BaseModel, Field

from system_prompt import SYSTEM_PROMPT
from tools import TOOL_SCHEMAS, call_tool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("concierge")

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
MAX_TOOL_HOPS = 4
# Cap per-session message history to bound prompt size. A single turn can add
# 2-4 entries (user, optional assistant tool_calls, tool results, final reply),
# so 40 covers ~10 turns comfortably.
MAX_SESSION_MESSAGES = 40
FRIENDLY_FALLBACK = (
    "I'm having trouble reaching our systems right now — could you try that again in a moment?"
)

# In-memory session store. Single-process scope. Multi-replica deploys would
# need Redis or whatever Agent Manager exposes for shared state.
SESSIONS: dict[str, list[dict[str, Any]]] = {}
SESSION_LOCKS: dict[str, threading.Lock] = defaultdict(threading.Lock)

# CORS_ALLOW_ORIGINS: comma-separated list of allowed origins for the public widget.
# Default "*" since the design picked a public scoped endpoint with no auth; tighten
# in Agent Manager env if a specific hotel website domain is known.
CORS_ALLOW_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()
]


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Lazy so the module imports cleanly when OPENAI_API_KEY isn't set
    (CI, linters, local smoke tests of /health)."""
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


app = FastAPI(title="Grand Meridian Concierge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


class ChatRequest(BaseModel):
    message: str
    session_id: str
    context: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    response: str


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "model": OPENAI_MODEL}


def _truncate(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the most recent messages, but never split an assistant tool_calls
    message from its tool results (would produce an invalid prompt)."""
    if len(history) <= MAX_SESSION_MESSAGES:
        return history
    cut = len(history) - MAX_SESSION_MESSAGES
    while cut < len(history) and history[cut].get("role") == "tool":
        cut += 1
    return history[cut:]


def _run_loop(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Run the OpenAI tool-calling loop. Mutates `messages` with assistant
    and tool entries. Returns (final_reply, mutated_messages)."""
    for _ in range(MAX_TOOL_HOPS):
        completion = _get_client().chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        msg = completion.choices[0].message

        if msg.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = call_tool(tc.function.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    }
                )
            continue

        reply = (msg.content or "").strip()
        if reply:
            messages.append({"role": "assistant", "content": reply})
        return (reply or FRIENDLY_FALLBACK), messages

    log.warning("hop budget exceeded")
    return "I'm still working that out — could you give me a moment and ask again?", messages


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    started = time.perf_counter()

    if not req.message.strip():
        return ChatResponse(response="How can I help you today?")
    if not req.session_id:
        # Spec says session_id is required. If a client sends "", treat as a
        # fresh session every turn (no continuity) rather than 400-ing.
        log.warning("empty session_id; conversation continuity disabled for this turn")

    sid = req.session_id or "_anonymous_"

    with SESSION_LOCKS[sid]:
        history = SESSIONS.get(sid, [])
        if not history:
            history.append({"role": "system", "content": SYSTEM_PROMPT})
        history.append({"role": "user", "content": req.message})

        # `context` is accepted per the contract but not currently injected
        # into the prompt. Logged here so it surfaces in the trace.
        if req.context:
            log.info("session=%s context=%s", sid, json.dumps(req.context)[:500])

        try:
            reply, history = _run_loop(history)
        except RateLimitError:
            log.warning("session=%s openai rate limit", sid)
            reply = FRIENDLY_FALLBACK
        except APIError as e:
            log.warning("session=%s openai api error: %s", sid, e)
            reply = FRIENDLY_FALLBACK
        except Exception as e:
            log.exception("session=%s unhandled error in /chat: %s", sid, e)
            reply = FRIENDLY_FALLBACK

        SESSIONS[sid] = _truncate(history)

    log.info(
        "session=%s reply_chars=%d elapsed_ms=%d",
        sid,
        len(reply),
        int((time.perf_counter() - started) * 1000),
    )
    return ChatResponse(response=reply)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("agent:app", host="0.0.0.0", port=port, reload=False)
