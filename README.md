# Agent Manager Analyst Demo — The Grand Meridian Concierge

WSO2 Agent Manager analyst-briefing demo. A hotel concierge agent deployed via
Agent Manager, observed via the platform's testing UI, and consumed from a
hotel landing page through a vanilla JS chat widget.

## What's here

```
.
├── agent.py            FastAPI app exposing POST /chat. Stateless tool-calling loop.
├── tools.py            3 hotel tools + dispatch table.
├── hotel_data.py       Single source of truth for rooms, menu, recommendations.
├── system_prompt.py    Concierge persona + locked graceful-degradation phrasing.
├── requirements.txt    openai, fastapi, uvicorn, pytest.
├── tests/test_tools.py 13 unit tests, ~1 second to run.
├── web/
│   ├── index.html      "The Grand Meridian" landing page (Tailwind via CDN).
│   └── widget.js       Vanilla JS chat widget, ~250 lines, no build step.
└── TODOS.md            Pre-flight tasks (hello-world deploy validation).
```

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
python agent.py
# → listening on http://localhost:8000
```

Smoke-test from another terminal:
```bash
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Is the honeymoon suite available the first weekend in June?"}]}' | jq
```

Serve the hotel website (separate terminal):
```bash
cd web/
python3 -m http.server 8000
# Note: this conflicts with the agent on port 8000.
# Use a different port for the website:
python3 -m http.server 5500
# → open http://localhost:5500
```

If the agent is on `:8000` and the website on `:5500`, edit `web/index.html`'s
`window.GRAND_MERIDIAN_AGENT_URL` to point at `http://localhost:8000/chat`. CORS
on the agent defaults to `*` so this works locally without further config.

## Deploy to Agent Manager

1. **Pre-flight (see `TODOS.md`):** push a hello-world `print("hello")` agent
   first to verify Agent Manager's expected repo layout. This codebase assumes
   standard Python: `agent.py` as entry point, `requirements.txt` for deps.
2. Push this repo to GitHub.
3. In Agent Manager: Connect Repository → enter the GitHub URL.
4. Configure env vars in Agent Manager's UI:
   - `OPENAI_API_KEY` (secret)
   - `OPENAI_MODEL=gpt-4o`
   - `CORS_ALLOW_ORIGINS=*` (or the specific hotel website origin)
   - `PORT` is set automatically by Agent Manager.
5. Deploy. Endpoint will be exposed at the URL Agent Manager assigns.
6. Update `web/index.html`'s `window.GRAND_MERIDIAN_AGENT_URL` to that URL.

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
