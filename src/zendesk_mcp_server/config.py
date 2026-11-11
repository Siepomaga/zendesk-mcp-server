"""
Configuration for the Zendesk MCP server.

The server authenticates with OAuth (authorization code flow with PKCE). Each
operator authorizes once with their own Zendesk login via ``zendesk-auth``, so
API calls carry their identity and are subject to the same permission checks as
the Zendesk UI.

API-token authentication (``ZENDESK_EMAIL`` + ``ZENDESK_API_KEY``) is not
supported: Zendesk blocks creating new API tokens from 2026-10-27 and stops
accepting all of them on 2027-04-30.

Credentials are validated here, before any client is constructed, so a
misconfiguration produces a readable message instead of a library traceback.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

logger = logging.getLogger(__name__)

# Scope identifiers required by the tools this server exposes:
#   tickets:read              tickets, comments, search
#   tickets:write             create/update tickets, add comments
#   ticket_attachments:read   fetch files attached to tickets
#   users:read                requester details and the signed-in user ("me")
#   hc:read                   Help Center articles for the knowledge base
#
# Zendesk accepts unrecognized scope strings when issuing a token but then
# rejects every request made with it as 403, so keep these exact.
DEFAULT_OAUTH_SCOPES = (
    "tickets:read tickets:write ticket_attachments:read users:read hc:read"
)

# Must match a redirect URL registered on the OAuth client in Admin Center.
DEFAULT_REDIRECT_URI = "http://localhost:4567/callback"

_MISSING_CLIENT_ID_MESSAGE = (
    "ZENDESK_CLIENT_ID is not set. Create a public OAuth client in Zendesk Admin "
    "Center (Apps and integrations > APIs > OAuth clients), set its identifier as "
    "ZENDESK_CLIENT_ID, then run `uv run zendesk-auth` once. See .env.example."
)

_API_TOKEN_UNSUPPORTED_MESSAGE = (
    "ZENDESK_EMAIL / ZENDESK_API_KEY are set, but API-token authentication is no "
    "longer supported (Zendesk retires API tokens on 2027-04-30). "
    + _MISSING_CLIENT_ID_MESSAGE
)


class ConfigurationError(RuntimeError):
    """Raised when the environment does not describe a usable configuration."""


@dataclass(frozen=True)
class OAuthSettings:
    """OAuth authorization-code-with-PKCE configuration."""

    subdomain: str
    client_id: str
    token_file: Path
    scopes: str = DEFAULT_OAUTH_SCOPES
    redirect_uri: str = DEFAULT_REDIRECT_URI

    @property
    def token_endpoint(self) -> str:
        return f"https://{self.subdomain}.zendesk.com/oauth/tokens"

    @property
    def authorize_endpoint(self) -> str:
        return f"https://{self.subdomain}.zendesk.com/oauth/authorizations/new"


Settings = OAuthSettings


def default_token_file() -> Path:
    """
    Location of the OAuth token store.

    Deliberately outside the project directory so tokens are never picked up by
    version control or a Docker build context.
    """
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    return base / "zendesk-mcp" / "tokens.json"


def _clean(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build settings from the environment."""
    env = os.environ if env is None else env

    subdomain = _clean(env.get("ZENDESK_SUBDOMAIN"))
    if not subdomain:
        raise ConfigurationError(
            "ZENDESK_SUBDOMAIN is not set. For https://acme.zendesk.com the "
            "subdomain is 'acme'."
        )

    client_id = _clean(env.get("ZENDESK_CLIENT_ID"))
    if not client_id:
        if _clean(env.get("ZENDESK_EMAIL")) or _clean(env.get("ZENDESK_API_KEY")):
            raise ConfigurationError(_API_TOKEN_UNSUPPORTED_MESSAGE)
        raise ConfigurationError(_MISSING_CLIENT_ID_MESSAGE)

    token_file = _clean(env.get("ZENDESK_TOKEN_FILE"))
    settings = OAuthSettings(
        subdomain=subdomain,
        client_id=client_id,
        token_file=Path(token_file).expanduser() if token_file else default_token_file(),
        scopes=_clean(env.get("ZENDESK_OAUTH_SCOPES")) or DEFAULT_OAUTH_SCOPES,
        redirect_uri=_clean(env.get("ZENDESK_OAUTH_REDIRECT_URI")) or DEFAULT_REDIRECT_URI,
    )
    logger.info(
        "Using Zendesk OAuth authentication (client_id=%s, token file=%s).",
        settings.client_id,
        settings.token_file,
    )
    return settings
