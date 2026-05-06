# VIP Personalization Crew — External CrewAI Sample

A standalone CrewAI agent that runs on any host (laptop, VM, another cloud)
and gets Agent Manager's tracing and LLM governance applied without any
AM-specific code. The integration is one CLI prefix on the existing run
command.

Companion sample to the main concierge agent in this repo. The concierge is a
**Platform-Hosted Agent** (deployed *into* AM); this crew is an **external
agent** (deployed *outside* AM and observed *by* it). Same governance
guarantees, different deployment topology.

## One-time setup

```bash
cd vip_crew
uv venv && uv sync
```

VIPs available (sourced from `../hotel_data.py`): `VIP-042` (Dr. Mei Tanaka),
`VIP-101` (Marcus Chen), `VIP-203` (Sofia Reyes).

## Step 1 — Smoke test (crew alone, direct OpenAI)

Verify the crew runs end-to-end before plugging in Agent Manager.

```bash
cd vip_crew
unset OPENAI_BASE_URL                    # ensure no leftover AM gateway from .env.local
export OPENAI_API_KEY=sk-...
uv run python crew.py VIP-042
```

The four agents stream their reasoning to the terminal; a final welcome note
prints at the end. Should complete in ~60s.

## Step 2 — Full integration (Agent Manager gateway + tracing)

1. Fill `.env.local` (in the repo root, gitignored):

```bash
cp ../.env.local.example ../.env.local
# Edit: OPENAI_BASE_URL, OPENAI_API_KEY, AMP_OTEL_ENDPOINT, AMP_AGENT_API_KEY
```

2. Run with the AM instrumentation wrapper:

```bash
cd vip_crew
set -a; source ../.env.local; set +a

# Standard run:
uv run amp-instrument python crew.py VIP-042

# Pricing flag — response triggers the disclosure decorator described in the
# main README's governance section:
uv run amp-instrument python crew.py VIP-203 --include-pricing
```

The only change from Step 1's invocation is the `amp-instrument` prefix; the
CrewAI source files remain untouched. After each run, AM's trace panel shows
CrewAI-specific spans within a few seconds:

```
crew.kickoff → task.execute → agent.execute_task → LLM call
```

## Architecture

- `crew.py` — 4-agent sequential crew plus CLI entrypoint.
- `llm.py` — `crewai.LLM` configured for the AM gateway (`API-Key` header
  pattern). Mode-gated on `OPENAI_BASE_URL` presence, mirroring the main
  agent's governed/BYO split.
- `tools.py` — `lookup_guest_history` tool. Reads `VIP_GUESTS` from
  `../hotel_data.py` at runtime to keep a single source of truth.
- `pyproject.toml` — uv-managed CrewAI project plus `amp-instrumentation`.

**Zero AM-specific imports in any source file.** Instrumentation attaches at
process launch via the `amp-instrument` wrapper.
