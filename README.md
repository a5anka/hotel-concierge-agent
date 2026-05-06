# Hotel Concierge — A WSO2 Agent Manager Sample

A complete sample agent for WSO2 Agent Manager. A hotel concierge built on
LangGraph + OpenAI, deployed via Agent Manager, observed through the platform's
trace panel, and consumed from a static landing page via a vanilla JS chat
widget.

Use this repo as a reference for:

- The **Platform-Hosted Agent** chat contract (`POST /chat`).
- **BYO vs governed** LLM credential modes (env-injection-driven, no code changes).
- **In-band readiness signaling** via a `READY` log line.
- A **framework-agnostic** integration: the same AM tracing + LLM governance
  applied to a CrewAI agent running outside AM (see [`vip_crew/`](vip_crew/)).

## Repo layout

```
.
├── main.py             Entry point. Agent Manager start command: `python main.py`.
├── agent.py            FastAPI app + LangGraph tool-calling loop. POST /chat keyed by session_id.
├── tools.py            3 hotel tools (room availability, room-service menu, local recs).
├── hotel_data.py       Single source of truth for rooms, menu, recommendations.
├── system_prompt.py    Concierge persona prompt.
├── requirements.txt    openai, fastapi, uvicorn, langgraph, pytest.
├── tests/              Unit tests (~1s).
├── web/
│   ├── index.html      "The Grand Meridian" landing page (Tailwind via CDN).
│   └── widget.js       Vanilla JS chat widget, ~250 lines, no build step.
└── vip_crew/           External CrewAI sample — see vip_crew/README.md.
```

## Chat interface (Platform-Hosted Agent contract)

```
POST /chat   (port 8000)
Request:  {"message": "string", "session_id": "string", "context": {}}
Response: {"response": "string"}
```

Conversation state is kept server-side, keyed by `session_id`. The client sends
one user message per turn; the server stitches the thread together. `context`
is accepted per the contract and logged into the trace, but is not currently
injected into the prompt.

## Run locally

Install deps:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run unit tests:
```bash
pytest tests/ -v
```

Start the agent:
```bash
export OPENAI_API_KEY_DEFAULT=sk-...    # local-dev key (BYO mode)
export OPENAI_MODEL=gpt-4o
python main.py
# → listening on http://localhost:8000
```

Smoke-test from another terminal:
```bash
curl -s http://localhost:8000/health

curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "Is the honeymoon suite available the first weekend in June?",
    "session_id": "smoke-1",
    "context": {}
  }' | jq

# Reuse the same session_id to continue the conversation:
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "What about for three nights?", "session_id": "smoke-1", "context": {}}' | jq
```

Serve the website (separate terminal — agent owns `:8000`):
```bash
cd web/
python3 -m http.server 5500
# → open http://localhost:5500
```

The committed default in `web/index.html` points
`window.GRAND_MERIDIAN_AGENT_URL` at `http://localhost:8000/chat`, so local dev
needs no edit. CORS on the agent defaults to `*`, so the cross-port request
works without further config.

## Deploy to Agent Manager

| Field             | Value                                                     |
|-------------------|-----------------------------------------------------------|
| Display Name      | `Grand Meridian Concierge`                                |
| GitHub Repository | `https://github.com/a5anka/hotel-concierge-agent`         |
| Branch            | `main`                                                    |
| App Path          | `.` (repo root)                                           |
| Language          | `Python`                                                  |
| Language Version  | `3.11`                                                    |
| Start Command     | `python main.py`                                          |
| Agent Interface   | `Chat Agent` (POST /chat, port 8000)                      |

Steps:

1. In Agent Manager: **Add Agent → Platform-Hosted Agent** and fill the form
   above.
2. Configure env vars:
   - `OPENAI_API_KEY_DEFAULT` (secret) — BYO key, used until an LLM Service
     Provider is configured at the agent level.
   - `OPENAI_MODEL=gpt-4o`
3. Deploy. Agent Manager assigns a public URL for the agent.
4. Point the widget at the deployed agent. Open the website with
   `?agent=<deployed-url>` once — the widget persists it to `localStorage`
   (key `gmAgentUrl`) and uses it on subsequent loads. `?agent=reset` clears it.

The agent listens on `8000`; the `Agent Interface: Chat Agent (POST /chat,
port 8000)` form field is what tells the gateway where to route. The Envoy
gateway in front of the agent handles CORS on the deployed path, so no
`CORS_ALLOW_ORIGINS` env var is needed.

## LLM credentials and governance modes

The agent supports two modes, switched purely by env injection. `OPENAI_URL`
presence is the mode gate — the two key slots have distinct purposes and
don't cross-fallback:

