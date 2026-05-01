"""Hotel concierge agent — FastAPI service exposing POST /chat.

Implements the WSO2 Agent Manager standard chat interface:
  Request:  {message: string, session_id: string, context: JSON}
  Response: {response: string}

Conversation state is tracked server-side, keyed by session_id. The client
sends one user message per turn. Tool-calling runs through LangGraph's
prebuilt create_react_agent so each LLM call and tool call is a discrete
OTEL GenAI semconv span in Agent Manager's trace panel.
Defensive at every layer: rate limits, recursion-limit exhaustion, and
unhandled exceptions return a friendly fallback rather than 500-ing.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import create_react_agent
from openai import APIError, RateLimitError
from pydantic import BaseModel

from system_prompt import SYSTEM_PROMPT
from tools import LANGCHAIN_TOOLS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("concierge")

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
# Cap per-session message history to bound prompt size. A single turn can add
# 2-4 entries (user, optional AI tool_calls, tool results, final reply),
# so 40 covers ~10 turns comfortably.
MAX_SESSION_MESSAGES = 40
FRIENDLY_FALLBACK = (
    "I'm having trouble reaching our systems right now — could you try that again in a moment?"
)

# In-memory session store. Single-process scope. Multi-replica deploys would
# need Redis or whatever Agent Manager exposes for shared state.
SESSIONS: dict[str, list[BaseMessage]] = {}
SESSION_LOCKS: dict[str, threading.Lock] = defaultdict(threading.Lock)

# CORS_ALLOW_ORIGINS: comma-separated list of allowed origins for the public widget.
CORS_ALLOW_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()
]


_agent = None


def _resolve_llm_config() -> dict[str, Any]:
    """OPENAI_URL presence is the mode gate. In governed mode, the AM gateway
    expects the API key on a custom `API-Key` header (not `Authorization: Bearer`),
    so we suppress the SDK's default Authorization header and set API-Key
    explicitly — this matches Agent Manager's documented sample. In BYO mode,
    we use OPENAI_API_KEY_DEFAULT against OpenAI directly."""
    base_url = os.getenv("OPENAI_URL")
    if base_url:
        return {
            "base_url": base_url,
            "api_key": "",
            "default_headers": {
                "API-Key": os.getenv("OPENAI_API_KEY", ""),
                "Authorization": "",
            },
        }
    return {"api_key": os.getenv("OPENAI_API_KEY_DEFAULT")}


def _get_agent():
    """Lazy so the module imports cleanly with no keys set (CI, linters,
    /health smoke tests). ChatOpenAI reads credentials on first instantiation,
    not at import time."""
    global _agent
    if _agent is None:
        llm = ChatOpenAI(model=OPENAI_MODEL, **_resolve_llm_config())
        _agent = create_react_agent(llm, tools=LANGCHAIN_TOOLS, prompt=SYSTEM_PROMPT)
    return _agent


def _ready_payload() -> dict[str, Any]:
    """Single source of truth for /health and the startup log line. The
    `governed` flag makes the live LLM mode visible without reading the
    trace — useful for /health and as a startup signal in platform logs."""
    return {
        "ok": True,
        "model": OPENAI_MODEL,
        "governed": bool(os.environ.get("OPENAI_URL")),
        "port": int(os.environ.get("PORT", "8000")),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Emit a recognizable startup line so callers can grep platform logs to
    confirm the agent is listening before invoking. Agent Manager's Workload
    schema does not expose readiness probes (verified against ComponentType
    `agent-api` and the available Traits), so this log line is the only
    in-band readiness signal during the cold-start window."""
    log.info("READY %s", json.dumps(_ready_payload()))
    yield


app = FastAPI(title="Grand Meridian Concierge", lifespan=lifespan)
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
    return _ready_payload()


def _truncate(history: list[BaseMessage]) -> list[BaseMessage]:
    """Keep the most recent messages, but never start the slice on a
    ToolMessage (would be orphaned without its preceding AIMessage tool_calls
    and produce an invalid LangChain prompt)."""
    if len(history) <= MAX_SESSION_MESSAGES:
        return history
    cut = len(history) - MAX_SESSION_MESSAGES
    while cut < len(history) and isinstance(history[cut], ToolMessage):
        cut += 1
    return history[cut:]


def _final_text(messages: list[BaseMessage]) -> str:
    """Pull the last AIMessage content from the agent's returned message list."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, str):
                return content.strip()
            # content can be a list of content blocks for some providers; flatten.
            if isinstance(content, list):
                parts = [
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                ]
                return "".join(parts).strip()
    return ""


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    started = time.perf_counter()

    if not req.message.strip():
        return ChatResponse(response="How can I help you today?")
    if not req.session_id:
        log.warning("empty session_id; conversation continuity disabled for this turn")

    sid = req.session_id or "_anonymous_"

    with SESSION_LOCKS[sid]:
        history = SESSIONS.get(sid, [])
        history = history + [HumanMessage(content=req.message)]

        # `context` is accepted per the contract but not currently injected
        # into the prompt. Logged here so it surfaces in the trace.
        if req.context:
            log.info("session=%s context=%s", sid, json.dumps(req.context)[:500])

        try:
            result = _get_agent().invoke(
                {"messages": history},
                config={
                    "configurable": {"thread_id": sid},
                    "metadata": {"session_id": sid},
                },
            )
            history = result["messages"]
            reply = _final_text(history) or FRIENDLY_FALLBACK
        except GraphRecursionError:
            log.warning("session=%s langgraph recursion limit exceeded", sid)
            reply = "I'm still working that out — could you give me a moment and ask again?"
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
