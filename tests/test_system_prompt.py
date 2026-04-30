"""Tests for the system prompt variant selector.

The baseline prompt is demo-day load-bearing — its graceful-degradation
phrasing for Q3/Q8/Q9 is the only thing keeping those questions from
hitting tools they shouldn't, and the grounding guardrails are what
keeps the LLM from inventing menu items. The regression test below
guards those locked phrases.

The two broken variants exist for the Act 5 regression beat. They must
provably differ from the baseline on the load-bearing phrases, otherwise
the LLM-judge scores won't drop and the act collapses.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from hotel_data import LATE_CHECKOUT_POLICY, POOL_HOURS, RESERVATION_HANDOFF
from system_prompt import (
    BASELINE_PROMPT,
    BROKEN_BETA_1,
    BROKEN_BETA_2,
    select_prompt,
)


class TestSelectPrompt:
    """select_prompt() resolves variant names to prompt strings.

    Unknown values must fall back to baseline silently — a typo in the
    SYSTEM_PROMPT_VARIANT env var must not cause a boot crash mid-demo.
    """

    def test_default_variant_returns_baseline(self) -> None:
        assert select_prompt(None) is BASELINE_PROMPT
        assert select_prompt("baseline") is BASELINE_PROMPT

    def test_broken_variant_returns_beta_1(self) -> None:
        assert select_prompt("broken") is BROKEN_BETA_1

    def test_broken_2_variant_returns_beta_2(self) -> None:
        assert select_prompt("broken-2") is BROKEN_BETA_2

    def test_unknown_variant_falls_back_to_baseline(self) -> None:
        assert select_prompt("garbage") is BASELINE_PROMPT
        assert select_prompt("") is BASELINE_PROMPT
        assert select_prompt("   ") is BASELINE_PROMPT

    def test_variant_lookup_is_case_insensitive(self) -> None:
        assert select_prompt("BROKEN") is BROKEN_BETA_1
        assert select_prompt("Broken-2") is BROKEN_BETA_2
        assert select_prompt("BaSeLiNe") is BASELINE_PROMPT


class TestBaselineLocksLoadBearingPhrases:
    """REGRESSION GUARD.

    The baseline prompt's graceful-degradation phrasing is demo-day
    load-bearing. If a future refactor removes any of these strings,
    the corresponding scripted question silently breaks during the
    analyst briefing. This test fails loudly the moment that happens.
    """

    def test_baseline_contains_q3_late_checkout_policy(self) -> None:
        assert LATE_CHECKOUT_POLICY in BASELINE_PROMPT

    def test_baseline_contains_q8_pool_hours(self) -> None:
        assert POOL_HOURS in BASELINE_PROMPT

    def test_baseline_contains_q9_reservation_handoff(self) -> None:
        assert RESERVATION_HANDOFF in BASELINE_PROMPT

    def test_baseline_keeps_hardcoded_answer_guardrail(self) -> None:
        """The 'do NOT call a tool for these' phrasing is what keeps
        Q3/Q8/Q9 on the hardcoded path. Without it the LLM may invoke
        check_room_availability on a late-checkout question and
        produce an off-script answer."""
        assert "do NOT call a tool" in BASELINE_PROMPT

    def test_baseline_keeps_grounding_guardrail(self) -> None:
        """Without 'Never invent prices', groundedness scores drop on
        the rehearsal traces. That's exactly what the broken variants
        exploit, so the baseline must keep this line intact."""
        assert "Never invent prices" in BASELINE_PROMPT
        assert "Stay grounded in the tool data" in BASELINE_PROMPT


class TestBrokenVariantsStripGuardrails:
    """The broken variants must actually differ from the baseline on
    the load-bearing phrases. Otherwise the regression beat doesn't
    work — the LLM-judges grade the broken trace the same as the
    baseline and the side-by-side time-series shows no V."""

    def test_beta_1_strips_grounding_phrases(self) -> None:
        assert "Never invent prices" not in BROKEN_BETA_1
        assert "Stay grounded in the tool data" not in BROKEN_BETA_1

    def test_beta_1_strips_hardcoded_answer_block(self) -> None:
        assert "do NOT call a tool" not in BROKEN_BETA_1
        assert LATE_CHECKOUT_POLICY not in BROKEN_BETA_1
        assert RESERVATION_HANDOFF not in BROKEN_BETA_1

    def test_beta_2_strips_more_than_beta_1(self) -> None:
        """β2 is the more aggressive fallback. It should remove
        everything β1 does, and additionally weaken the tool-calling
        instructions so the LLM is more likely to wing it."""
        assert "Never invent prices" not in BROKEN_BETA_2
        assert "Stay grounded in the tool data" not in BROKEN_BETA_2
        assert "do NOT call a tool" not in BROKEN_BETA_2
        # β2 explicitly invites general knowledge — that's the lever
        # that drops groundedness on questions like Q4 (menu).
        assert "general knowledge" in BROKEN_BETA_2.lower()

    def test_variants_are_distinct(self) -> None:
        """Smoke test that nothing got accidentally duplicated."""
        assert BASELINE_PROMPT != BROKEN_BETA_1
        assert BROKEN_BETA_1 != BROKEN_BETA_2
        assert BASELINE_PROMPT != BROKEN_BETA_2


class TestModuleLevelEnvVarBinding:
    """The SYSTEM_PROMPT module constant must reflect the
    SYSTEM_PROMPT_VARIANT env var at import time. agent.py imports
    SYSTEM_PROMPT once at module load and bakes it into the agent —
    so this is the integration boundary that makes the live
    env-var-flip-and-redeploy demo beat work."""

    def test_unset_env_var_yields_baseline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SYSTEM_PROMPT_VARIANT", raising=False)
        sys.modules.pop("system_prompt", None)
        try:
            mod = importlib.import_module("system_prompt")
            assert mod.SYSTEM_PROMPT is mod.BASELINE_PROMPT
        finally:
            sys.modules.pop("system_prompt", None)

    def test_broken_env_var_yields_beta_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SYSTEM_PROMPT_VARIANT", "broken")
        sys.modules.pop("system_prompt", None)
        try:
            mod = importlib.import_module("system_prompt")
            assert mod.SYSTEM_PROMPT is mod.BROKEN_BETA_1
        finally:
            sys.modules.pop("system_prompt", None)

    def test_broken_2_env_var_yields_beta_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SYSTEM_PROMPT_VARIANT", "broken-2")
        sys.modules.pop("system_prompt", None)
        try:
            mod = importlib.import_module("system_prompt")
            assert mod.SYSTEM_PROMPT is mod.BROKEN_BETA_2
        finally:
            sys.modules.pop("system_prompt", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
