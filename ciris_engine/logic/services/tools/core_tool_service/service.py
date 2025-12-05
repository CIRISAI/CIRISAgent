"""
Core Tool Service - Provides core system tools for agents.

Implements ToolService protocol to expose core tools:
- Secrets management (RECALL_SECRET, UPDATE_SECRETS_FILTER)
- Ticket management (UPDATE_TICKET, GET_TICKET, DEFER_TICKET)
- Agent guidance (SELF_HELP)

Tickets are NOT a service - they're a coordination mechanism that sits above services.
Tools provide the agent-facing interface for ticket updates during task execution.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.logic.utils.jsondict_helpers import get_str
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
from ciris_engine.schemas.types import JSONDict

# ToolParameters is a JSONDict for flexible parameter passing
ToolParameters = JSONDict

logger = logging.getLogger(__name__)

# Error message constants to avoid duplication
ERROR_TICKET_ID_REQUIRED = "ticket_id (str) is required"
ERROR_FILTER_NOT_EXPOSED = "Filter operations not currently exposed"


class CoreToolService(BaseService, ToolService):
    """Service providing core system tools (secrets, tickets, guidance)."""

    def __init__(
        self,
        secrets_service: SecretsService,
        time_service: TimeServiceProtocol,
        db_path: Optional[str] = None,
    ) -> None:
        """Initialize with secrets service, time service, and optional db path.

        Args:
            secrets_service: Service for secrets management
            time_service: Service for time operations
            db_path: Optional database path override. When None (default),
                    uses current config (_test_db_path or essential_config).
                    When provided, uses this specific path for all operations.
        """
        super().__init__(time_service=time_service)
        self.secrets_service = secrets_service
        # Store db_path for persistence calls - None means use current config
        self._db_path = db_path
        self.adapter_name = "core_tools"

        # v1.4.3 metrics tracking
        self._secrets_retrieved = 0
        self._secrets_stored = 0
        self._tickets_updated = 0
        self._tickets_retrieved = 0
        self._tickets_deferred = 0
        self._metrics_tracking: Dict[str, float] = {}  # For custom metric tracking
        self._tool_executions = 0
        self._tool_failures = 0

    @property
    def db_path(self) -> Optional[str]:
        """Get database path for persistence operations.

        Returns the stored db_path if provided during initialization,
        otherwise None to use current config (_test_db_path or essential_config).
        """
        return self._db_path

    def _track_metric(self, metric_name: str, default: float = 0.0) -> float:
        """Track a metric with default value."""
        return self._metrics_tracking.get(metric_name, default)

    def get_service_type(self) -> ServiceType:
        """Get service type."""
        return ServiceType.TOOL

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return ["recall_secret", "update_secrets_filter", "self_help", "update_ticket", "get_ticket", "defer_ticket"]

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
        elif tool_name == "update_ticket":
            result = await self._update_ticket(parameters)
        elif tool_name == "get_ticket":
            result = await self._get_ticket(parameters)
        elif tool_name == "defer_ticket":
            result = await self._defer_ticket(parameters)
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
            secret_uuid_val = get_str(params, "secret_uuid", "")
            purpose = params.get("purpose", "No purpose specified")
            decrypt = params.get("decrypt", False)

            if not secret_uuid_val:
                return ToolResult(success=False, error="secret_uuid is required")

            # Retrieve the secret
            if decrypt:
                value = await self.secrets_service.retrieve_secret(secret_uuid_val)
                if value is None:
                    return ToolResult(success=False, error=f"Secret {secret_uuid_val} not found")
                self._secrets_retrieved += 1  # Track successful retrieval
                result_data = {"value": value, "decrypted": True}
            else:
                # Just verify it exists
                # Just check if it exists by trying to retrieve
                value = await self.secrets_service.retrieve_secret(secret_uuid_val)
                if value is None:
                    return ToolResult(success=False, error=f"Secret {secret_uuid_val} not found")
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
                if not pattern:
                    return ToolResult(success=False, error="pattern is required for add_pattern")

                # Filter operations not directly accessible - would need to be exposed
                return ToolResult(success=False, error=ERROR_FILTER_NOT_EXPOSED)

            elif operation == "remove_pattern":
                pattern = params.get("pattern")
                if not pattern:
                    return ToolResult(success=False, error="pattern is required for remove_pattern")

                # Filter operations not directly accessible
                return ToolResult(success=False, error=ERROR_FILTER_NOT_EXPOSED)

            elif operation == "list_patterns":
                # Filter operations not directly accessible
                patterns: List[Any] = []
                result_data.update({"patterns": patterns})

            elif operation == "enable":
                # Filter operations not directly accessible
                return ToolResult(success=False, error=ERROR_FILTER_NOT_EXPOSED)

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

    def _validate_ticket_id(self, params: ToolParameters) -> Optional[str]:
        """Validate and extract ticket_id from parameters.

        Returns:
            ticket_id if valid, None otherwise
        """
        ticket_id = params.get("ticket_id")
        if not ticket_id or not isinstance(ticket_id, str):
            return None
        return ticket_id

    def _parse_metadata_json(
        self, metadata_updates: Any, start_time: float
    ) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """Parse metadata updates, handling JSON strings from CLI/mock LLM.

        Args:
            metadata_updates: Raw metadata updates (dict or JSON string)
            start_time: Timer start for debug logging

        Returns:
            Tuple of (parsed_metadata, error_message). One will be None.
        """
        import json
        import time

        # Handle JSON string from command-line tools (mock LLM, CLI)
        if isinstance(metadata_updates, str):
            try:
                metadata_updates = json.loads(metadata_updates)
                logger.debug(
                    f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s PARSED_JSON metadata_updates={metadata_updates}"
                )
            except json.JSONDecodeError as e:
                return None, f"metadata must be valid JSON: {e}"

        if not isinstance(metadata_updates, dict):
            return None, "metadata must be a dictionary or valid JSON string"

        return metadata_updates, None

    def _merge_single_stage(
        self,
        merged_stages: dict[str, Any],
        stage_name: str,
        stage_data: Any,
        start_time: float,
    ) -> None:
        """Merge a single stage into the merged_stages dict in place.

        Args:
            merged_stages: Dictionary of merged stages (modified in place)
            stage_name: Name of the stage to merge
            stage_data: Data for the stage
            start_time: Timer start for debug logging
        """
        import time

        logger.debug(
            f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s MERGING_STAGE " f"stage={stage_name} data={stage_data}"
        )

        if not isinstance(stage_data, dict):
            return

        if stage_name in merged_stages and isinstance(merged_stages[stage_name], dict):
            # Merge existing stage
            before = merged_stages[stage_name].copy()
            merged_stages[stage_name] = {**merged_stages[stage_name], **stage_data}
            logger.debug(
                f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s MERGED_STAGE "
                f"stage={stage_name} before={before} after={merged_stages[stage_name]}"
            )
        else:
            # New stage
            merged_stages[stage_name] = stage_data
            logger.debug(
                f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s NEW_STAGE " f"stage={stage_name} data={stage_data}"
            )

    def _merge_stage_metadata(
        self, current_metadata: dict[str, Any], metadata_updates: dict[str, Any], start_time: float
    ) -> dict[str, Any]:
        """Deep merge stage metadata, preserving existing stage data.

        Args:
            current_metadata: Current ticket metadata
            metadata_updates: New metadata to merge
            start_time: Timer start for debug logging

        Returns:
            Merged metadata dictionary
        """
        import time

        # Shallow merge first
        merged_metadata: dict[str, Any] = {**current_metadata, **metadata_updates}

        # Deep merge for 'stages' key only
        if "stages" not in metadata_updates or "stages" not in current_metadata:
            return merged_metadata

        merged_stages: dict[str, Any] = {**current_metadata.get("stages", {})}
        stages_updates = metadata_updates.get("stages", {})

        logger.debug(
            f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s DEEP_MERGE_STAGES "
            f"base_stages={list(merged_stages.keys())} update_stages={list(stages_updates.keys())}"
        )

        if isinstance(stages_updates, dict):
            for stage_name, stage_data in stages_updates.items():
                self._merge_single_stage(merged_stages, stage_name, stage_data, start_time)
            merged_metadata["stages"] = merged_stages

        return merged_metadata

    def _update_ticket_status_only(
        self, ticket_id: str, new_status: Any, params: ToolParameters, result_data: dict[str, Any]
    ) -> Optional[ToolResult]:
        """Update ticket status and add to result data.

        Args:
            ticket_id: Ticket ID to update
            new_status: New status value
            params: Tool parameters (for notes)
            result_data: Result dictionary to update

        Returns:
            ToolResult with error if update fails, None if successful
        """
        from ciris_engine.logic.persistence.models.tickets import update_ticket_status

        if not isinstance(new_status, str):
            return ToolResult(success=False, error="status must be a string")

        notes = params.get("notes")
        notes_str = str(notes) if notes is not None else None
        success = update_ticket_status(ticket_id, new_status, notes=notes_str, db_path=self._db_path)

        if not success:
            return ToolResult(success=False, error=f"Failed to update ticket {ticket_id} status")

        result_data["updates"]["status"] = new_status
        if notes:
            result_data["updates"]["notes"] = notes

        return None

    def _update_ticket_metadata_only(
        self,
        ticket_id: str,
        current_ticket: dict[str, Any],
        metadata_updates: Any,
        result_data: dict[str, Any],
        start_time: float,
    ) -> Optional[ToolResult]:
        """Update ticket metadata with deep merge for stages.

        Args:
            ticket_id: Ticket ID to update
            current_ticket: Current ticket data
            metadata_updates: New metadata to merge
            result_data: Result dictionary to update
            start_time: Timer start for debug logging

        Returns:
            ToolResult with error if update fails, None if successful
        """
        import time

        from ciris_engine.logic.persistence.models.tickets import update_ticket_metadata

        logger.debug(
            f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s METADATA_UPDATE_START metadata_updates={metadata_updates}"
        )

        # Parse JSON if needed
        parsed_metadata, error = self._parse_metadata_json(metadata_updates, start_time)
        if error:
            return ToolResult(success=False, error=error)

        metadata_updates = parsed_metadata

        # Get current metadata
        current_metadata = current_ticket.get("metadata", {})
        if not isinstance(current_metadata, dict):
            current_metadata = {}

        logger.debug(f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s BEFORE_MERGE current={current_metadata}")

        # Deep merge with special handling for stages
        merged_metadata = self._merge_stage_metadata(current_metadata, metadata_updates, start_time)

        logger.debug(f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s AFTER_MERGE merged={merged_metadata}")

        # Update database
        success = update_ticket_metadata(ticket_id, merged_metadata, db_path=self._db_path)
        logger.debug(f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s DB_UPDATE_RESULT success={success}")

        if not success:
            return ToolResult(success=False, error=f"Failed to update ticket {ticket_id} metadata")

        result_data["updates"]["metadata"] = metadata_updates
        return None

    async def _update_ticket(self, params: ToolParameters) -> ToolResult:
        """Update ticket status or metadata during task processing."""
        import time

        start_time = time.time()

        try:
            from ciris_engine.logic.persistence.models.tickets import get_ticket

            # Validate ticket_id
            ticket_id = self._validate_ticket_id(params)
            if not ticket_id:
                return ToolResult(success=False, error=ERROR_TICKET_ID_REQUIRED)

            logger.debug(f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s START ticket_id={ticket_id}")

            # Get current ticket to validate and merge metadata
            current_ticket = get_ticket(ticket_id, db_path=self._db_path)
            if not current_ticket:
                return ToolResult(success=False, error=f"Ticket {ticket_id} not found")

            logger.debug(
                f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s FETCHED current_metadata={current_ticket.get('metadata', {})}"
            )

            result_data: dict[str, Any] = {"ticket_id": ticket_id, "updates": {}}

            # Update status if provided
            new_status = params.get("status")
            if new_status:
                error_result = self._update_ticket_status_only(ticket_id, new_status, params, result_data)
                if error_result:
                    return error_result

            # Update metadata if provided
            metadata_updates = params.get("metadata")
            if metadata_updates:
                error_result = self._update_ticket_metadata_only(
                    ticket_id, current_ticket, metadata_updates, result_data, start_time
                )
                if error_result:
                    return error_result

            self._tickets_updated += 1
            logger.debug(f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s COMPLETE result={result_data}")
            return ToolResult(success=True, data=result_data)

        except Exception as e:
            logger.error(f"Error updating ticket: {e}")
            return ToolResult(success=False, error=str(e))

    async def _get_ticket(self, params: ToolParameters) -> ToolResult:
        """Retrieve current ticket state during task processing."""
        try:
            from ciris_engine.logic.persistence.models.tickets import get_ticket

            ticket_id = params.get("ticket_id")
            if not ticket_id or not isinstance(ticket_id, str):
                return ToolResult(success=False, error=ERROR_TICKET_ID_REQUIRED)

            # Use self._db_path to respect provided path or current config
            ticket = get_ticket(ticket_id, db_path=self._db_path)
            if not ticket:
                return ToolResult(success=False, error=f"Ticket {ticket_id} not found")

            self._tickets_retrieved += 1
            return ToolResult(success=True, data=ticket)

        except Exception as e:
            logger.error(f"Error retrieving ticket: {e}")
            return ToolResult(success=False, error=str(e))

    async def _defer_ticket(self, params: ToolParameters) -> ToolResult:
        """Defer ticket processing to a future time or await human response.

        Automatically sets ticket status to 'deferred' to prevent WorkProcessor
        from creating new tasks until the deferral condition is resolved.
        """
        try:
            from datetime import timedelta

            from ciris_engine.logic.persistence.models.tickets import (
                get_ticket,
                update_ticket_metadata,
                update_ticket_status,
            )

            ticket_id = params.get("ticket_id")
            if not ticket_id or not isinstance(ticket_id, str):
                return ToolResult(success=False, error=ERROR_TICKET_ID_REQUIRED)

            # Get current ticket - use self._db_path to respect provided path or current config
            current_ticket = get_ticket(ticket_id, db_path=self._db_path)
            if not current_ticket:
                return ToolResult(success=False, error=f"Ticket {ticket_id} not found")

            current_metadata = current_ticket.get("metadata", {})
            if not isinstance(current_metadata, dict):
                current_metadata = {}

            # Determine deferral type
            defer_until_timestamp = params.get("defer_until")  # ISO8601 timestamp
            defer_hours = params.get("defer_hours")  # Relative hours
            await_human = params.get("await_human", False)  # Wait for human response
            reason = params.get("reason", "No reason provided")

            result_data = {"ticket_id": ticket_id, "deferral_type": None, "reason": reason}

            if await_human:
                # Mark as awaiting human response
                current_metadata["awaiting_human_response"] = True
                current_metadata["deferred_reason"] = reason
                current_metadata["deferred_at"] = self._now().isoformat()
                result_data["deferral_type"] = "awaiting_human"

            elif defer_until_timestamp:
                # Defer until specific timestamp
                current_metadata["deferred_until"] = defer_until_timestamp
                current_metadata["deferred_reason"] = reason
                current_metadata["deferred_at"] = self._now().isoformat()
                current_metadata["awaiting_human_response"] = False
                result_data["deferral_type"] = "until_timestamp"
                result_data["deferred_until"] = defer_until_timestamp

            elif defer_hours:
                # Defer for relative hours
                if not isinstance(defer_hours, (int, float)):
                    return ToolResult(success=False, error="defer_hours must be a number")
                defer_until = self._now() + timedelta(hours=float(defer_hours))
                current_metadata["deferred_until"] = defer_until.isoformat()
                current_metadata["deferred_reason"] = reason
                current_metadata["deferred_at"] = self._now().isoformat()
                current_metadata["awaiting_human_response"] = False
                result_data["deferral_type"] = "relative_hours"
                result_data["deferred_until"] = defer_until.isoformat()
                result_data["defer_hours"] = defer_hours

            else:
                return ToolResult(success=False, error="Must provide defer_until, defer_hours, or await_human=true")

            # Update ticket status to 'deferred' (prevents task generation)
            status_success = update_ticket_status(
                ticket_id, "deferred", notes=f"Deferred: {reason}", db_path=self._db_path
            )
            if not status_success:
                return ToolResult(success=False, error=f"Failed to update ticket {ticket_id} status to deferred")

            # Update ticket metadata
            success = update_ticket_metadata(ticket_id, current_metadata, db_path=self._db_path)
            if not success:
                return ToolResult(success=False, error=f"Failed to defer ticket {ticket_id}")

            self._tickets_deferred += 1
            result_data["status_updated"] = "deferred"
            return ToolResult(success=True, data=result_data)

        except Exception as e:
            logger.error(f"Error deferring ticket: {e}")
            return ToolResult(success=False, error=str(e))

    async def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return ["recall_secret", "update_secrets_filter", "self_help", "update_ticket", "get_ticket", "defer_ticket"]

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
        elif tool_name == "update_ticket":
            return ToolInfo(
                name="update_ticket",
                description="Update ticket status or metadata during task processing",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "ticket_id": {"type": "string", "description": "Ticket ID to update"},
                        "status": {
                            "type": "string",
                            "enum": [
                                "pending",
                                "assigned",
                                "in_progress",
                                "blocked",
                                "deferred",
                                "completed",
                                "cancelled",
                                "failed",
                            ],
                            "description": "New ticket status",
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Metadata updates (merged with existing metadata)",
                        },
                        "notes": {"type": "string", "description": "Optional notes about the update"},
                    },
                    required=["ticket_id"],
                ),
                category="workflow",
                when_to_use="When processing a ticket task and need to record progress or results",
            )
        elif tool_name == "get_ticket":
            return ToolInfo(
                name="get_ticket",
                description="Retrieve current ticket state during task processing",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={"ticket_id": {"type": "string", "description": "Ticket ID to retrieve"}},
                    required=["ticket_id"],
                ),
                category="workflow",
                when_to_use="When you need to check current ticket status, metadata, or stage progress",
            )
        elif tool_name == "defer_ticket":
            return ToolInfo(
                name="defer_ticket",
                description="Defer ticket processing to future time or await human response",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "ticket_id": {"type": "string", "description": "Ticket ID to defer"},
                        "defer_until": {"type": "string", "description": "ISO8601 timestamp to defer until"},
                        "defer_hours": {"type": "number", "description": "Hours to defer (relative)"},
                        "await_human": {
                            "type": "boolean",
                            "description": "Wait for human response (blocks task generation)",
                        },
                        "reason": {"type": "string", "description": "Reason for deferral (for audit/transparency)"},
                    },
                    required=["ticket_id", "reason"],
                ),
                category="workflow",
                when_to_use="When ticket needs human input or must wait for external event/time",
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
        elif tool_name == "update_ticket":
            return "ticket_id" in parameters
        elif tool_name == "get_ticket":
            return "ticket_id" in parameters
        elif tool_name == "defer_ticket":
            return "ticket_id" in parameters and "reason" in parameters
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
                update={"adapter": self.adapter_name, "tool_count": 6}
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
                "tickets_updated": float(self._tickets_updated),
                "tickets_retrieved": float(self._tickets_retrieved),
                "tickets_deferred": float(self._tickets_deferred),
                "audit_events_generated": float(self._request_count),  # Each execution generates an audit event
                "available_tools": 6.0,  # recall_secret, update_secrets_filter, self_help, update_ticket, get_ticket, defer_ticket
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
                "core_tool_invocations": float(self._request_count),
                "core_tool_uptime_seconds": uptime_seconds,
                "secrets_retrieved": float(self._secrets_retrieved),
                "secrets_stored": 0.0,  # This service only retrieves, never stores
                "tickets_updated": float(self._tickets_updated),
                "tickets_retrieved": float(self._tickets_retrieved),
                "tickets_deferred": float(self._tickets_deferred),
                # Backwards compatibility aliases for unit tests
                "tickets_updated_total": float(self._tickets_updated),
                "tickets_deferred_total": float(self._tickets_deferred),
                "tools_enabled": 6.0,  # recall_secret, update_secrets_filter, self_help, update_ticket, get_ticket, defer_ticket
            }
        )

        return metrics

    # get_telemetry() removed - use get_metrics() from BaseService instead
