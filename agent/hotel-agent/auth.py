"""Outbound authorisation for calls this agent makes to hotel-mcp.

+---------------------------------------------------------------------------+
|  THIS IS THE ONLY FILE YOU MAY CHANGE IN THE LEAST-PRIVILEGE EXERCISE.     |
|  Do not add tool allow-lists, do not branch on tool names, and do not      |
|  change the MCP server. Authorisation decisions belong to the platform;    |
|  this file only decides which credential the agent presents.               |
+---------------------------------------------------------------------------+

CONTRACT
--------
``mcp_auth_headers()`` returns the headers attached to every outbound MCP
request. mcp_client.py calls it once per tool invocation, so returning a
short-lived credential is fine as long as you handle refresh here.

WHAT THE CURRENT BUILD DOES
---------------------------
It presents a single static API key (``HOTEL_MCP_API_KEY``) that is the same
in every deployment of this code. The key is a property of the *deployment
configuration*, not of the agent, so the platform has no way to tell one
caller apart from another. Whatever that key is allowed to do, every agent
built from this repository is allowed to do.

WHAT THE PLATFORM MAKES AVAILABLE
---------------------------------
When an Agent Identity is attached to a deployment, Agent Manager injects a
client-credentials grant for that identity. config.py already reads it:

    settings.agent_id_token_url
    settings.agent_id_client_id
    settings.agent_id_client_secret
    settings.agent_id_scopes

Nothing in this build uses those values. ``httpx`` is already a dependency if
you need to make an HTTP call from here.
"""

from __future__ import annotations

import logging

from config import settings

log = logging.getLogger("hotel-agent.auth")

_WARNED = False


def mcp_auth_headers() -> dict[str, str]:
    """Headers to attach to every outbound hotel-mcp request.

    Called once per MCP tool invocation. Returning ``{}`` means the request is
    made anonymously, which hotel-mcp rejects when HOTEL_MCP_REQUIRE_AUTH is on.
    """
    global _WARNED
    if not settings.hotel_mcp_api_key:
        if not _WARNED:
            log.warning(
                "HOTEL_MCP_API_KEY is unset. MCP calls will be made without a "
                "credential and hotel-mcp will refuse them."
            )
            _WARNED = True
        return {}
    return {"API-Key": settings.hotel_mcp_api_key}


def describe_credential() -> dict[str, object]:
    """What credential this agent is presenting, surfaced on GET /health.

    Keep this honest when you change mcp_auth_headers(): an operator needs to
    be able to tell from outside the process which identity the agent is using.
    """
    return {
        "mode": "static-api-key",
        "credential_present": bool(settings.hotel_mcp_api_key),
        "agent_identity_available": bool(settings.agent_id_client_id),
        "agent_identity_in_use": False,
    }
