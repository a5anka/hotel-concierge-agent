# Agent Manager Analyst Demo — The Grand Meridian Concierge

WSO2 Agent Manager analyst-briefing demo. A hotel concierge agent deployed via
Agent Manager, observed via the platform's testing UI, and consumed from a
hotel landing page through a vanilla JS chat widget.

## What's here

```
.
├── main.py             Entry point. Agent Manager start command: `python main.py`.
├── agent.py            FastAPI app + tool-calling loop. POST /chat keyed by session_id.
├── tools.py            3 hotel tools + dispatch table.
├── hotel_data.py       Single source of truth for rooms, menu, recommendations.
├── system_prompt.py    Concierge persona + locked graceful-degradation phrasing.
├── requirements.txt    openai, fastapi, uvicorn, pytest.
├── tests/test_tools.py 16 unit tests, ~1 second to run.
├── web/
│   ├── index.html      "The Grand Meridian" landing page (Tailwind via CDN).
│   └── widget.js       Vanilla JS chat widget, ~250 lines, no build step.
└── TODOS.md            Pre-flight tasks (hello-world deploy validation).
```

## Chat interface (Agent Manager standard)

```
POST /chat   (port 8000)
Request:  {"message": "string", "session_id": "string", "context": {}}
Response: {"response": "string"}
```

Conversation state is kept server-side, keyed by `session_id`. Send one user
message per turn; the server stitches the thread together. `context` is
accepted per the contract and logged into the trace, but not currently
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

Start the agent server:
```bash
export OPENAI_API_KEY=sk-...
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
    "session_id": "smoke-test-1",
    "context": {}
  }' | jq

# Reuse the same session_id to continue the conversation:
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "What about for three nights?", "session_id": "smoke-test-1", "context": {}}' | jq
```

Serve the hotel website (separate terminal — agent is already on `:8000`):
```bash
cd web/
python3 -m http.server 5500
# → open http://localhost:5500
```

`web/index.html` already points `window.GRAND_MERIDIAN_AGENT_URL` at
`http://localhost:8000/chat`, so no edit needed for local dev. CORS on the agent
defaults to `*`, so the cross-port request works without further config.

## Deploy to Agent Manager

Settings (matching the standard Platform-Hosted Agent form):

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

1. In Agent Manager: Add Agent → Platform-Hosted Agent → fill the form above.
2. Configure env vars:
   - `OPENAI_API_KEY` (secret)
   - `OPENAI_MODEL=gpt-4o`
   - `CORS_ALLOW_ORIGINS=*` (or the specific hotel website origin)
   - `PORT` is set automatically by Agent Manager.
3. Deploy. Endpoint will be exposed at the URL Agent Manager assigns.
4. Update `web/index.html`'s `window.GRAND_MERIDIAN_AGENT_URL` to that URL.

## The 10 scripted demo questions

These are the rehearsed questions for the analyst briefing. The agent must
answer all 10 cleanly before demo day.

1. Is the honeymoon suite available for the first weekend in June?
2. What's the price difference between a standard room and a deluxe suite?
3. Can I get a late checkout? (graceful degradation — no tool call)
4. What's on the room service menu?
5. Do you have a vegetarian option for dinner?
6. What are the best restaurants within walking distance?
7. I have kids — is there anything nearby for families?
8. What time does the pool open? (graceful degradation — no tool call)
9. Can you book me a table at the rooftop bar? (graceful degradation — no tool call)
10. Compare a junior suite and the presidential suite for a 3-night stay (multi-tool — trace climax)

Question 10 is the trace inspection question — it triggers multiple
`check_room_availability` tool calls, making Agent Manager's trace panel
visibly rich.

## Demo references

- **Design doc (locked decisions):** `~/.gstack/projects/agent-manager-analyst-demo/asankaab-unknown-design-20260428-161725.md`
- **Test plan:** `~/.gstack/projects/agent-manager-analyst-demo/asankaab-unknown-eng-review-test-plan-20260429-000000.md`
- **Visual reference (HTML wireframe sketch):** `~/.gstack/projects/agent-manager-analyst-demo/designs/grand-meridian-20260429/grand-meridian-sketch.html`
