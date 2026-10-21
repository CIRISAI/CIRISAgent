"""Every URL fetch path the agent did not choose goes through the SSRF guard (#941).

The guard was already written and already correct. It had exactly ONE caller.
These tests pin the wiring, because the wiring is the whole fix — and pin it at
the call sites rather than only on the guard, since "the guard works" was
already true while three fetch paths bypassed it.

The two observation-path sites matter most: `document_parser._download_file`
and `base_vision` fetch `attachment.url` off an INBOUND message, so they run
before any thought exists and upstream of every gate #938 can impose. An
attacker-supplied attachment URL was fetched as a consequence of *receiving a
message*.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from ciris_engine.logic.utils.url_guard import BLOCKED_HOSTS, assert_url_safe, validate_url_for_ssrf

# Reachable-looking URLs that must be refused. Each is a distinct technique.
HOSTILE = [
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",  # AWS metadata
    "http://metadata.google.internal/computeMetadata/v1/",  # GCP metadata
    "http://100.100.100.200/latest/meta-data/",  # Alibaba metadata
    "http://localhost:8080/v1/system/shutdown",  # the agent's own API
    "http://127.0.0.1/",
    "file:///etc/passwd",  # scheme escape
    "gopher://127.0.0.1:6379/_FLUSHALL",  # protocol smuggling at redis
    "dict://127.0.0.1:11211/stat",
]


class TestGuard:
    @pytest.mark.parametrize("url", HOSTILE)
    def test_hostile_urls_are_refused(self, url: str) -> None:
        is_valid, _ = validate_url_for_ssrf(url)
        assert is_valid is False, f"{url} was allowed"

    def test_private_ranges_are_refused(self) -> None:
        for url in ("http://10.0.0.1/", "http://192.168.1.1/", "http://172.16.0.1/"):
            assert validate_url_for_ssrf(url)[0] is False

    def test_unresolvable_host_is_refused_not_allowed(self) -> None:
        """DNS failure is suspicious, and must not fall through to permit."""
        assert validate_url_for_ssrf("http://nonexistent.invalid./")[0] is False

    def test_a_hostname_resolving_to_loopback_is_refused(self) -> None:
        """The reason the guard resolves before validating.

        Checking the hostname string alone is defeated by a name that simply
        resolves to 127.0.0.1 — which an attacker controls for their own domain.
        """
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 0))]):
            assert validate_url_for_ssrf("http://evil.example.com/")[0] is False

    def test_metadata_ip_reached_via_dns_is_refused(self) -> None:
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("169.254.169.254", 0))]):
            assert validate_url_for_ssrf("http://harmless.example.com/")[0] is False

    def test_every_resolved_address_is_checked_not_just_the_first(self) -> None:
        """A host resolving to one public and one private address must be refused.

        Validating only addr_info[0] would let an attacker put a public address
        first and still have the connection race to the private one.
        """
        with patch(
            "socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 0)), (2, 1, 6, "", ("10.0.0.1", 0))],
        ):
            assert validate_url_for_ssrf("http://mixed.example.com/")[0] is False

    def test_a_public_host_is_allowed(self) -> None:
        """The guard has to still permit the legitimate case."""
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
            is_valid, ip = validate_url_for_ssrf("https://example.com/doc.pdf")
            assert is_valid is True
            assert ip == "93.184.216.34"

    def test_blocklist_covers_the_four_documented_clouds(self) -> None:
        for host in ("169.254.169.254", "metadata.google.internal", "100.100.100.200", "localhost"):
            assert host in BLOCKED_HOSTS


class TestAssertHelper:
    def test_raises_with_the_context_named(self) -> None:
        with pytest.raises(ValueError, match="curl"):
            assert_url_safe("http://169.254.169.254/", "curl")

    def test_passes_a_safe_url_through(self) -> None:
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
            assert_url_safe("https://example.com/", "curl")


class TestCallSitesAreWired:
    """The wiring, not the guard. This is what #941 was actually about."""

    @pytest.mark.asyncio
    async def test_document_parser_refuses_a_hostile_attachment(self) -> None:
        from ciris_engine.logic.adapters.document_parser import DocumentParser

        parser = DocumentParser()
        assert await parser._download_file("http://169.254.169.254/latest/meta-data/") is None

    @pytest.mark.asyncio
    async def test_curl_refuses_a_hostile_url(self) -> None:
        from ciris_engine.logic.adapters.api.api_tools import APIToolService

        svc = APIToolService()
        result = await svc._curl({"url": "http://169.254.169.254/latest/meta-data/"})
        assert "error" in result
        assert "SSRF" in result["error"]

    @pytest.mark.asyncio
    async def test_http_get_and_post_inherit_the_guard(self) -> None:
        """Both delegate to _curl, so neither may be a way around it."""
        from ciris_engine.logic.adapters.api.api_tools import APIToolService

        svc = APIToolService()
        for method in (svc._http_get, svc._http_post):
            result = await method({"url": "http://localhost:8080/v1/system/shutdown"})
            assert "SSRF" in result.get("error", "")

    def test_api_document_still_exports_the_original_name(self) -> None:
        """Its call site and tests were left untouched by the lift."""
        from ciris_engine.logic.adapters.api.api_document import (
            validate_url_for_ssrf as reexported,
        )

        assert reexported is validate_url_for_ssrf
