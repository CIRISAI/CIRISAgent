"""Tests for mDNS resolver module."""

from __future__ import annotations

import asyncio
import socket
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.utils.mdns_resolver import (
    DiscoveredService,
    _is_ip_address,
    _is_local_hostname,
    _ServiceDiscoveryListener,
    close_mdns,
    discover_and_probe_hostnames,
    discover_services,
    resolve_local_hostname,
    resolve_url_hostname,
)


class TestIsLocalHostname:
    """Tests for _is_local_hostname function."""

    def test_local_hostname_lowercase(self) -> None:
        """Test .local hostname detection (lowercase)."""
        assert _is_local_hostname("jetson.local") is True

    def test_local_hostname_uppercase(self) -> None:
        """Test .local hostname detection (uppercase)."""
        assert _is_local_hostname("JETSON.LOCAL") is True

    def test_local_hostname_mixed_case(self) -> None:
        """Test .local hostname detection (mixed case)."""
        assert _is_local_hostname("Jetson.Local") is True

    def test_non_local_hostname(self) -> None:
        """Test non-.local hostname."""
        assert _is_local_hostname("example.com") is False

    def test_localhost_not_local(self) -> None:
        """Test localhost is not a .local hostname."""
        assert _is_local_hostname("localhost") is False


class TestIsIpAddress:
    """Tests for _is_ip_address function."""

    def test_ipv4_address(self) -> None:
        """Test IPv4 address detection."""
        assert _is_ip_address("192.168.1.1") is True

    def test_ipv4_localhost(self) -> None:
        """Test localhost IPv4 detection."""
        assert _is_ip_address("127.0.0.1") is True

    def test_ipv6_address(self) -> None:
        """Test IPv6 address detection."""
        assert _is_ip_address("::1") is True

    def test_ipv6_full(self) -> None:
        """Test full IPv6 address detection."""
        assert _is_ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334") is True

    def test_hostname_not_ip(self) -> None:
        """Test hostname is not detected as IP."""
        assert _is_ip_address("jetson.local") is False

    def test_invalid_ip(self) -> None:
        """Test invalid IP format."""
        assert _is_ip_address("256.256.256.256") is False


class TestResolveLocalHostname:
    """Tests for resolve_local_hostname function."""

    @pytest.mark.asyncio
    async def test_returns_ip_unchanged(self) -> None:
        """Test that IP addresses are returned unchanged."""
        result = await resolve_local_hostname("192.168.1.100")
        assert result == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_returns_ipv6_unchanged(self) -> None:
        """Test that IPv6 addresses are returned unchanged."""
        result = await resolve_local_hostname("::1")
        assert result == "::1"

    @pytest.mark.asyncio
    async def test_non_local_uses_socket(self) -> None:
        """Test that non-.local hostnames use socket resolution."""
        with patch("socket.gethostbyname", return_value="93.184.216.34"):
            result = await resolve_local_hostname("example.com")
            assert result == "93.184.216.34"

    @pytest.mark.asyncio
    async def test_non_local_fallback_on_failure(self) -> None:
        """Test that failed non-.local resolution returns hostname."""
        with patch("socket.gethostbyname", side_effect=socket.gaierror):
            result = await resolve_local_hostname("nonexistent.example.com")
            assert result == "nonexistent.example.com"

    @pytest.mark.asyncio
    async def test_local_uses_zeroconf(self) -> None:
        """Test that .local hostnames attempt zeroconf resolution."""
        mock_azc = MagicMock()

        with patch(
            "ciris_engine.logic.utils.mdns_resolver._get_async_zeroconf",
            new_callable=AsyncMock,
            return_value=mock_azc,
        ), patch(
            "ciris_engine.logic.utils.mdns_resolver._resolve_via_zeroconf",
            new_callable=AsyncMock,
            return_value="192.168.50.203",
        ):
            result = await resolve_local_hostname("jetson.local")
            assert result == "192.168.50.203"

    @pytest.mark.asyncio
    async def test_local_fallback_to_socket(self) -> None:
        """Test that .local falls back to socket if zeroconf fails."""
        with patch(
            "ciris_engine.logic.utils.mdns_resolver._get_async_zeroconf",
            new_callable=AsyncMock,
            return_value=None,
        ), patch("socket.gethostbyname", return_value="192.168.1.100"):
            result = await resolve_local_hostname("test.local")
            assert result == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_local_returns_hostname_on_all_failures(self) -> None:
        """Test that hostname is returned if all resolution methods fail."""
        with patch(
            "ciris_engine.logic.utils.mdns_resolver._get_async_zeroconf",
            new_callable=AsyncMock,
            return_value=None,
        ), patch("socket.gethostbyname", side_effect=socket.gaierror):
            result = await resolve_local_hostname("unknown.local")
            assert result == "unknown.local"


