"""Utility helpers for CIRIS Engine."""

import logging

from .constants import (  # noqa:F401
    ACCORD_MODE,
    ACCORD_TEXT,
    ACCORD_TEXT_COMPRESSED,
    ENGINE_OVERVIEW_TEMPLATE,
    WA_USER_IDS,
    get_accord_text,
    get_localized_accord_text,
)
from .graphql_context_provider import GraphQLClient, GraphQLContextProvider  # noqa:F401
from .location_utils import (  # noqa:F401
    UserLocation,
    format_coordinates_for_trace,
    get_location_for_context_enrichment,
    get_user_location,
)
from .mdns_resolver import (  # noqa:F401
    DiscoveredService,
    close_mdns,
    discover_and_probe_hostnames,
    discover_services,
    resolve_local_hostname,
    resolve_url_hostname,
)
from .user_utils import extract_user_nick  # noqa:F401

logger = logging.getLogger(__name__)

__all__ = [
    "ACCORD_MODE",
    "ACCORD_TEXT",
    "ACCORD_TEXT_COMPRESSED",
    "get_accord_text",
    "get_localized_accord_text",
    "ENGINE_OVERVIEW_TEMPLATE",
    "WA_USER_IDS",
    "GraphQLClient",
    "GraphQLContextProvider",
    "extract_user_nick",
    "UserLocation",
    "get_user_location",
    "get_location_for_context_enrichment",
    "format_coordinates_for_trace",
    # mDNS resolver utilities
    "DiscoveredService",
    "close_mdns",
    "discover_and_probe_hostnames",
    "discover_services",
    "resolve_local_hostname",
    "resolve_url_hostname",
]
