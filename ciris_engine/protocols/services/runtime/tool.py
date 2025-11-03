"""Tool Service Protocol."""

from abc import abstractmethod
from typing import Any, Dict, List, Optional, Protocol

from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.types import JSONDict

# ToolParameters is a JSONDict for flexible parameter passing
ToolParameters = JSONDict

from ...runtime.base import ServiceProtocol


class ToolServiceProtocol(ServiceProtocol, Protocol):
    """Protocol for tool execution service."""

    @abstractmethod
    async def execute_tool(self, tool_name: str, parameters: ToolParameters) -> ToolExecutionResult:
        """Execute a tool with validated parameters.

        Note: parameters is a plain dict that has been validated against the tool's schema.
        The protocol accepts dict to allow flexibility in parameter types.
        """
        ...

    @abstractmethod
    async def list_tools(self) -> List[str]:
        """List available tools."""
        ...

    @abstractmethod
    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a specific tool."""
        ...

    @abstractmethod
    async def get_available_tools(self) -> List[str]:
        """Get list of all available tools.

        Returns:
            List of tool names that are currently available for execution.
        """
        ...

    @abstractmethod
    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool.

        Args:
            tool_name: Name of the tool to get info for.

        Returns:
            ToolInfo object if tool exists, None otherwise.
        """
        ...

    @abstractmethod
    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get detailed information about all available tools.

        Returns:
            List of ToolInfo objects for all available tools.
        """
        ...

    @abstractmethod
    async def validate_parameters(self, tool_name: str, parameters: ToolParameters) -> bool:
        """Validate parameters for a specific tool without executing it.

        Args:
            tool_name: Name of the tool to validate parameters for.
            parameters: Dictionary of parameters to validate.

        Returns:
            True if parameters are valid, False otherwise.
        """
        ...

    @abstractmethod
    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get the result of a previously executed tool by correlation ID.

        Args:
            correlation_id: Unique identifier for the tool execution.
            timeout: Maximum time to wait for result in seconds.

        Returns:
            ToolExecutionResult if found within timeout, None otherwise.
        """
        ...

    def get_service_metadata(self) -> Dict[str, Any]:
        """Get service metadata including data source information.

        Returns:
            Dict with metadata:
            {
                "data_source": bool,              # Whether tool accesses external data source
                "data_source_type": str,          # Type: sql, rest, hl7, file, api, etc.
                "contains_pii": bool,             # Whether source contains PII
                "gdpr_applicable": bool,          # Whether GDPR applies
                "connector_id": str,              # Unique connector identifier
                "data_retention_days": int,       # Data retention period (optional)
                "encryption_at_rest": bool,       # Whether data is encrypted (optional)
                "geographic_location": str,       # Data location for compliance (optional)
                "compliance_certifications": list # SOC2, HIPAA, etc. (optional)
            }

        Default implementation returns empty dict (not a data source).
        Tool services that access external data should override this method.

        Example:
            def get_service_metadata(self) -> Dict[str, Any]:
                return {
                    "data_source": True,
                    "data_source_type": "sql",
                    "contains_pii": True,
                    "gdpr_applicable": True,
                    "connector_id": self._connector_id,
                }
        """
        return {}  # Default: not a data source