class TestResolveUrlHostname:
    """Tests for resolve_url_hostname function."""

    @pytest.mark.asyncio
    async def test_url_with_ip_unchanged(self) -> None:
        """Test URL with IP address is returned unchanged."""
        result = await resolve_url_hostname("http://192.168.1.100:8080/api")
        assert result == "http://192.168.1.100:8080/api"

    @pytest.mark.asyncio
    async def test_resolves_hostname_in_url(self) -> None:
        """Test hostname in URL is resolved to IP."""
        with patch(
            "ciris_engine.logic.utils.mdns_resolver.resolve_local_hostname",
            new_callable=AsyncMock,
            return_value="192.168.50.203",
        ):
            result = await resolve_url_hostname("http://jetson.local:8080/v1/models")
            assert result == "http://192.168.50.203:8080/v1/models"

    @pytest.mark.asyncio
    async def test_preserves_path_and_query(self) -> None:
        """Test that path and query are preserved."""
        with patch(
            "ciris_engine.logic.utils.mdns_resolver.resolve_local_hostname",
            new_callable=AsyncMock,
            return_value="10.0.0.1",
        ):
            result = await resolve_url_hostname("http://server.local:3000/api?key=value")
            assert result == "http://10.0.0.1:3000/api?key=value"

    @pytest.mark.asyncio
    async def test_preserves_auth_in_url(self) -> None:
        """Test that authentication info is preserved."""
        with patch(
            "ciris_engine.logic.utils.mdns_resolver.resolve_local_hostname",
            new_callable=AsyncMock,
            return_value="10.0.0.1",
        ):
            result = await resolve_url_hostname("http://user:pass@server.local:3000/")
            assert "user:pass@" in result
            assert "10.0.0.1:3000" in result

    @pytest.mark.asyncio
    async def test_url_unchanged_on_resolution_failure(self) -> None:
        """Test URL is unchanged if resolution fails."""
        with patch(
            "ciris_engine.logic.utils.mdns_resolver.resolve_local_hostname",
            new_callable=AsyncMock,
            return_value="server.local",  # Returns hostname unchanged
        ):
            result = await resolve_url_hostname("http://server.local:8080/")
            assert result == "http://server.local:8080/"

    @pytest.mark.asyncio
    async def test_handles_malformed_url(self) -> None:
        """Test handling of malformed URLs."""
        result = await resolve_url_hostname("not-a-url")
        assert result == "not-a-url"


class TestDiscoveredService:
    """Tests for DiscoveredService dataclass."""

    def test_url_property(self) -> None:
        """Test URL property generation."""
        service = DiscoveredService(
            name="homeassistant",
            service_type="_home-assistant._tcp.local.",
            hostname="homeassistant.local",
            ip_address="192.168.1.50",
            port=8123,
            properties={},
        )
        assert service.url == "http://192.168.1.50:8123"

    def test_with_properties(self) -> None:
        """Test service with properties."""
        service = DiscoveredService(
            name="test",
            service_type="_test._tcp.local.",
            hostname="test.local",
            ip_address="10.0.0.1",
            port=1234,
            properties={"version": "1.0", "capabilities": "all"},
        )
        assert service.properties["version"] == "1.0"
        assert service.properties["capabilities"] == "all"


