"""
Tests for how ZendeskClient applies an AuthProvider: the shared session handed
to zenpy, per-request credentials, and the attachment-fetch safety checks.
"""
import base64

import pytest
import responses

from zendesk_mcp_server.auth import AuthProvider, _HeaderAuthProvider
from zendesk_mcp_server.zendesk_client import ZendeskClient

SUBDOMAIN = "example"
BEARER = "Bearer static-token"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ATTACHMENT_URL = "https://example.zendesk.com/attachments/token/abc/?name=x.png"
CDN_URL = "https://example.zdusercontent.com/attachment/abc/x.png"


class StaticAuthProvider(_HeaderAuthProvider):
    def auth_header(self) -> str:
        return BEARER


class RotatingAuthProvider(_HeaderAuthProvider):
    """Stands in for an OAuth provider whose token changes between requests."""

    def __init__(self):
        self.calls = 0

    def auth_header(self) -> str:
        self.calls += 1
        return f"Bearer token-{self.calls}"


@pytest.fixture
def client():
    return ZendeskClient(subdomain=SUBDOMAIN, auth=StaticAuthProvider())


def test_header_providers_satisfy_the_protocol():
    assert isinstance(StaticAuthProvider(), AuthProvider)


def test_client_hands_zenpy_a_session_it_will_not_reauthenticate(client):
    assert client.session.authorized is True
    assert client.session.auth is client.auth
    # zenpy stores the session it was given on each sub-API's config.
    assert client.client.tickets.session is client.session


def test_provider_without_response_hook_adds_no_hook(client):
    assert client.session.hooks["response"] == []


@responses.activate
def test_rotating_credentials_are_applied_per_request():
    client = ZendeskClient(subdomain=SUBDOMAIN, auth=RotatingAuthProvider())
    for _ in range(2):
        responses.add(
            responses.GET,
            ATTACHMENT_URL,
            body=PNG_MAGIC,
            content_type="image/png",
            status=200,
        )

    client.get_ticket_attachment(ATTACHMENT_URL)
    client.get_ticket_attachment(ATTACHMENT_URL)

    sent = [call.request.headers["Authorization"] for call in responses.calls]
    assert sent == ["Bearer token-1", "Bearer token-2"]


@responses.activate
def test_attachment_redirect_to_cdn_drops_the_authorization_header(client):
    """
    Zendesk's CDN returns 403 when it receives an Authorization header, so the
    header must not survive the cross-origin redirect.
    """
    responses.add(
        responses.GET,
        ATTACHMENT_URL,
        status=302,
        headers={"Location": CDN_URL},
    )
    responses.add(
        responses.GET,
        CDN_URL,
        body=PNG_MAGIC + b"payload",
        content_type="image/png",
        status=200,
    )

    result = client.get_ticket_attachment(ATTACHMENT_URL)

    assert result["content_type"] == "image/png"
    first, second = responses.calls
    assert first.request.headers["Authorization"] == BEARER
    assert "Authorization" not in second.request.headers


@responses.activate
def test_get_tickets_sends_the_auth_header_and_query(client):
    responses.add(
        responses.GET,
        f"https://{SUBDOMAIN}.zendesk.com/api/v2/tickets.json",
        json={"tickets": [], "next_page": None},
    )

    client.get_tickets(page=2, per_page=10)

    request = responses.calls[0].request
    assert request.headers["Authorization"] == BEARER
    assert "page=2" in request.url and "per_page=10" in request.url


@responses.activate
def test_get_ticket_attachment_returns_base64_for_allowed_image(client):
    body = PNG_MAGIC + b"payload"
    responses.add(
        responses.GET,
        ATTACHMENT_URL,
        body=body,
        content_type="image/png",
        status=200,
    )

    result = client.get_ticket_attachment(ATTACHMENT_URL)

    assert result["kind"] == "image"
    assert result["content_type"] == "image/png"
    assert base64.b64decode(result["data"]) == body


def test_get_ticket_attachment_refuses_untrusted_hosts(client):
    """The bearer token must never be sent to a host outside Zendesk."""
    with pytest.raises(ValueError, match="untrusted host"):
        client.get_ticket_attachment("https://attacker.example.net/x.png")


@responses.activate
def test_get_ticket_attachment_rejects_disallowed_content_type(client):
    responses.add(
        responses.GET,
        ATTACHMENT_URL,
        body=b"<svg/>",
        content_type="image/svg+xml",
        status=200,
    )

    with pytest.raises(ValueError, match="is not allowed"):
        client.get_ticket_attachment(ATTACHMENT_URL)


@responses.activate
def test_get_ticket_attachment_rejects_spoofed_magic_bytes(client):
    responses.add(
        responses.GET,
        ATTACHMENT_URL,
        body=b"definitely-not-a-png",
        content_type="image/png",
        status=200,
    )

    with pytest.raises(ValueError, match="does not match declared content type"):
        client.get_ticket_attachment(ATTACHMENT_URL)
