"""mDNS/Zeroconf utilities for local network discovery and hostname resolution.

Provides:
1. Hostname resolution - Resolve .local hostnames to IP addresses via mDNS
2. Service discovery - Find services by mDNS service type (e.g., _home-assistant._tcp.local.)
3. URL resolution - Resolve hostnames in URLs to IP addresses

Uses zeroconf library for reliable mDNS across all platforms (including Android
where socket.gethostbyname() doesn't support .local domains).

Usage:
    from ciris_engine.logic.utils.mdns_resolver import (
        resolve_local_hostname,
        resolve_url_hostname,
        discover_services,
    )

    # Resolve a .local hostname
    ip = await resolve_local_hostname("jetson.local")

    # Resolve hostname in URL
    url = await resolve_url_hostname("http://homeassistant.local:8123/api")

    # Discover services
    services = await discover_services("_home-assistant._tcp.local.")
"""

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

# Lazy-loaded zeroconf state
_zeroconf_available: Optional[bool] = None
_async_zeroconf: Optional[Any] = None
_zeroconf_lock = asyncio.Lock()


async def _get_async_zeroconf() -> Optional[Any]:
    """Get or create a shared AsyncZeroconf instance.

    Lazy-loads zeroconf to avoid blocking startup (import can take 60s+).
    Returns None if zeroconf is not available.
    """
    global _zeroconf_available, _async_zeroconf

    if _zeroconf_available is False:
        return None

    async with _zeroconf_lock:
        if _async_zeroconf is not None:
            return _async_zeroconf

        try:
            from zeroconf.asyncio import AsyncZeroconf

            _async_zeroconf = AsyncZeroconf()
            _zeroconf_available = True
            logger.info("[mDNS] AsyncZeroconf initialized for mDNS resolution")
            return _async_zeroconf
        except ImportError:
            _zeroconf_available = False
            logger.info("[mDNS] Zeroconf not available - falling back to socket resolution")
            return None
        except Exception as e:
            _zeroconf_available = False
            logger.warning(f"[mDNS] Failed to initialize Zeroconf: {e}")
            return None


async def close_mdns() -> None:
    """Close the shared mDNS resolver.

    Call this during shutdown to clean up resources.
    """
    global _async_zeroconf

    async with _zeroconf_lock:
        if _async_zeroconf is not None:
            try:
                await _async_zeroconf.async_close()
                logger.info("[mDNS] AsyncZeroconf closed")
            except Exception as e:
                logger.warning(f"[mDNS] Error closing Zeroconf: {e}")
            finally:
                _async_zeroconf = None


def _is_local_hostname(hostname: str) -> bool:
    """Check if hostname is an mDNS .local domain."""
    return hostname.lower().endswith(".local")


def _is_ip_address(hostname: str) -> bool:
    """Check if hostname is already an IP address."""
    try:
        socket.inet_aton(hostname)
        return True
    except socket.error:
        pass

    try:
        socket.inet_pton(socket.AF_INET6, hostname)
        return True
    except socket.error:
        pass

    return False


async def resolve_local_hostname(
    hostname: str,
    timeout: float = 3.0,
) -> str:
    """Resolve a .local hostname to its IP address via mDNS.

    Uses zeroconf if available for reliable mDNS resolution across platforms.
    Falls back to socket.gethostbyname() if zeroconf is not available.

    Args:
        hostname: The hostname to resolve (e.g., "jetson.local")
        timeout: Resolution timeout in seconds

    Returns:
        Resolved IP address, or original hostname if resolution fails
    """
    # Already an IP? Return as-is
    if _is_ip_address(hostname):
        return hostname

    # Non-.local hostname - use standard resolution
    if not _is_local_hostname(hostname):
        try:
            ip = socket.gethostbyname(hostname)
            logger.info(f"[mDNS] Resolved {hostname} -> {ip} via socket (non-.local)")
            return ip
        except socket.gaierror:
            logger.info(f"[mDNS] Failed to resolve non-.local hostname: {hostname}")
            return hostname

    # Try zeroconf for .local hostnames
    logger.info(f"[mDNS] Attempting zeroconf resolution for {hostname}...")
    azc = await _get_async_zeroconf()
    if azc is not None:
        try:
            resolved_ip = await _resolve_via_zeroconf(azc, hostname, timeout)
            if resolved_ip:
                logger.info(f"[mDNS] Resolved {hostname} -> {resolved_ip} via zeroconf")
                return resolved_ip
            else:
                logger.info(f"[mDNS] Zeroconf returned no result for {hostname}")
        except Exception as e:
            logger.warning(f"[mDNS] Zeroconf resolution failed for {hostname}: {e}")
    else:
        logger.warning("[mDNS] AsyncZeroconf not available")

    # Fall back to socket (works on some platforms)
    logger.info(f"[mDNS] Falling back to socket.gethostbyname for {hostname}")
    try:
        ip = socket.gethostbyname(hostname)
        logger.info(f"[mDNS] Resolved {hostname} -> {ip} via socket fallback")
        return ip
    except socket.gaierror as e:
        logger.warning(f"[mDNS] Socket resolution also failed for {hostname}: {e}")
        return hostname