| Mode      | `OPENAI_URL` | `OPENAI_API_KEY` (AM-injected) | `OPENAI_API_KEY_DEFAULT` (BYO) | Outcome                              |
|-----------|--------------|--------------------------------|--------------------------------|--------------------------------------|
| BYO       | unset        | (ignored)                      | set                            | Direct OpenAI, no governance         |
| Governed  | set          | set                            | (ignored)                      | Routed via AM gateway with guardrails |

In governed mode the AM gateway expects the key on a custom `API-Key` header
(not `Authorization: Bearer`). The resolver passes `api_key=""` to suppress
the OpenAI SDK's default `Authorization` header, then sets `API-Key` via
`default_headers`. See `_resolve_llm_config()` in `agent.py` for the
implementation.

For production deploys, configure an **LLM Service Provider** at the org
level so all traffic flows through governed credentials. `GET /health` reports
the live mode:

```bash
curl -s http://localhost:8000/health
# → {"ok":true,"model":"gpt-4o","governed":false,"port":8000}
```

### Example: a compliance prompt decorator

Beyond credential routing, AM's LLM Service Provider can attach a **prompt
decorator** that augments every outbound LLM call without any change to agent
code. The concierge's governed deploy uses one such decorator to enforce a
pricing-disclosure policy:

> If your response mentions pricing, rates, or availability ANYWHERE, append
> exactly one line — and only one — at the very end of the entire response,
> AFTER any signature line: *"See our [terms and conditions](https://grandmeridian.example/terms)
> for confirmation of rates and availability."* Do not insert this line at the
> end of paragraphs, lists, or sections — only at the absolute end of the
> response. If this line already appears in the response, do NOT add another.

The decorator is configured in the AM admin UI (on the LLM Service Provider,
or as an agent-level override) and applies uniformly to every LLM call routed
through the gateway — including calls from the external CrewAI agent below.
The agent code has no awareness of it, which is the point: governance lives
at the platform, not in app code.

## Readiness signal

After a redeploy, the agent emits a recognizable startup line so callers can
confirm it's live before sending traffic. Watch the platform log panel (or
`kubectl logs`) for it:

```
READY {"ok": true, "model": "gpt-4o", "governed": true, "port": 8000}
```

The payload is identical to `/health` — same source of truth — so the
`governed` flag also confirms the env injection landed. If you see
`governed: false` after configuring an LLM Service Provider, the env-var
contract isn't reaching the agent.

## Demo questions

A walk-through of the agent's behavior end-to-end. These cover all three
response paths the agent can take: tool call, hardcoded prompt response, and
multi-tool trace.

1. Is the honeymoon suite available for the first weekend in June?
2. What's the price difference between a standard room and a deluxe suite?
3. Can I get a late checkout? *(no tool call — graceful degradation in the prompt)*
4. What's on the room service menu?
5. Do you have a vegetarian option for dinner?
6. What are the best restaurants within walking distance?
7. I have kids — is there anything nearby for families?
8. What time does the pool open? *(no tool call — graceful degradation)*
9. Can you book me a table at the rooftop bar? *(no tool call — graceful degradation)*
10. Compare a junior suite and the presidential suite for a 3-night stay *(multi-tool — rich trace)*

Question 10 triggers multiple `check_room_availability` tool calls in a
single turn — the trace panel shows each as a discrete OTEL GenAI span.

## External agent sample (CrewAI on a laptop)

[`vip_crew/`](vip_crew/) is a CrewAI agent that runs anywhere — laptop, VM,
another cloud — and gets Agent Manager's traces and LLM governance applied
without any code changes. The integration is one CLI prefix:

```bash
cd vip_crew
uv venv && uv sync

cp ../.env.local.example ../.env.local
# Fill in: OPENAI_BASE_URL, OPENAI_API_KEY, AMP_OTEL_ENDPOINT, AMP_AGENT_API_KEY

set -a; source ../.env.local; set +a

# Run it through the AM instrumentation wrapper:
uv run amp-instrument python crew.py VIP-042

# With pricing flag — response triggers the disclosure decorator from the governance section above:
uv run amp-instrument python crew.py VIP-203 --include-pricing
```

Available VIPs: `VIP-042` (Dr. Mei Tanaka), `VIP-101` (Marcus Chen),
`VIP-203` (Sofia Reyes).

The CrewAI code itself has no AM-specific imports — the only change from a
normal `python crew.py ...` invocation is the `amp-instrument` prefix. AM's
trace panel lights up with CrewAI spans (`crew.kickoff` →
`agent.execute_task` → LLM call), and any governance configured at the LLM
Service Provider level applies to those calls.

Full details in [`vip_crew/README.md`](vip_crew/README.md).
