"""
Constants for API adapter.

This module defines constants used across the API adapter to avoid
duplicate string literals and improve maintainability.
"""

# Error Messages
ERROR_ADAPTER_MANAGER_NOT_AVAILABLE = "Adapter manager not available"
ERROR_AUDIT_SERVICE_NOT_AVAILABLE = "Audit service not available"
ERROR_CONFIG_SERVICE_NOT_AVAILABLE = "Config service not available"
ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE = "Runtime control service not available"
ERROR_TIME_SERVICE_NOT_AVAILABLE = "Time service not available"
ERROR_RESOURCE_MONITOR_NOT_AVAILABLE = "Resource monitor service not available"
ERROR_MEMORY_SERVICE_NOT_AVAILABLE = "Memory service not available"
ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE = "Shutdown service not available"
ERROR_TELEMETRY_SERVICE_NOT_AVAILABLE = "Telemetry service not available"
ERROR_WISE_AUTHORITY_SERVICE_NOT_AVAILABLE = "Wise Authority service not available"

# Field Descriptions
DESC_RESULTS_OFFSET = "Results offset"
DESC_CONFIGURATION_KEY = "Configuration key"
DESC_AUDIT_ENTRY_ID = "Audit entry ID"
DESC_ADAPTER_ID = "Adapter ID"
DESC_ADAPTER_TYPE = "Adapter type"

# Service Unavailable Messages
# These are used when a service is not available in the app state
SERVICE_UNAVAILABLE_TEMPLATE = "{} service not available"

# Common Field Descriptions for Query Parameters
DESC_LIMIT = "Maximum results"
DESC_OFFSET = "Results offset"
DESC_START_TIME = "Start of time range"
DESC_END_TIME = "End of time range"
DESC_SEARCH_TEXT = "Search text"
DESC_HUMAN_READABLE_STATUS = "Human-readable status message"
DESC_CURRENT_COGNITIVE_STATE = "Current cognitive state"

# Common Field Descriptions for Path Parameters
DESC_ID_PARAM = "{} ID"
DESC_KEY_PARAM = "{} key"
DESC_NAME_PARAM = "{} name"

# Response Messages
MSG_NOT_FOUND = "{} '{}' not found"
MSG_DELETED = "{} '{}' deleted successfully"
MSG_UPDATED = "{} '{}' updated successfully"
MSG_CREATED = "{} '{}' created successfully"

# Permission Messages
MSG_INSUFFICIENT_PERMISSIONS = "Insufficient permissions. Requires {} role or higher."
MSG_SENSITIVE_CONFIG_PERMISSION = "Cannot {} sensitive config '{}' without {} role"
MSG_SYSTEM_CONFIG_PERMISSION = "Cannot modify system config '{}' without SYSTEM_ADMIN role"
MSG_WITHOUT_SYSTEM_ADMIN_ROLE = " without SYSTEM_ADMIN role"
