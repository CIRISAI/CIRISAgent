"""
CIRIS Modular Services - Pluggable service adapters.

This package contains optional service modules that can be dynamically loaded.
Adapters are discovered at runtime via the service loader mechanism reading
each adapter's `manifest.json` — there is no canonical static list here.
The `__all__` below is intentionally limited to a small handful of widely-
referenced names; do not add adapter directories here just to "register"
them. New adapters become available the moment their manifest is loadable.
"""

__all__ = [
    "mock_llm",
    "reddit",
    "external_data_sql",
    "mcp_client",
    "mcp_server",
    "mcp_common",
    "ciris_accord_metrics",
]
