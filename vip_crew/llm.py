"""LLM configuration with two modes (matches agent.py's _resolve_llm_config)."""

import os
from crewai import LLM


def get_llm() -> LLM:
    """Return crewai LLM, mode-gated on OPENAI_BASE_URL presence.

    BYO mode (no OPENAI_BASE_URL): direct OpenAI, normal Bearer auth.
    Governed mode (OPENAI_BASE_URL set): AM gateway with custom API-Key header.
    The AM gateway expects API-Key, not Authorization: Bearer — so we suppress
    the SDK's default header and add API-Key explicitly via default_headers.

    Env vars:
      - OPENAI_MODEL: model name (default: gpt-4o)
      - OPENAI_API_KEY: OpenAI key (BYO) or AM JWT (governed)
      - OPENAI_BASE_URL: AM gateway URL (governed mode only)
    """
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL")

    if base_url:
        return LLM(
            model=model,
            base_url=base_url,
            api_key="",
            default_headers={
                "API-Key": api_key,
                "Authorization": "",
            },
        )
    return LLM(model=model, api_key=api_key)