class TestServiceDiscoveryListener:
    """Tests for _ServiceDiscoveryListener class."""

    def test_add_service_with_valid_info(self) -> None:
        """Test adding a service with valid info."""
        listener = _ServiceDiscoveryListener()

        # Mock the zeroconf instance and service info
        mock_info = MagicMock()
        mock_info.parsed_addresses.return_value = ["192.168.1.100"]
        mock_info.server = "myservice.local."
        mock_info.port = 8080
        mock_info.properties = {b"key": b"value"}

        mock_zc = MagicMock()
        mock_zc.get_service_info.return_value = mock_info

        listener.add_service(mock_zc, "_test._tcp.local.", "myservice._test._tcp.local.")

        assert len(listener.services) == 1
        assert listener.services[0].ip_address == "192.168.1.100"
        assert listener.services[0].port == 8080
        assert listener.services[0].hostname == "myservice.local"

    def test_add_service_no_info(self) -> None:
        """Test adding a service when get_service_info returns None."""
        listener = _ServiceDiscoveryListener()

        mock_zc = MagicMock()
        mock_zc.get_service_info.return_value = None

        listener.add_service(mock_zc, "_test._tcp.local.", "noinfo._test._tcp.local.")

        assert len(listener.services) == 0

    def test_add_service_no_addresses(self) -> None:
        """Test adding a service with no addresses."""
        listener = _ServiceDiscoveryListener()

        mock_info = MagicMock()
        mock_info.parsed_addresses.return_value = []

        mock_zc = MagicMock()
        mock_zc.get_service_info.return_value = mock_info

        listener.add_service(mock_zc, "_test._tcp.local.", "noaddr._test._tcp.local.")

        assert len(listener.services) == 0

    def test_remove_service_no_op(self) -> None:
        """Test that remove_service is a no-op."""
        listener = _ServiceDiscoveryListener()
        # Should not raise
        listener.remove_service(MagicMock(), "_test._tcp.local.", "service")

    def test_update_service_no_op(self) -> None:
        """Test that update_service is a no-op."""
        listener = _ServiceDiscoveryListener()
        # Should not raise
        listener.update_service(MagicMock(), "_test._tcp.local.", "service")


