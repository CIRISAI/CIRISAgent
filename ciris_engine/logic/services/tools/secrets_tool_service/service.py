"""
Secrets Tool Service - Provides secrets management tools.

Implements ToolService protocol to expose RECALL_SECRET and UPDATE_SECRETS_FILTER tools.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services import ToolService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolInfo,
    ToolParameterSchema,
    ToolResult,
)
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.core.secrets import SecretContext
from ciris_engine.schemas.types import ToolParameters

logger = logging.getLogger(__name__)


class SecretsToolService(BaseService, ToolService):
    """Service providing secrets management tools."""

    def __init__(self, secrets_service: SecretsService, time_service: TimeServiceProtocol) -> None:
        """Initialize with secrets service and time service."""
        super().__init__(time_service=time_service)
        self.secrets_service = secrets_service
        self.adapter_name = "secrets"

        # v1.4.3 metrics tracking
        self._secrets_retrieved = 0
        self._secrets_stored = 0
        self._metrics_tracking: Dict[str, float] = {}  # For custom metric tracking
        self._tool_executions = 0
        self._tool_failures = 0

    def _track_metric(self, metric_name: str, default: float = 0.0) -> float:
        """Track a metric with default value."""
        return self._metrics_tracking.get(metric_name, default)

    def get_service_type(self) -> ServiceType:
        """Get service type."""
        return ServiceType.TOOL

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return ["recall_secret", "update_secrets_filter", "self_help"]

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are available."""
        return self.secrets_service is not None

    def _register_dependencies(self) -> None:
        """Register service dependencies."""
        super()._register_dependencies()
        self._dependencies.add("SecretsService")

    async def is_healthy(self) -> bool:
        """Check if service is healthy.

        SecretsToolService is stateless and always healthy if instantiated.
        """
        return True

    async def execute_tool(self, tool_name: str, parameters: ToolParameters) -> ToolExecutionResult:
        """Execute a tool and return the result."""
        self._track_request()  # Track the tool execution
        self._tool_executions += 1

        if tool_name == "recall_secret":
            result = await self._recall_secret(parameters)
        elif tool_name == "update_secrets_filter":
            result = await self._update_secrets_filter(parameters)
        elif tool_name == "self_help":
            result = await self._self_help(parameters)
        else:
            self._tool_failures += 1  # Unknown tool is a failure!
            result = ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        if not result.success:
            self._tool_failures += 1  # Track failed executions
            self._track_error(Exception(result.error or "Tool execution failed"))

        return ToolExecutionResult(
            tool_name=tool_name,
            status=ToolExecutionStatus.COMPLETED if result.success else ToolExecutionStatus.FAILED,
            success=result.success,
            data=result.data,
            error=result.error,
            correlation_id=f"secrets_{tool_name}_{self._now().timestamp()}",
        )

    async def _recall_secret(self, params: ToolParameters) -> ToolResult:
        """Recall a secret by UUID."""
        try:
            secret_uuid = params.get("secret_uuid")
            purpose = params.get("purpose", "No purpose specified")
            decrypt = params.get("decrypt", False)

            if not secret_uuid:
                return ToolResult(success=False, error="secret_uuid is required")

            # Create context for audit
            context = SecretContext(
                operation="recall",
                request_id=f"recall_{secret_uuid}_{self._now().timestamp()}",
                metadata={"purpose": purpose},
            )

            # Retrieve the secret
            if decrypt:
                value = await self.secrets_service.retrieve_secret(secret_uuid)
                if value is None:
                    return ToolResult(success=False, error=f"Secret {secret_uuid} not found")
                self._secrets_retrieved += 1  # Track successful retrieval
                result_data = {"value": value, "decrypted": True}
            else:
                # Just verify it exists
                # Just check if it exists by trying to retrieve
                value = await self.secrets_service.retrieve_secret(secret_uuid)
                if value is None:
                    return ToolResult(success=False, error=f"Secret {secret_uuid} not found")
                self._secrets_retrieved += 1  # Track successful retrieval
                result_data = {"exists": True, "decrypted": False}

            return ToolResult(success=True, data=result_data)

        except Exception as e:
            logger.error(f"Error recalling secret: {e}")
            return ToolResult(success=False, error=str(e))

    async def _update_secrets_filter(self, params: ToolParameters) -> ToolResult:
        """Update secrets filter configuration."""
        try:
            operation = params.get("operation")
            if not operation:
                return ToolResult(success=False, error="operation is required")

            result_data = {"operation": operation}

            if operation == "add_pattern":
                pattern = params.get("pattern")
                pattern_type = params.get("pattern_type", "regex")
                if not pattern:
                    return ToolResult(success=False, error="pattern is required for add_pattern")

                # Filter operations not directly accessible - would need to be exposed
                return ToolResult(success=False, error="Filter operations not currently exposed")

            elif operation == "remove_pattern":
                pattern = params.get("pattern")
                if not pattern:
                    return ToolResult(success=False, error="pattern is required for remove_pattern")

                # Filter operations not directly accessible
                return ToolResult(success=False, error="Filter operations not currently exposed")

            elif operation == "list_patterns":
                # Filter operations not directly accessible
                patterns: List[Any] = []
                result_data.update({"patterns": patterns})

            elif operation == "enable":
                enabled = params.get("enabled", True)
                # Filter operations not directly accessible
                return ToolResult(success=False, error="Filter operations not currently exposed")

            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")

            return ToolResult(success=True, data=result_data)

        except Exception as e:
            logger.error(f"Error updating secrets filter: {e}")
            return ToolResult(success=False, error=str(e))

    async def _self_help(self, parameters: ToolParameters) -> ToolResult:
        """Access the agent experience document."""
        try:
            experience_path = Path("docs/agent_experience.md")

            if not experience_path.exists():
                return ToolResult(
                    success=False, error="Agent experience document not found at docs/agent_experience.md"
                )

            content = experience_path.read_text()

            return ToolResult(
                success=True, data={"content": content, "source": "docs/agent_experience.md", "length": len(content)}
            )

        except Exception as e:
            logger.error(f"Error reading experience document: {e}")
            return ToolResult(success=False, error=str(e))

    async def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return ["recall_secret", "update_secrets_filter", "self_help"]

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool."""
        if tool_name == "recall_secret":
            return ToolInfo(
                name="recall_secret",
                description="Recall a stored secret by UUID",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "secret_uuid": {"type": "string", "description": "UUID of the secret to recall"},
                        "purpose": {"type": "string", "description": "Why the secret is needed (for audit)"},
                        "decrypt": {
                            "type": "boolean",
                            "description": "Whether to decrypt the secret value",
                            "default": False,
                        },
                    },
                    required=["secret_uuid", "purpose"],
                ),
                category="security",
                when_to_use="When you need to retrieve a previously stored secret value",
            )
        elif tool_name == "update_secrets_filter":
            return ToolInfo(
                name="update_secrets_filter",
                description="Update secrets detection filter configuration",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "operation": {
                            "type": "string",
                            "enum": ["add_pattern", "remove_pattern", "list_patterns", "enable"],
                            "description": "Operation to perform",
                        },
                        "pattern": {"type": "string", "description": "Pattern for add/remove operations"},
                        "pattern_type": {"type": "string", "enum": ["regex", "exact"], "default": "regex"},
                        "enabled": {"type": "boolean", "description": "For enable operation"},
                    },
                    required=["operation"],
                ),
                category="security",
                when_to_use="When you need to modify how secrets are detected",
            )
        elif tool_name == "self_help":
            return ToolInfo(
                name="self_help",
                description="Access your experience document for guidance",
                parameters=ToolParameterSchema(type="object", properties={}, required=[]),
                category="knowledge",
                when_to_use="When you need guidance on your capabilities or best practices",
            )
        return None

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get information about all available tools."""
        tools = []
        for tool_name in await self.get_available_tools():
            tool_info = await self.get_tool_info(tool_name)
            if tool_info:
                tools.append(tool_info)
        return tools

    async def validate_parameters(self, tool_name: str, parameters: ToolParameters) -> bool:
        """Validate parameters for a tool."""
        if tool_name == "recall_secret":
            return "secret_uuid" in parameters and "purpose" in parameters
        elif tool_name == "update_secrets_filter":
            operation = parameters.get("operation")
            if not operation:
                return False
            if operation in ["add_pattern", "remove_pattern"]:
                return "pattern" in parameters
            return True
        elif tool_name == "self_help":
            return True  # No parameters required
        return False

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of an async tool execution."""
        # Secrets tools execute synchronously
        return None

    async def list_tools(self) -> List[str]:
        """List available tools - required by ToolServiceProtocol."""
        return await self.get_available_tools()

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a specific tool - required by ToolServiceProtocol."""
        tool_info = await self.get_tool_info(tool_name)
        if tool_info:
            return tool_info.parameters
        return None

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities with custom metadata."""
        # Get base capabilities
        capabilities = super().get_capabilities()

        # Add custom metadata using model_copy
        if capabilities.metadata:
            capabilities.metadata = capabilities.metadata.model_copy(
                update={"adapter": self.adapter_name, "tool_count": 3}
            )

        return capabilities

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect tool service specific metrics."""
        metrics = super()._collect_custom_metrics()

        # Calculate success rate
        success_rate = 0.0
        if self._request_count > 0:
            success_rate = (self._request_count - self._error_count) / self._request_count

        # Add tool-specific metrics
        metrics.update(
            {
                "tool_executions": float(self._request_count),
                "tool_errors": float(self._error_count),
                "success_rate": success_rate,
                "secrets_retrieved": float(self._secrets_retrieved),
                "audit_events_generated": float(self._request_count),  # Each execution generates an audit event
                "available_tools": 3.0,  # recall_secret, update_secrets_filter, self_help
            }
        )

        return metrics

    async def get_metrics(self) -> Dict[str, float]:
        """Get all metrics including base, custom, and v1.4.3 specific.

        Returns:
            Dict with all metrics including tool-specific and v1.4.3 metrics
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        current_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        uptime_seconds = 0.0
        if self._start_time:
            uptime_seconds = max(0.0, (current_time - self._start_time).total_seconds())

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "secrets_tool_invocations": float(self._request_count),
                "secrets_tool_retrieved": float(self._secrets_retrieved),
                "secrets_tool_stored": 0.0,  # This service only retrieves, never stores
                "secrets_tool_uptime_seconds": uptime_seconds,
                "tools_enabled": 3.0,  # recall_secret, update_secrets_filter, self_help
            }
        )

        return metrics

    # get_telemetry() removed - use get_metrics() from BaseService instead