async def _resolve_via_zeroconf(
    azc: Any,
    hostname: str,
    timeout: float,
) -> Optional[str]:
    """Resolve hostname using zeroconf's mDNS query.

    Uses ServiceInfo to resolve the hostname, which is the same approach
    that works reliably for Home Assistant discovery on Android.
    """
    # Run sync resolution in thread pool to avoid blocking event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _sync_resolve_via_serviceinfo,
        hostname,
        timeout,
    )


def _sync_resolve_via_serviceinfo(
    hostname: str,
    timeout: float,
) -> Optional[str]:
    """Synchronous hostname resolution via mDNS.

    Uses ServiceInfo.request() which is the same mechanism that
    HA adapter's get_service_info() uses internally. This is the
    standard zeroconf API for resolving addresses.
    """
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError:
        logger.info("[mDNS] Zeroconf not available")
        return None

    # Normalize hostname
    name = hostname.rstrip(".")

    logger.info(f"[mDNS] Resolving {hostname} via ServiceInfo.request()")

    zc: Any = None
    try:
        zc = Zeroconf()

        # Create a ServiceInfo for a dummy service on this host
        # This lets us use ServiceInfo.request() to resolve the hostname
        # The service type doesn't matter - we just want the address
        service_name = f"_ciris-probe._tcp.local."
        full_name = f"probe.{service_name}"

        # Try using ServiceInfo to resolve the server hostname
        # ServiceInfo.request() sends the appropriate mDNS queries
        info = ServiceInfo(
            service_name,
            full_name,
            server=f"{name}.",  # The hostname we want to resolve
            port=0,
        )

        # request() sends mDNS queries and waits for response
        # This is what get_service_info() uses internally
        timeout_ms = int(timeout * 1000)
        if info.request(zc, timeout_ms):
            addresses = info.parsed_addresses()
            if addresses:
                ip = addresses[0]
                logger.info(f"[mDNS] Resolved {hostname} -> {ip} via ServiceInfo")
                return ip

        # Fallback: Try direct A record lookup via get_service_info on the hostname
        # Some zeroconf versions support this
        try:
            # Try to resolve as if it's a service name
            direct_info = zc.get_service_info(
                "_device-info._tcp.local.",  # Standard device info service
                f"{name}._device-info._tcp.local.",
                timeout=int(timeout * 1000),
            )
            if direct_info:
                addresses = direct_info.parsed_addresses()
                if addresses:
                    resolved_ip: str = addresses[0]
                    logger.info(f"[mDNS] Resolved {hostname} -> {resolved_ip} via device-info")
                    return resolved_ip
        except Exception:
            pass

        logger.info(f"[mDNS] No response for {hostname} after {timeout}s")
        return None

    except Exception as e:
        logger.info(f"[mDNS] Resolution failed for {hostname}: {e}")
        import traceback
        logger.debug(f"[mDNS] Traceback: {traceback.format_exc()}")
        return None
    finally:
        if zc is not None:
            try:
                zc.close()
            except Exception:
                pass


