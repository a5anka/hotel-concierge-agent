# TODOS

## Pre-flight: hello-world deploy validation

**What:** Push a 5-line `print("hello")` agent stub to a throwaway GitHub repo, connect it to Agent Manager, deploy. Verify the repo layout assumption (`agent.py` + `requirements.txt`, no Procfile/Dockerfile needed) before writing the real agent.

**Why:** Plan assumes "treat as standard Python: `agent.py` + `requirements.txt`." If Agent Manager expects a different layout (Procfile, Dockerfile, specific entry name, runtime.txt), you discover it Day 1 morning mid-build and waste hours debugging the deploy pipeline instead of building the agent.

**Pros:** ~20 min now removes the highest-blast-radius unknown in the plan. De-risks Day 1 morning.

**Cons:** ~20 min added if redundant. If user already knows Agent Manager's expected layout from prior work, this is unnecessary.

**Context:** Agent Manager builds from GitHub repo. Standard Python convention is `requirements.txt` + named entry point (`agent.py` / `main.py` / `app.py`). Platform-specific layouts (Heroku Procfile, Cloud Run Dockerfile, fly.io fly.toml) differ. Unclear which family Agent Manager belongs to. Verifying with a stub keeps the cost of being wrong low.

**Depends on / blocked by:** Agent Manager access, ability to create a throwaway GitHub repo.

**When to do this:** Before Day 1 morning build, OR the moment Day 1 morning's real-agent deploy fails for a structural reason.
