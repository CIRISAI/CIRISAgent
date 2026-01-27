"""
Peekaboo Tool Service for CIRIS.

Converted from Clawdbot skill: peekaboo
Capture and automate macOS UI with the Peekaboo CLI.

This service provides skill-based guidance for using external tools/CLIs.
The detailed instructions from the original SKILL.md are embedded in the
ToolInfo.documentation field for DMA-aware tool selection.
"""

import logging
import os
import shutil
from datetime import datetime, timezone
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


class PeekabooToolService:
    """
    Peekaboo tool service providing skill-based guidance.

    Original skill: peekaboo
    Description: Capture and automate macOS UI with the Peekaboo CLI.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("PeekabooToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("PeekabooToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("PeekabooToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="peekaboo",
            description="""Capture and automate macOS UI with the Peekaboo CLI.""",
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
            when_to_use="""When you need to capture and automate macos ui with the peekaboo cli.""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="peekaboo"),
                ],
                platforms=["darwin"],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install Peekaboo (brew)",
                    formula="steipete/tap/peekaboo",
                    provides_binaries=["peekaboo"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Peekaboo is a full macOS UI automation CLI: capture/inspect screens, target UI",
                detailed_instructions="""# Peekaboo\n\nPeekaboo is a full macOS UI automation CLI: capture/inspect screens, target UI\nelements, drive input, and manage apps/windows/menus. Commands share a snapshot\ncache and support `--json`/`-j` for scripting. Run `peekaboo` or\n`peekaboo <cmd> --help` for flags; `peekaboo --version` prints build metadata.\nTip: run via `polter peekaboo` to ensure fresh builds.\n\n## Features (all CLI capabilities, excluding agent/MCP)\n\nCore\n- `bridge`: inspect Peekaboo Bridge host connectivity\n- `capture`: live capture or video ingest + frame extraction\n- `clean`: prune snapshot cache and temp files\n- `config`: init/show/edit/validate, providers, models, credentials\n- `image`: capture screenshots (screen/window/menu bar regions)\n- `learn`: print the full agent guide + tool catalog\n- `list`: apps, windows, screens, menubar, permissions\n- `permissions`: check Screen Recording/Accessibility status\n- `run`: execute `.peekaboo.json` scripts\n- `sleep`: pause execution for a duration\n- `tools`: list available tools with filtering/display options\n\nInteraction\n- `click`: target by ID/query/coords with smart waits\n- `drag`: drag & drop across elements/coords/Dock\n- `hotkey`: modifier combos like `cmd,shift,t`\n- `move`: cursor positioning with optional smoothing\n- `paste`: set clipboard -> paste -> restore\n- `press`: special-key sequences with repeats\n- `scroll`: directional scrolling (targeted + smooth)\n- `swipe`: gesture-style drags between targets\n- `type`: text + control keys (`--clear`, delays)\n\nSystem\n- `app`: launch/quit/relaunch/hide/unhide/switch/list apps\n- `clipboard`: read/write clipboard (text/images/files)\n- `dialog`: click/input/file/dismiss/list system dialogs\n- `dock`: launch/right-click/hide/show/list Dock items\n- `menu`: click/list application menus + menu extras\n- `menubar`: list/click status bar items\n- `open`: enhanced `open` with app targeting + JSON payloads\n- `space`: list/switch/move-window (Spaces)\n- `visualizer`: exercise Peekaboo visual feedback animations\n- `window`: close/minimize/maximize/move/resize/focus/list\n\nVision\n- `see`: annotated UI maps, snapshot IDs, optional analysis\n\nGlobal runtime flags\n- `--json`/`-j`, `--verbose`/`-v`, `--log-level <level>`\n- `--no-remote`, `--bridge-socket <path>`\n\n## Quickstart (happy path)\n```bash\npeekaboo permissions\npeekaboo list apps --json\npeekaboo see --annotate --path /tmp/peekaboo-see.png\npeekaboo click --on B1\npeekaboo type \"Hello\" --return\n```\n\n## Common targeting parameters (most interaction commands)\n- App/window: `--app`, `--pid`, `--window-title`, `--window-id`, `--window-index`\n- Snapshot targeting: `--snapshot` (ID from `see`; defaults to latest)\n- Element/coords: `--on`/`--id` (element ID), `--coords x,y`\n- Focus control: `--no-auto-focus`, `--space-switch`, `--bring-to-current-space`,\n  `--focus-timeout-seconds`, `--focus-retry-count`\n\n## Common capture parameters\n- Output: `--path`, `--format png|jpg`, `--retina`\n- Targeting: `--mode screen|window|frontmost`, `--screen-index`,\n  `--window-title`, `--window-id`\n- Analysis: `--analyze \"prompt\"`, `--annotate`\n- Capture engine: `--capture-engine auto|classic|cg|modern|sckit`\n\n## Common motion/typing parameters\n- Timing: `--duration` (drag/swipe), `--steps`, `--delay` (type/scroll/press)\n- Human-ish movement: `--profile human|linear`, `--wpm` (typing)\n- Scroll: `--direction up|down|left|right`, `--amount <ticks>`, `--smooth`\n\n## Examples\n### See -> click -> type (most reliable flow)\n```bash\npeekaboo see --app Safari --window-title \"Login\" --annotate --path /tmp/see.png\npeekaboo click --on B3 --app Safari\npeekaboo type \"user@example.com\" --app Safari\npeekaboo press tab --count 1 --app Safari\npeekaboo type \"supersecret\" --app Safari --return\n```\n\n### Target by window id\n```bash\npeekaboo list windows --app \"Visual Studio Code\" --json\npeekaboo click --window-id 12345 --coords 120,160\npeekaboo type \"Hello from Peekaboo\" --window-id 12345\n```\n\n### Capture screenshots + analyze\n```bash\npeekaboo image --mode screen --screen-index 0 --retina --path /tmp/screen.png\npeekaboo image --app Safari --window-title \"Dashboard\" --analyze \"Summarize KPIs\"\npeekaboo see --mode screen --screen-index 0 --analyze \"Summarize the dashboard\"\n```\n\n### Live capture (motion-aware)\n```bash\npeekaboo capture live --mode region --region 100,100,800,600 --duration 30 \\\n  --active-fps 8 --idle-fps 2 --highlight-changes --path /tmp/capture\n```\n\n### App + window management\n```bash\npeekaboo app launch \"Safari\" --open https://example.com\npeekaboo window focus --app Safari --window-title \"Example\"\npeekaboo window set-bounds --app Safari --x 50 --y 50 --width 1200 --height 800\npeekaboo app quit --app Safari\n```\n\n### Menus, menubar, dock\n```bash\npeekaboo menu click --app Safari --item \"New Window\"\npeekaboo menu click --app TextEdit --path \"Format > Font > Show Fonts\"\npeekaboo menu click-extra --title \"WiFi\"\npeekaboo dock launch Safari\npeekaboo menubar list --json\n```\n\n### Mouse + gesture input\n```bash\npeekaboo move 500,300 --smooth\npeekaboo dra""",
                examples=[],
                gotchas=[],
                homepage="https://peekaboo.boo",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "peekaboo", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["peekaboo"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "peekaboo":
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
        if tool_name != "peekaboo":
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

        if tool_name != "peekaboo":
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

            # Check requirements
            requirements_met, missing = self._check_requirements()
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
            tool_info = self._build_tool_info()
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

    def _check_requirements(self) -> tuple[bool, List[str]]:
        """Check if all requirements are met."""
        missing = []

        # Check binaries
        binaries = ["'peekaboo'"]
        for binary in binaries:
            if not shutil.which(binary):
                missing.append(f"binary:{binary}")

        # Check any_binaries (at least one)
        any_binaries = []
        if any_binaries:
            found = any(shutil.which(b) for b in any_binaries)
            if not found:
                missing.append(f"any_binary:{','.join(any_binaries)}")

        # Check env vars
        env_vars = []
        for env_var in env_vars:
            if not os.environ.get(env_var):
                missing.append(f"env:{env_var}")

        return len(missing) == 0, missing
