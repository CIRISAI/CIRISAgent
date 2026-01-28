"""
Ordercli Tool Service for CIRIS.

Converted from Clawdbot skill: ordercli
Foodora-only CLI for checking past orders and active order status (Deliveroo WIP).

This service provides skill-based guidance for using external tools/CLIs.
The detailed instructions from the original SKILL.md are embedded in the
ToolInfo.documentation field for DMA-aware tool selection.
"""

import logging
import os
import shutil
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ciris_engine.schemas.adapters.tools import (
    BinaryRequirement,
    ConfigRequirement,
    EnvVarRequirement,
    InstallStep,
    ToolDMAGuidance,
    ToolDocumentation,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolGotcha,
    ToolInfo,
    ToolParameterSchema,
    ToolRequirements,
    UsageExample,
)

logger = logging.getLogger(__name__)


class OrdercliToolService:
    """
    Ordercli tool service providing skill-based guidance.

    Original skill: ordercli
    Description: Foodora-only CLI for checking past orders and active order status (Deliveroo WIP).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("OrdercliToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("OrdercliToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("OrdercliToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="ordercli",
            description="""Foodora-only CLI for checking past orders and active order status (Deliveroo WIP).""",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "command": {
                        "type": "string",
                        "description": "The command to execute (will be validated against skill guidance)",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory for command execution (optional)",
                    },
                },
                required=["command"],
            ),
            category="skill",
            when_to_use="""When you need to foodora-only cli for checking past orders and active order status (deliveroo wip).""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="ordercli"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install ordercli (brew)",
                    formula="steipete/tap/ordercli",
                    provides_binaries=["ordercli"],
                ),
                InstallStep(id="go", kind="go", label="Install ordercli (go)", provides_binaries=["ordercli"]),
            ],
            documentation=ToolDocumentation(
                quick_start="Use `ordercli` to check past orders and track active order status (Foodora only right now).",
                detailed_instructions="""# ordercli\n\nUse `ordercli` to check past orders and track active order status (Foodora only right now).\n\nQuick start (Foodora)\n- `ordercli foodora countries`\n- `ordercli foodora config set --country AT`\n- `ordercli foodora login --email you@example.com --password-stdin`\n- `ordercli foodora orders`\n- `ordercli foodora history --limit 20`\n- `ordercli foodora history show <orderCode>`\n\nOrders\n- Active list (arrival/status): `ordercli foodora orders`\n- Watch: `ordercli foodora orders --watch`\n- Active order detail: `ordercli foodora order <orderCode>`\n- History detail JSON: `ordercli foodora history show <orderCode> --json`\n\nReorder (adds to cart)\n- Preview: `ordercli foodora reorder <orderCode>`\n- Confirm: `ordercli foodora reorder <orderCode> --confirm`\n- Address: `ordercli foodora reorder <orderCode> --confirm --address-id <id>`\n\nCloudflare / bot protection\n- Browser login: `ordercli foodora login --email you@example.com --password-stdin --browser`\n- Reuse profile: `--browser-profile \"$HOME/Library/Application Support/ordercli/browser-profile\"`\n- Import Chrome cookies: `ordercli foodora cookies chrome --profile \"Default\"`\n\nSession import (no password)\n- `ordercli foodora session chrome --url https://www.foodora.at/ --profile \"Default\"`\n- `ordercli foodora session refresh --client-id android`\n\nDeliveroo (WIP, not working yet)\n- Requires `DELIVEROO_BEARER_TOKEN` (optional `DELIVEROO_COOKIE`).\n- `ordercli deliveroo config set --market uk`\n- `ordercli deliveroo history`\n\nNotes\n- Use `--config /tmp/ordercli.json` for testing.\n- Confirm before any reorder or cart-changing action.""",
                examples=[],
                gotchas=[],
                homepage="https://ordercli.sh",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "ordercli", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["ordercli"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "ordercli":
            return self._build_tool_info()
        return None

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get info for all tools."""
        return [self._build_tool_info()]

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a tool."""
        tool_info = await self.get_tool_info(tool_name)
        return tool_info.parameters if tool_info else None

    async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Validate parameters for a tool."""
        if tool_name != "ordercli":
            return False
        return "command" in parameters

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of previously executed tool."""
        return None

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return list of available tools (legacy format)."""
        tool_info = self._build_tool_info()
        return [
            {
                "name": tool_info.name,
                "description": tool_info.description,
                "parameters": tool_info.parameters.model_dump() if tool_info.parameters else {},
            }
        ]

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        """Execute the skill-based tool.

        Note: This is a guidance tool - it provides instructions for using
        external CLIs rather than executing them directly. The agent should
        use the bash tool to execute the actual commands.
        """
        self._call_count += 1
        correlation_id = str(uuid4())

        if tool_name != "ordercli":
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown tool: {tool_name}",
                correlation_id=correlation_id,
            )

        try:
            command = parameters.get("command", "")

            # Check requirements using ToolInfo
            tool_info = self._build_tool_info()
            requirements_met, missing = self._check_requirements(tool_info)
            if not requirements_met:
                return ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={"missing_requirements": missing},
                    error=f"Missing requirements: {', '.join(missing)}",
                    correlation_id=correlation_id,
                )

            # Return guidance for executing the command
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data={
                    "command": command,
                    "guidance": "Use bash tool to execute this command",
                    "skill_instructions": tool_info.documentation.quick_start if tool_info.documentation else None,
                    "requirements_met": requirements_met,
                },
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

    def _check_requirements(self, tool_info: ToolInfo) -> tuple[bool, List[str]]:
        """Check if all requirements are met using ToolInfo.requirements."""
        missing = []

        if not tool_info.requirements:
            return True, []

        req = tool_info.requirements

        # Check binaries
        for bin_req in req.binaries:
            if not shutil.which(bin_req.name):
                missing.append(f"binary:{bin_req.name}")

        # Check any_binaries (at least one)
        if req.any_binaries:
            found = any(shutil.which(b.name) for b in req.any_binaries)
            if not found:
                names = [b.name for b in req.any_binaries]
                missing.append(f"any_binary:{','.join(names)}")

        # Check env vars
        for env_req in req.env_vars:
            if not os.environ.get(env_req.name):
                missing.append(f"env:{env_req.name}")

        # Check config keys (skip for now - would need config service)
        # for config_req in req.config_keys:
        #     ...

        return len(missing) == 0, missing
