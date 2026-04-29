"""Tests for the BYO instrumentation init in tracing.py.

The module's `_init()` runs at import time. Tests force a fresh import via
`sys.modules.pop("tracing", None)` so each test exercises the real import
path under controlled env vars, mirroring the pattern in test_agent.py.
"""

from __future__ import annotations

import importlib
import io
import sys
from contextlib import redirect_stderr
from unittest.mock import patch

import pytest


def _reimport_tracing():
    sys.modules.pop("tracing", None)
    return importlib.import_module("tracing")


class TestTracingNoOpWithoutEnv:
    """Local dev / CI / pytest must not pull traceloop transitives or emit
    side effects. The Act-2-trace fix is a deploy-only concern."""

    def test_no_op_when_endpoint_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AMP_OTEL_ENDPOINT", raising=False)
        monkeypatch.delenv("AMP_AGENT_API_KEY", raising=False)
        sys.modules.pop("traceloop.sdk", None)
        sys.modules.pop("traceloop", None)
        try:
            _reimport_tracing()
            assert "traceloop.sdk" not in sys.modules, (
                "tracing imported traceloop.sdk despite AMP_OTEL_ENDPOINT being unset"
            )
        finally:
            sys.modules.pop("tracing", None)

    def test_no_op_when_endpoint_set_but_api_key_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AMP_OTEL_ENDPOINT", "http://collector:4318")
        monkeypatch.delenv("AMP_AGENT_API_KEY", raising=False)
        sys.modules.pop("traceloop.sdk", None)
        try:
            _reimport_tracing()
            assert "traceloop.sdk" not in sys.modules
        finally:
            sys.modules.pop("tracing", None)


class TestTracingInitsWhenEnvSet:
    """When both AMP env vars are present, Traceloop.init() must be called
    with the kwargs amp-instrumentation's bootstrap uses, so trace shape
    matches what the Agent Manager panel was rendering before opt-out."""

    def test_calls_traceloop_init_with_amp_kwargs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AMP_OTEL_ENDPOINT", "http://collector:4318")
        monkeypatch.setenv("AMP_AGENT_API_KEY", "test-key")
        monkeypatch.delenv("AMP_AGENT_VERSION", raising=False)

        with patch("traceloop.sdk.Traceloop.init") as mock_init:
            sys.modules.pop("tracing", None)
            try:
                _reimport_tracing()
            finally:
                sys.modules.pop("tracing", None)

            assert mock_init.called, "Traceloop.init was not invoked"
            kwargs = mock_init.call_args.kwargs
            assert kwargs["telemetry_enabled"] is False
            assert kwargs["api_endpoint"] == "http://collector:4318"
            assert kwargs["headers"] == {"x-amp-api-key": "test-key"}
            assert kwargs["resource_attributes"] == {}

    def test_includes_agent_version_resource_attr_when_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AMP_OTEL_ENDPOINT", "http://collector:4318")
        monkeypatch.setenv("AMP_AGENT_API_KEY", "test-key")
        monkeypatch.setenv("AMP_AGENT_VERSION", "v1.2.3")

        with patch("traceloop.sdk.Traceloop.init") as mock_init:
            sys.modules.pop("tracing", None)
            try:
                _reimport_tracing()
            finally:
                sys.modules.pop("tracing", None)

            assert mock_init.call_args.kwargs["resource_attributes"] == {
                "agent-manager/agent-version": "v1.2.3"
            }


class TestTracingInitFailureIsSwallowed:
    """A bad endpoint, network blip during deploy, or upstream traceloop bug
    must not crash agent boot. Better to ship thin traces than 502 the agent
    during the analyst briefing."""

    def test_init_exception_caught_and_logged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AMP_OTEL_ENDPOINT", "http://collector:4318")
        monkeypatch.setenv("AMP_AGENT_API_KEY", "test-key")

        buf = io.StringIO()
        with patch(
            "traceloop.sdk.Traceloop.init", side_effect=RuntimeError("simulated")
        ):
            with redirect_stderr(buf):
                sys.modules.pop("tracing", None)
                try:
                    _reimport_tracing()
                finally:
                    sys.modules.pop("tracing", None)

        assert "Traceloop.init failed" in buf.getvalue()
        assert "simulated" in buf.getvalue()


class TestMainImportOrder:
    """If main.py imports agent before tracing, the LangChain instrumentor
    wraps BaseCallbackManager.__init__ AFTER langchain_core has loaded — the
    wrap is applied to a class that's already been instantiated for runtime
    use, and Q10's nested LangGraph spans never appear. Static check guards
    against future refactors silently reordering imports."""

    def test_tracing_imported_before_agent(self) -> None:
        from pathlib import Path

        main_src = Path(__file__).parent.parent / "main.py"
        text = main_src.read_text()
        tracing_idx = text.find("import tracing")
        agent_idx = text.find("from agent import")
        assert tracing_idx > 0, "main.py is missing `import tracing`"
        assert agent_idx > 0, "main.py is missing `from agent import ...`"
        assert tracing_idx < agent_idx, (
            "main.py imports `agent` before `tracing` — instrumentor wrap will apply "
            "after langchain_core loads and Q10's nested spans will be lost"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
