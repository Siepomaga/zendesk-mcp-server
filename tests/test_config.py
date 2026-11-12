"""
Tests for environment-driven configuration.
"""
from pathlib import Path

import pytest

from zendesk_mcp_server.config import (
    DEFAULT_OAUTH_SCOPES,
    DEFAULT_REDIRECT_URI,
    ConfigurationError,
    OAuthSettings,
    default_token_file,
    load_settings,
)

SUBDOMAIN = "example"
CLIENT_ID = "zendesk-mcp-client"
EMAIL = "agent@example.com"
API_TOKEN = "test-api-token"

OAUTH_ENV = {"ZENDESK_SUBDOMAIN": SUBDOMAIN, "ZENDESK_CLIENT_ID": CLIENT_ID}
API_TOKEN_ENV = {
    "ZENDESK_SUBDOMAIN": SUBDOMAIN,
    "ZENDESK_EMAIL": EMAIL,
    "ZENDESK_API_KEY": API_TOKEN,
}


def test_oauth_selected_when_client_id_present():
    settings = load_settings(OAUTH_ENV)

    assert isinstance(settings, OAuthSettings)
    assert settings.client_id == CLIENT_ID
    assert settings.scopes == DEFAULT_OAUTH_SCOPES
    assert settings.redirect_uri == DEFAULT_REDIRECT_URI
    assert settings.token_file == default_token_file()
    assert settings.token_endpoint == "https://example.zendesk.com/oauth/tokens"
    assert (
        settings.authorize_endpoint
        == "https://example.zendesk.com/oauth/authorizations/new"
    )


def test_oauth_overrides_are_honoured(tmp_path):
    token_file = tmp_path / "custom-tokens.json"
    settings = load_settings(
        {
            **OAUTH_ENV,
            "ZENDESK_OAUTH_SCOPES": "tickets:read",
            "ZENDESK_TOKEN_FILE": str(token_file),
            "ZENDESK_OAUTH_REDIRECT_URI": "http://localhost:9999/cb",
        }
    )

    assert settings.scopes == "tickets:read"
    assert settings.token_file == token_file
    assert settings.redirect_uri == "http://localhost:9999/cb"


def test_default_scopes_cover_every_endpoint_the_server_calls():
    scopes = set(DEFAULT_OAUTH_SCOPES.split())

    assert scopes == {
        "tickets:read",
        "tickets:write",
        "ticket_attachments:read",
        "users:read",
        "hc:read",
    }


def test_leftover_api_token_variables_are_ignored_when_oauth_is_configured():
    settings = load_settings({**API_TOKEN_ENV, **OAUTH_ENV})

    assert isinstance(settings, OAuthSettings)


def test_api_token_only_config_is_rejected_with_migration_hint():
    """API tokens are retired; the error must say how to move to OAuth."""
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings(API_TOKEN_ENV)

    message = str(excinfo.value)
    assert "no longer supported" in message
    assert "ZENDESK_CLIENT_ID" in message
    assert "zendesk-auth" in message
    assert API_TOKEN not in message


def test_missing_subdomain_is_rejected():
    with pytest.raises(ConfigurationError, match="ZENDESK_SUBDOMAIN"):
        load_settings({"ZENDESK_CLIENT_ID": CLIENT_ID})


def test_missing_client_id_explains_how_to_set_up_oauth():
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings({"ZENDESK_SUBDOMAIN": SUBDOMAIN})

    message = str(excinfo.value)
    assert "ZENDESK_CLIENT_ID" in message
    assert "OAuth clients" in message
    assert "zendesk-auth" in message
    assert "no longer supported" not in message


@pytest.mark.parametrize("env", [{"ZENDESK_EMAIL": EMAIL}, {"ZENDESK_API_KEY": API_TOKEN}])
def test_partial_api_token_config_is_rejected(env):
    with pytest.raises(ConfigurationError, match="no longer supported"):
        load_settings({"ZENDESK_SUBDOMAIN": SUBDOMAIN, **env})


def test_blank_values_are_treated_as_unset():
    with pytest.raises(ConfigurationError):
        load_settings(
            {"ZENDESK_SUBDOMAIN": SUBDOMAIN, "ZENDESK_CLIENT_ID": "   ", "ZENDESK_EMAIL": ""}
        )


def test_default_token_file_lives_outside_the_project(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    path = default_token_file()

    assert path == tmp_path / "zendesk-mcp" / "tokens.json"
    assert Path.cwd() not in path.parents
