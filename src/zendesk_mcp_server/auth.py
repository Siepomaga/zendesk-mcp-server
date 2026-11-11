"""
Pluggable authentication for the Zendesk API.

The server authenticates with OAuth (see ``oauth.OAuthAuthProvider``). Zendesk
retired API tokens: no new ones can be created after 2026-10-27 and all of them
stop working on 2027-04-30, so API-token auth is not supported.

A provider is a ``requests`` auth callable, which is what makes rotating
credentials work: the callable runs on every request, so an expiring OAuth token
can be refreshed transparently rather than being baked into a header once at
construction time.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from requests.auth import AuthBase


@runtime_checkable
class AuthProvider(Protocol):
    """
    Supplies an ``Authorization`` header value for Zendesk API requests.

    Implementations are also ``requests`` auth callables so they can be attached
    to a session and applied per request.
    """

    def auth_header(self) -> str:
        """
        Return the current ``Authorization`` header value.

        Implementations that hold expiring credentials refresh them here, so
        callers can rely on the returned value being usable right now.
        """
        ...

    def __call__(self, request):  # pragma: no cover - protocol definition
        ...


class _HeaderAuthProvider(AuthBase):
    """Applies whatever ``auth_header()`` returns to an outgoing request."""

    def auth_header(self) -> str:
        raise NotImplementedError

    def __call__(self, request):
        request.headers["Authorization"] = self.auth_header()
        return request