async def resolve_url_hostname(
    url: str,
    timeout: float = 3.0,
) -> str:
    """Resolve the hostname in a URL to its IP address.

    Useful for ensuring reliable connectivity on platforms where mDNS
    hostname resolution is unreliable (e.g., Android browsers).

    Args:
        url: URL with potential .local hostname (e.g., http://homeassistant.local:8123)
        timeout: Resolution timeout in seconds

    Returns:
        URL with hostname replaced by IP if resolvable, original URL otherwise
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return url

        # Skip if already an IP
        if _is_ip_address(hostname):
            return url

        # Resolve hostname
        ip = await resolve_local_hostname(hostname, timeout)
        if ip == hostname:
            return url  # Resolution failed, return original

        # Reconstruct URL with IP
        netloc = ip
        if parsed.port:
            netloc = f"{ip}:{parsed.port}"
        if parsed.username:
            auth = parsed.username
            if parsed.password:
                auth = f"{auth}:{parsed.password}"
            netloc = f"{auth}@{netloc}"

        new_parsed = parsed._replace(netloc=netloc)
        return urlunparse(new_parsed)

    except Exception as e:
        logger.debug(f"[mDNS] URL resolution failed for {url}: {e}")
        return url


@dataclass
class DiscoveredService:
    """A service discovered via mDNS."""

    name: str
    service_type: str
    hostname: str
    ip_address: str
    port: int
    properties: Dict[str, Any] = field(default_factory=dict)

    @property
    def url(self) -> str:
        """HTTP URL for this service (using IP for reliability)."""
        return f"http://{self.ip_address}:{self.port}"


class _ServiceDiscoveryListener:
    """Listener for mDNS service discovery."""

    def __init__(self) -> None:
        self.services: List[DiscoveredService] = []

    def add_service(self, zc: Any, type_: str, name: str) -> None:
        """Handle discovered service."""
        info = zc.get_service_info(type_, name)
        if not info:
            logger.debug(f"[mDNS] Could not get service info for {name}")
            return

        addresses = info.parsed_addresses()
        if not addresses:
            logger.debug(f"[mDNS] Service {name} has no addresses")
            return

        ip_address = addresses[0]
        server = getattr(info, "server", None)
        hostname = server.rstrip(".") if server else ip_address

        # Parse properties
        properties: Dict[str, Any] = {}
        if info.properties:
            for key, value in info.properties.items():
                if isinstance(key, bytes):
                    key = key.decode("utf-8", errors="replace")
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="replace")
                properties[key] = value

        service = DiscoveredService(
            name=name.replace(f".{type_}", ""),
            service_type=type_,
            hostname=hostname,
            ip_address=ip_address,
            port=info.port,
            properties=properties,
        )
        self.services.append(service)
        logger.info(f"[mDNS] Discovered {service.name} at {service.url}")

    def remove_service(self, zc: Any, type_: str, name: str) -> None:
        """Handle removed service."""
        pass

    def update_service(self, zc: Any, type_: str, name: str) -> None:
        """Handle updated service."""
        pass


async def discover_services(
    service_type: str,
    timeout: float = 3.0,
) -> List[DiscoveredService]:
    """Discover services of a given type via mDNS.

    Args:
        service_type: mDNS service type (e.g., "_home-assistant._tcp.local.")
        timeout: Discovery timeout in seconds

    Returns:
        List of discovered services with resolved IP addresses
    """
    azc = await _get_async_zeroconf()
    if azc is None:
        logger.warning("[mDNS] Zeroconf not available for service discovery")
        return []

    try:
        from zeroconf import ServiceBrowser

        listener = _ServiceDiscoveryListener()
        # ServiceBrowser accepts any object with add_service/remove_service/update_service methods
        browser = ServiceBrowser(azc.zeroconf, service_type, listener)  # type: ignore[arg-type]

        # Wait for discovery
        await asyncio.sleep(timeout)

        # Cleanup
        browser.cancel()

        logger.info(f"[mDNS] Discovery complete: found {len(listener.services)} services")
        return listener.services

    except Exception as e:
        logger.error(f"[mDNS] Service discovery failed: {e}")
        return []


async def discover_and_probe_hostnames(
    hostnames: List[Tuple[str, int]],
    probe_endpoint: str = "/",
    timeout: float = 5.0,
    valid_status_codes: Tuple[int, ...] = (200, 401, 403),
) -> List[Dict[str, Any]]:
    """Discover services by probing a list of hostnames.

    This combines mDNS hostname resolution with HTTP probing to find
    services that don't advertise via mDNS service types (e.g., LLM servers).

    Args:
        hostnames: List of (hostname, port) tuples to probe
        probe_endpoint: HTTP endpoint to probe (e.g., "/api/tags" for Ollama)
        timeout: Total timeout for all probes
        valid_status_codes: HTTP status codes that indicate a valid service

    Returns:
        List of discovered services with resolved IP addresses
    """
    import aiohttp

    discovered: List[Dict[str, Any]] = []

    async def probe_host(hostname: str, port: int) -> Optional[Dict[str, Any]]:
        # First resolve hostname to IP via mDNS
        ip = await resolve_local_hostname(hostname, timeout=2.0)
        url = f"http://{ip}:{port}{probe_endpoint}"

        try:
            client_timeout = aiohttp.ClientTimeout(total=2.0)
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.get(url) as response:
                    if response.status in valid_status_codes:
                        return {
                            "hostname": hostname,
                            "ip": ip,
                            "port": port,
                            "url": f"http://{ip}:{port}",
                            "status": response.status,
                        }
        except Exception:
            pass
        return None

    # Probe all hostnames in parallel
    tasks = [probe_host(h, p) for h, p in hostnames]
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        results = []

    # Filter successful probes
    for result in results:
        if isinstance(result, dict):
            discovered.append(result)

    return discovered
