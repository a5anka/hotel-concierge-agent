"""Hotel concierge agent — FastAPI service exposing POST /chat.

Stateless: the client sends the full message history with each request.
Tool-calling loop uses the OpenAI SDK. Defensive at every layer: rate limits
and timeouts return a friendly fallback message rather than 500-ing.
"""

from __future__ import annotations

import json
import logging
import os
import time
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
FRIENDLY_FALLBACK = (
    "I'm having trouble reaching our systems right now — could you try that again in a moment?"
)

# CORS_ALLOW_ORIGINS: comma-separated list of allowed origins for the public widget.
# Default "*" since the design picked a public scoped endpoint with no auth; tighten
# in Agent Manager env if a specific hotel website domain is known.
CORS_ALLOW_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()
]


client = OpenAI()
app = FastAPI(title="Grand Meridian Concierge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


class Message(BaseModel):
    role: str
    content: str | None = None


class ChatRequest(BaseModel):
    messages: list[Message] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: int
    model: str


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "model": OPENAI_MODEL}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    started = time.perf_counter()

    # Always prepend the system prompt; ignore any system message the client sent.
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in req.messages:
        if m.role == "system":
            continue
        if m.role not in ("user", "assistant", "tool"):
            continue
        messages.append({"role": m.role, "content": m.content or ""})

    if not any(m["role"] == "user" for m in messages):
        return ChatResponse(
            reply="How can I help you today?",
            tool_calls=[],
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=OPENAI_MODEL,
        )

    tool_calls_log: list[dict[str, Any]] = []

    try:
        for hop in range(MAX_TOOL_HOPS):
            completion = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
            choice = completion.choices[0]
            msg = choice.message

            if msg.tool_calls:
                # Append the assistant's tool-call message verbatim so the next
                # round can see what was requested.
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
                    name = tc.function.name
                    raw_args = tc.function.arguments or "{}"
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                    result = call_tool(name, args)
                    tool_calls_log.append({"name": name, "arguments": args, "result": result})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result),
                        }
                    )
                continue

            # No tool calls — this is the final answer.
            reply = (msg.content or "").strip()
            if not reply:
                reply = FRIENDLY_FALLBACK
            return ChatResponse(
                reply=reply,
                tool_calls=tool_calls_log,
                latency_ms=int((time.perf_counter() - started) * 1000),
                model=OPENAI_MODEL,
            )

        # Hit the hop budget without a final assistant message.
        log.warning("hop budget exceeded with %d tool calls", len(tool_calls_log))
        return ChatResponse(
            reply="I'm still working that out — could you give me a moment and ask again?",
            tool_calls=tool_calls_log,
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=OPENAI_MODEL,
        )

    except RateLimitError:
        log.warning("openai rate limit")
        return ChatResponse(
            reply=FRIENDLY_FALLBACK,
            tool_calls=tool_calls_log,
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=OPENAI_MODEL,
        )
    except APIError as e:
        log.warning("openai api error: %s", e)
        return ChatResponse(
            reply=FRIENDLY_FALLBACK,
            tool_calls=tool_calls_log,
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=OPENAI_MODEL,
        )
    except Exception as e:
        log.exception("unhandled error in /chat: %s", e)
        return ChatResponse(
            reply=FRIENDLY_FALLBACK,
            tool_calls=tool_calls_log,
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=OPENAI_MODEL,
        )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("agent:app", host="0.0.0.0", port=port, reload=False)