class TestDiscoverServices:
    """Tests for discover_services function."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_zeroconf_unavailable(self) -> None:
        """Test that empty list is returned when zeroconf is not available."""
        with patch(
            "ciris_engine.logic.utils.mdns_resolver._get_async_zeroconf",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await discover_services("_test._tcp.local.", timeout=0.1)
            assert result == []

    @pytest.mark.asyncio
    async def test_discovers_services(self) -> None:
        """Test successful service discovery."""
        mock_azc = MagicMock()
        mock_azc.zeroconf = MagicMock()

        mock_browser = MagicMock()

        with patch(
            "ciris_engine.logic.utils.mdns_resolver._get_async_zeroconf",
            new_callable=AsyncMock,
            return_value=mock_azc,
        ), patch(
            "zeroconf.ServiceBrowser",
            return_value=mock_browser,
        ):
            # Use very short timeout for test
            result = await discover_services("_test._tcp.local.", timeout=0.1)

            # Browser should be cancelled
            mock_browser.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_exception(self) -> None:
        """Test that exceptions are handled gracefully."""
        mock_azc = MagicMock()
        mock_azc.zeroconf = MagicMock()

        with patch(
            "ciris_engine.logic.utils.mdns_resolver._get_async_zeroconf",
            new_callable=AsyncMock,
            return_value=mock_azc,
        ), patch(
            "zeroconf.ServiceBrowser",
            side_effect=Exception("Network error"),
        ):
            result = await discover_services("_test._tcp.local.", timeout=0.1)
            assert result == []


class TestDiscoverAndProbeHostnames:
    """Tests for discover_and_probe_hostnames function."""

    @pytest.mark.asyncio
    async def test_discovers_accessible_hosts(self) -> None:
        """Test discovering hosts that respond to probes."""
        with patch(
            "ciris_engine.logic.utils.mdns_resolver.resolve_local_hostname",
            new_callable=AsyncMock,
            return_value="192.168.1.100",
        ), patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = MagicMock()
            mock_response.status = 200

            mock_session = MagicMock()
            mock_get_cm = AsyncMock()
            mock_get_cm.__aenter__.return_value = mock_response
            mock_session.get.return_value = mock_get_cm
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await discover_and_probe_hostnames(
                [("server.local", 8080)],
                probe_endpoint="/health",
                timeout=1.0,
            )

            assert len(result) == 1
            assert result[0]["hostname"] == "server.local"
            assert result[0]["ip"] == "192.168.1.100"
            assert result[0]["port"] == 8080

    @pytest.mark.asyncio
    async def test_accepts_401_status(self) -> None:
        """Test that 401 status is accepted (indicates service exists)."""
        with patch(
            "ciris_engine.logic.utils.mdns_resolver.resolve_local_hostname",
            new_callable=AsyncMock,
            return_value="192.168.1.100",
        ), patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = MagicMock()
            mock_response.status = 401

            mock_session = MagicMock()
            mock_get_cm = AsyncMock()
            mock_get_cm.__aenter__.return_value = mock_response
            mock_session.get.return_value = mock_get_cm
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await discover_and_probe_hostnames(
                [("server.local", 8080)],
                timeout=1.0,
            )

            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_filters_failed_probes(self) -> None:
        """Test that failed probes are filtered out."""
        import aiohttp

        with patch(
            "ciris_engine.logic.utils.mdns_resolver.resolve_local_hostname",
            new_callable=AsyncMock,
            return_value="192.168.1.100",
        ), patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.get.side_effect = aiohttp.ClientError("Connection refused")
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await discover_and_probe_hostnames(
                [("unreachable.local", 8080)],
                timeout=1.0,
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_handles_timeout(self) -> None:
        """Test handling of overall timeout."""

        async def slow_resolve(hostname: str, timeout: float = 2.0) -> str:
            await asyncio.sleep(10)
            return "192.168.1.100"

        with patch(
            "ciris_engine.logic.utils.mdns_resolver.resolve_local_hostname",
            side_effect=slow_resolve,
        ):
            result = await discover_and_probe_hostnames(
                [("slow.local", 8080)],
                timeout=0.1,
            )

            # Should return empty due to timeout
            assert result == []


class TestCloseMdns:
    """Tests for close_mdns function."""

    @pytest.mark.asyncio
    async def test_closes_async_zeroconf(self) -> None:
        """Test that AsyncZeroconf is properly closed."""
        mock_azc = AsyncMock()

        with patch(
            "ciris_engine.logic.utils.mdns_resolver._async_zeroconf",
            mock_azc,
        ), patch(
            "ciris_engine.logic.utils.mdns_resolver._zeroconf_lock",
            asyncio.Lock(),
        ):
            # Need to patch at module level
            import ciris_engine.logic.utils.mdns_resolver as mdns

            original = mdns._async_zeroconf
            mdns._async_zeroconf = mock_azc

            try:
                await close_mdns()
                mock_azc.async_close.assert_called_once()
            finally:
                mdns._async_zeroconf = original

    @pytest.mark.asyncio
    async def test_handles_close_exception(self) -> None:
        """Test that exceptions during close are handled."""
        mock_azc = AsyncMock()
        mock_azc.async_close.side_effect = Exception("Close failed")

        import ciris_engine.logic.utils.mdns_resolver as mdns

        original = mdns._async_zeroconf
        mdns._async_zeroconf = mock_azc

        try:
            # Should not raise
            await close_mdns()
        finally:
            mdns._async_zeroconf = original

    @pytest.mark.asyncio
    async def test_no_op_when_not_initialized(self) -> None:
        """Test close is no-op when zeroconf not initialized."""
        import ciris_engine.logic.utils.mdns_resolver as mdns

        original = mdns._async_zeroconf
        mdns._async_zeroconf = None

        try:
            # Should not raise
            await close_mdns()
        finally:
            mdns._async_zeroconf = original
