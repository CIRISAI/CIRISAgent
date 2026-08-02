"""SSRF guard for every path that fetches a URL the agent did not choose.

Lifted verbatim from ``api_document.py``, where it was correct and had exactly
ONE caller (CIRISAgent#941). The paths that fetch model-authored URLs, and the
paths that fetch URLs off *inbound messages during observation*, all went
without it.

The observation-path ones are the reason this module exists rather than a
second copy of the checks: ``document_parser._download_file`` and
``base_vision`` fetch ``attachment.url`` from an inbound message — before any
thought exists, before any DMA runs, and therefore upstream of every gate a
task-scoped authorization design (#938) can impose. An attacker-supplied
attachment URL is fetched as a consequence of *receiving a message*. No
authorization scheme that begins at action selection reaches that; it has to be
stopped where the fetch happens.

What the guard does, all of it load-bearing:

* scheme allow-list — no ``file://``, ``gopher://``, ``dict://``
* explicit block-list for metadata hostnames across AWS/Azure/GCP/Alibaba
* **resolve first, then validate the resolved addresses** — checking the
  hostname alone is defeated by a name that resolves to 127.0.0.1, and checking
  after connect is defeated by DNS rebinding
* private / loopback / link-local rejection on every returned address, not just
  the first

``api_document`` keeps its own name for the function by re-exporting from here,
so its call site and tests are untouched.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BLOCKED_HOSTS: Set[str] = {
    "localhost",
    "127.0.0.1",
    "::1",
    "169.254.169.254",  # AWS/Azure/GCP metadata endpoint
    "metadata.google.internal",  # GCP metadata hostname
    "metadata",
    "100.100.100.200",  # Alibaba Cloud metadata
}


def validate_url_for_ssrf(url: str) -> Tuple[bool, Optional[str]]:
    """Validate URL is safe from SSRF attacks.

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_valid, resolved_ip) where resolved_ip is the validated IP
        address or None if validation failed.
    """
    try:
        parsed = urlparse(url)

        # Block non-http(s) schemes
        if parsed.scheme not in ("http", "https"):
            logger.warning(f"Blocked non-HTTP(S) URL scheme: {parsed.scheme}")
            return False, None

        # Block known dangerous hosts
        hostname = parsed.hostname
        if not hostname:
            logger.warning("URL missing hostname")
            return False, None

        hostname_lower = hostname.lower()
        if hostname_lower in BLOCKED_HOSTS:
            logger.warning(f"Blocked dangerous hostname: {hostname}")
            return False, None

        # Try to resolve hostname to IP and check for private/loopback ranges
        try:
            # Get IPv4 addresses for this hostname (prefer IPv4 for consistency)
            addr_info = socket.getaddrinfo(hostname, None, socket.AF_INET)
            if not addr_info:
                logger.warning(f"No IPv4 addresses found for hostname: {hostname}")
                return False, None

            # Use the first resolved IPv4 address (always a string from getaddrinfo)
            resolved_ip: str = str(addr_info[0][4][0])

            # Check all resolved IPs for safety
            for info in addr_info:
                ip_str = info[4][0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                    if ip.is_private or ip.is_loopback or ip.is_link_local:
                        logger.warning(f"Blocked private/loopback IP: {ip_str} for {hostname}")
                        return False, None
                    # Specifically block cloud metadata ranges
                    if isinstance(ip, ipaddress.IPv4Address):
                        if ip in ipaddress.ip_network("169.254.0.0/16"):
                            logger.warning(f"Blocked cloud metadata IP: {ip_str}")
                            return False, None
                except ValueError:
                    # Not a valid IP address
                    continue

            return True, resolved_ip
        except socket.gaierror:
            # DNS resolution failed - this is suspicious, block it
            logger.warning(f"Failed to resolve hostname: {hostname}")
            return False, None
        except Exception as e:
            # Any other error during resolution - block it
            logger.warning(f"Error validating hostname {hostname}: {e}")
            return False, None

    except Exception as e:
        logger.error(f"Error parsing URL for SSRF validation: {e}")
        return False, None


def assert_url_safe(url: str, context: str) -> None:
    """Raise ``ValueError`` unless ``url`` passes the SSRF guard.

    For call sites whose natural failure mode is an exception rather than a
    ``(bool, ip)`` pair. ``context`` names the fetch path so a blocked request
    is attributable in the log — "which of the four fetchers refused this" is
    the first question when one fires.
    """
    is_valid, _ = validate_url_for_ssrf(url)
    if not is_valid:
        logger.warning(f"[SSRF] {context}: refused to fetch {url!r}")
        raise ValueError(f"URL refused by SSRF guard ({context}): {url}")
