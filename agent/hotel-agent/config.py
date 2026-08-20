"""Configuration for the hotel booking agent.

Every value below arrives as an environment variable. Nothing is read from a
committed file and nothing is hardcoded, so the same image runs in development
and production and as the customer-facing or the operations deployment.

The MCP and agent-identity variable names match what Agent Manager injects
when the corresponding Tool Configuration and Agent Identity are attached. If
you name things differently in the console, change the aliases here rather
than renaming anything in the console.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Model -----------------------------------------------------------
    openai_model: str = Field(default="gpt-4o", validation_alias="OPENAI_MODEL")
    # Governed mode: set by an AM LLM Service Provider. Presence is the mode gate.
    openai_url: str = Field(default="", validation_alias="OPENAI_URL")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    # BYO mode: direct to OpenAI, used only when openai_url is empty.
    openai_api_key_default: str = Field(default="", validation_alias="OPENAI_API_KEY_DEFAULT")

    # --- hotel-mcp Tool Configuration -------------------------------------
    hotel_mcp_url: str = Field(default="", validation_alias="HOTEL_MCP_URL")
    hotel_mcp_api_key: str = Field(default="", validation_alias="HOTEL_MCP_API_KEY")

    # --- Agent Identity ---------------------------------------------------
    # Injected when an Agent Identity is attached to this deployment. The
    # shipped build does not use these. See auth.py.
    agent_id_token_url: str = Field(default="", validation_alias="AGENT_ID_TOKEN_URL")
    agent_id_client_id: str = Field(default="", validation_alias="AGENT_ID_CLIENT_ID")
    agent_id_client_secret: str = Field(default="", validation_alias="AGENT_ID_CLIENT_SECRET")
    agent_id_scopes: str = Field(default="", validation_alias="AGENT_ID_SCOPES")

    # --- Behaviour flags --------------------------------------------------
    system_prompt_variant: str = Field(default="baseline", validation_alias="SYSTEM_PROMPT_VARIANT")
    # See mcp_client.py. Ships enabled. Read that module before changing it.
    legacy_date_compat: bool = Field(default=True, validation_alias="HOTEL_MCP_LEGACY_DATE_COMPAT")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def governed(self) -> bool:
        return bool(self.openai_url)

    @property
    def mcp_configured(self) -> bool:
        return bool(self.hotel_mcp_url)


settings = Settings()
