"""Initialize OpenTelemetry tracing for Agent Manager deploys.

Replaces the auto-instrumentation that runs when Agent Manager's
"Enable auto-instrumentation" toggle is ON. We disable that toggle
(PR wso2/agent-manager#392) because amp-instrumentation's pinned
opentelemetry-instrumentation-langchain crashes under wrapt 2.x.
By owning the init ourselves, our requirements.txt's wrapt<2 pin
becomes authoritative and the LangChain instrumentor wraps cleanly.

Mirrors amp_instrumentation._bootstrap.initialization exactly except:
  - Gates on AMP_OTEL_ENDPOINT presence (no-op locally and in CI
    instead of raising ConfigurationError)
  - Catches init failures and logs to stderr instead of propagating
    (better to boot with thin traces than to 502 the agent)

Must be imported in main.py BEFORE `import agent`, so wrap runs
before any langchain_core symbol loads.
"""

import os
import sys


def _init() -> None:
    endpoint = os.environ.get("AMP_OTEL_ENDPOINT")
    api_key = os.environ.get("AMP_AGENT_API_KEY")
    if not endpoint or not api_key:
        return

    os.environ.setdefault(
        "TRACELOOP_TRACE_CONTENT", os.environ.get("AMP_TRACE_CONTENT", "true")
    )
    os.environ.setdefault("TRACELOOP_METRICS_ENABLED", "false")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_INSECURE", "true")

    resource_attributes = {}
    if version := os.environ.get("AMP_AGENT_VERSION"):
        resource_attributes["agent-manager/agent-version"] = version

    try:
        from traceloop.sdk import Traceloop

        Traceloop.init(
            telemetry_enabled=False,
            api_endpoint=endpoint,
            headers={"x-amp-api-key": api_key},
            resource_attributes=resource_attributes,
        )
    except Exception as e:
        print(f"tracing: Traceloop.init failed: {e}", file=sys.stderr)


_init()
