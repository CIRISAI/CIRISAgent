"""
CIRIS Modular Services - Pluggable service adapters.

This package contains optional service modules that can be dynamically loaded:
- mock_llm: Mock LLM service for testing
- reddit: Reddit communication adapter and tools
- geo_wisdom: Geographic navigation wise authority
- weather_wisdom: Weather forecasting wise authority
- sensor_wisdom: Home automation sensor integration
- external_data_sql: GDPR/DSAR SQL database tools

These modules are discovered at runtime via the service loader mechanism.
"""

__all__ = [
    "mock_llm",
    "reddit",
    "geo_wisdom",
    "weather_wisdom",
    "sensor_wisdom",
    "external_data_sql",
]
