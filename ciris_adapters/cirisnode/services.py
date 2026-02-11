"""
CIRISNode tool service implementation.

Provides tool interface for interacting with CIRISNode services:
- Health checking
- WBD (Wisdom-Based Deferral) operations
- HE-300 and SimpleBench benchmarks
- Agent event tracking
"""

import logging
from typing import Any, Dict, List, Optional, cast
from uuid import uuid4

from ciris_adapters.cirisnode.client import CIRISNodeClient
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema

logger = logging.getLogger(__name__)


class CIRISNodeToolService:
    """Tool service for CIRISNode operations.

    Provides tools for WBD, benchmarks, and agent event tracking.
    All tools are prefixed with 'cirisnode:' for namespace clarity.

    Example:
        service = CIRISNodeToolService(config={"base_url": "https://admin.ethicsengine.org"})
        await service.start()
        result = await service.execute_tool("cirisnode:health", {})
        await service.stop()
    """

    # Tool definitions using ToolInfo schema
    TOOL_DEFINITIONS: Dict[str, ToolInfo] = {
        "cirisnode:health": ToolInfo(
            name="cirisnode:health",
            description="Check CIRISNode service health and connectivity",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[],
            ),
        ),
        "cirisnode:wbd_submit": ToolInfo(
            name="cirisnode:wbd_submit",
            description="Submit a Wisdom-Based Deferral task for human review",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "agent_task_id": {
                        "type": "string",
                        "description": "Agent's internal task ID for tracking",
                    },
                    "payload": {
                        "type": "string",
                        "description": "Task payload describing what needs review",
                    },
                },
                required=["agent_task_id", "payload"],
            ),
        ),
        "cirisnode:wbd_tasks": ToolInfo(
            name="cirisnode:wbd_tasks",
            description="List pending and resolved WBD tasks",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[],
            ),
        ),
        "cirisnode:wbd_resolve": ToolInfo(
            name="cirisnode:wbd_resolve",
            description="Resolve a WBD task with approve or reject decision",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "task_id": {
                        "type": "string",
                        "description": "WBD task ID to resolve",
                    },
                    "decision": {
                        "type": "string",
                        "description": "Resolution decision: 'approve' or 'reject'",
                        "enum": ["approve", "reject"],
                    },
                    "comment": {
                        "type": "string",
                        "description": "Optional comment explaining the decision",
                    },
                },
                required=["task_id", "decision"],
            ),
        ),
        "cirisnode:he300_run": ToolInfo(
            name="cirisnode:he300_run",
            description="Start an HE-300 ethics benchmark job",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "scenario_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific scenario IDs to run (optional)",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category (optional)",
                    },
                    "n_scenarios": {
                        "type": "integer",
                        "description": "Number of scenarios to run (default 300)",
                        "default": 300,
                    },
                    "model": {
                        "type": "string",
                        "description": "LLM model to use (optional)",
                    },
                },
                required=[],
            ),
        ),
        "cirisnode:he300_status": ToolInfo(
            name="cirisnode:he300_status",
            description="Check status of an HE-300 benchmark job",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "job_id": {
                        "type": "string",
                        "description": "Benchmark job ID",
                    },
                },
                required=["job_id"],
            ),
        ),
        "cirisnode:he300_results": ToolInfo(
            name="cirisnode:he300_results",
            description="Get results of a completed HE-300 benchmark",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "job_id": {
                        "type": "string",
                        "description": "Benchmark job ID",
                    },
                },
                required=["job_id"],
            ),
        ),
        "cirisnode:he300_scenarios": ToolInfo(
            name="cirisnode:he300_scenarios",
            description="List available HE-300 benchmark scenarios",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "category": {
                        "type": "string",
                        "description": "Filter by category (optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum scenarios to return (default 100)",
                        "default": 100,
                    },
                },
                required=[],
            ),
        ),
        "cirisnode:simplebench_run": ToolInfo(
            name="cirisnode:simplebench_run",
            description="Start a SimpleBench benchmark job",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[],
            ),
        ),
        "cirisnode:simplebench_results": ToolInfo(
            name="cirisnode:simplebench_results",
            description="Get results of a SimpleBench job",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "job_id": {
                        "type": "string",
                        "description": "SimpleBench job ID",
                    },
                },
                required=["job_id"],
            ),
        ),
        "cirisnode:agent_events_post": ToolInfo(
            name="cirisnode:agent_events_post",
            description="Post an agent event for observability tracking",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "agent_uid": {
                        "type": "string",
                        "description": "Agent unique identifier",
                    },
                    "event": {
                        "type": "object",
                        "description": "Event data (Task/Thought/Action)",
                    },
                },
                required=["agent_uid", "event"],
            ),
        ),
        "cirisnode:agent_events_list": ToolInfo(
            name="cirisnode:agent_events_list",
            description="List all recorded agent events",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[],
            ),
        ),
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service.

        Args:
            config: Configuration from manifest (base_url, auth_token, etc.)
        """
        self.config = config or {}
        self._client: Optional[CIRISNodeClient] = None

    async def start(self) -> None:
        """Start the service and initialize HTTP client."""
        self._client = CIRISNodeClient(
            base_url=self.config.get("base_url"),
            auth_token=self.config.get("auth_token"),
            agent_token=self.config.get("agent_token"),
            timeout=self.config.get("timeout", 30),
            max_retries=self.config.get("max_retries", 3),
        )
        await self._client.start()
        logger.info("CIRISNodeToolService started")

    async def stop(self) -> None:
        """Stop the service and cleanup."""
        if self._client:
            await self._client.stop()
            self._client = None
        logger.info("CIRISNodeToolService stopped")

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    def get_service_metadata(self) -> Dict[str, Any]:
        """Return service metadata for DSAR and data source discovery."""
        return {"data_source": False, "service_type": "system"}

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return list(self.TOOL_DEFINITIONS.keys())

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        return self.TOOL_DEFINITIONS.get(tool_name)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get info for all tools."""
        return list(self.TOOL_DEFINITIONS.values())

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a tool."""
        tool_info = self.TOOL_DEFINITIONS.get(tool_name)
        return tool_info.parameters if tool_info else None

    async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Validate parameters for a tool without executing it."""
        if tool_name not in self.TOOL_DEFINITIONS:
            return False
        tool_info = self.TOOL_DEFINITIONS[tool_name]
        if not tool_info.parameters:
            return True
        required = tool_info.parameters.required or []
        return all(param in parameters for param in required)

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of previously executed tool. Not implemented for sync tools."""
        return None

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return list of available tools (legacy format)."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters.model_dump() if tool.parameters else {},
            }
            for tool in self.TOOL_DEFINITIONS.values()
        ]

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        """Execute a tool and return results.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            context: Optional execution context

        Returns:
            ToolExecutionResult with status, success, data, and error
        """
        correlation_id = str(uuid4())

        if tool_name not in self.TOOL_DEFINITIONS:
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown tool: {tool_name}",
                correlation_id=correlation_id,
            )

        if not self._client:
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error="Service not started. Call start() first.",
                correlation_id=correlation_id,
            )

        try:
            data = await self._execute_tool_impl(tool_name, parameters)
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data=data,
                error=None,
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )

    async def _execute_tool_impl(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Internal tool execution implementation.

        Args:
            tool_name: Tool to execute
            parameters: Tool parameters

        Returns:
            Tool execution result data (Dict or List depending on tool)
        """
        if not self._client:
            raise RuntimeError("Client not initialized")

        # Assert client exists for mypy
        client = self._client

        if tool_name == "cirisnode:health":
            return await client.health_check()

        elif tool_name == "cirisnode:wbd_submit":
            return await client.wbd_submit(
                agent_task_id=parameters["agent_task_id"],
                payload=parameters["payload"],
            )

        elif tool_name == "cirisnode:wbd_tasks":
            return await client.wbd_list_tasks()

        elif tool_name == "cirisnode:wbd_resolve":
            return await client.wbd_resolve(
                task_id=parameters["task_id"],
                decision=parameters["decision"],
                comment=parameters.get("comment"),
            )

        elif tool_name == "cirisnode:he300_run":
            return await client.he300_run(
                scenario_ids=parameters.get("scenario_ids"),
                category=parameters.get("category"),
                n_scenarios=parameters.get("n_scenarios", 300),
                model=parameters.get("model"),
            )

        elif tool_name == "cirisnode:he300_status":
            return await client.he300_status(job_id=parameters["job_id"])

        elif tool_name == "cirisnode:he300_results":
            return await client.he300_results(job_id=parameters["job_id"])

        elif tool_name == "cirisnode:he300_scenarios":
            return await client.he300_scenarios(
                category=parameters.get("category"),
                limit=parameters.get("limit", 100),
            )

        elif tool_name == "cirisnode:simplebench_run":
            return await client.simplebench_run()

        elif tool_name == "cirisnode:simplebench_results":
            return await client.simplebench_results(job_id=parameters["job_id"])

        elif tool_name == "cirisnode:agent_events_post":
            return await client.post_agent_event(
                agent_uid=parameters["agent_uid"],
                event=parameters["event"],
            )

        elif tool_name == "cirisnode:agent_events_list":
            events = await client.list_agent_events()
            return {"events": events}

        else:
            raise ValueError(f"Tool not implemented: {tool_name}")
