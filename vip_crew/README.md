# Act 4: VIP Personalization Agent (External CrewAI)

Standalone CrewAI agent. Runs on the presenter's laptop; AM observes traces and governs LLM calls without owning the deployment. Demonstrates that AM is genuinely framework-agnostic and cloud-agnostic.

## One-time setup

```bash
cd vip_crew
uv venv && uv sync
```

## Tier 1 — Crew only, direct OpenAI (smoke test)

```bash
cd vip_crew
unset OPENAI_BASE_URL
export OPENAI_API_KEY=sk-...
uv run python crew.py VIP-042
```

The four agents stream their reasoning to the terminal. Final welcome note prints at the end.

VIPs available (from `../hotel_data.py`): `VIP-042` (Dr. Mei Tanaka), `VIP-101` (Marcus Chen), `VIP-203` (Sofia Reyes).

## Tier 2 — With AM gateway + tracing (demo path)

1. Fill `.env.local` (in repo root, gitignored):

```bash
cp ../.env.local.example ../.env.local
# Edit OPENAI_BASE_URL, OPENAI_API_KEY, AMP_OTEL_ENDPOINT, AMP_AGENT_API_KEY
```

2. Run with the wrapper:

```bash
cd vip_crew
set -a; source ../.env.local; set +a
uv run amp-instrument uv run python crew.py VIP-042
```

The demo line:
> "All I did was prefix my normal run command with `amp-instrument`. The agent has no AM-specific code."

## Demo cards

```bash
# Trigger 1: standard personalization
uv run amp-instrument uv run python crew.py VIP-042

# Trigger 2: governance trigger — Act 3 prompt decorator should fire
uv run amp-instrument uv run python crew.py VIP-203 --include-pricing
```

After each run, switch to AM trace panel. CrewAI-specific spans appear within ~5s:
`crew.kickoff` → `task.execute` → `agent.execute_task` → LLM call.

## Architecture

- `crew.py` — 4-agent sequential crew + CLI entrypoint
- `llm.py` — `crewai.LLM` configured for AM gateway (API-Key header pattern). Mode-gated on `OPENAI_BASE_URL` presence.
- `tools.py` — `lookup_guest_history` tool. Reads `VIP_GUESTS` from `../hotel_data.py` at runtime (single source of truth).
- `pyproject.toml` — uv-managed; crewai + crewai-tools + amp-instrumentation only.

**Zero AM-specific imports in any source file.** Instrumentation attaches at process launch via `amp-instrument`.

## Pre-demo checklist

- [ ] `localhost:22893/otel` reachable: `curl -sI http://localhost:22893/otel` returns any HTTP response
- [ ] `.env.local` filled with real AM gateway URL + JWT
- [ ] `uv run python crew.py VIP-042` (Tier 1) produces a coherent welcome note in <60s
- [ ] `uv run amp-instrument uv run python crew.py VIP-042` produces traces in AM panel within ~5s
- [ ] `--include-pricing` run shows Act 3 prompt decorator output in welcome note
- [ ] 5 consecutive runs without amp-instrument crashing

## Fallback if `amp-instrument` flakes

```bash
uv run opentelemetry-instrument \
  --traces_exporter otlp_proto_grpc \
  --exporter_otlp_endpoint http://localhost:22893 \
  python crew.py VIP-042
```
