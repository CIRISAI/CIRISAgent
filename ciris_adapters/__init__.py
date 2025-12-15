"""
CIRIS Modular Services - Pluggable service adapters.

This package contains optional service modules that can be dynamically loaded:
- mock_llm: Mock LLM service for testing
- reddit: Reddit communication adapter and tools
- geo_wisdom: Geographic navigation wise authority
- weather_wisdom: Weather forecasting wise authority
- sensor_wisdom: Home automation sensor integration
- external_data_sql: GDPR/DSAR SQL database tools
- mcp_client: MCP client adapter for connecting to external MCP servers
- mcp_server: MCP server adapter for exposing CIRIS as an MCP server
- mcp_common: Shared utilities for MCP client and server
- ciris_covenant_metrics: Covenant compliance metrics for CIRISLens (opt-in required)

These modules are discovered at runtime via the service loader mechanism.
"""

__all__ = [
    "mock_llm",
    "reddit",
    "geo_wisdom",
    "weather_wisdom",
    "sensor_wisdom",
    "external_data_sql",
    "mcp_client",
    "mcp_server",
    "mcp_common",
    "ciris_covenant_metrics",
]
