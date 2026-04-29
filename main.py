"""Entry point matching the WSO2 Agent Manager start-command convention.

Agent Manager invokes `python main.py` after build. Local dev can also run
`python agent.py` directly — both end up serving the same FastAPI app.
"""

from __future__ import annotations

import os

import uvicorn

from agent import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
