"""
Bird Tool Service for CIRIS.

Converted from Clawdbot skill: bird
X/Twitter CLI for reading, searching, posting, and engagement via cookies.

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


class BirdToolService:
    """
    Bird tool service providing skill-based guidance.

    Original skill: bird
    Description: X/Twitter CLI for reading, searching, posting, and engagement via cookies.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("BirdToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("BirdToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("BirdToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="bird",
            description="""X/Twitter CLI for reading, searching, posting, and engagement via cookies.""",
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
            when_to_use="""When you need to x/twitter cli for reading, searching, posting, and engagement via cookies.""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="bird"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install bird (brew)",
                    formula="steipete/tap/bird",
                    provides_binaries=["bird"],
                ),
                InstallStep(
                    id="npm",
                    kind="node",
                    label="Install bird (npm)",
                    package="@steipete/bird",
                    provides_binaries=["bird"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Fast X/Twitter CLI using GraphQL + cookie auth.",
                detailed_instructions="""# bird 🐦\n\nFast X/Twitter CLI using GraphQL + cookie auth.\n\n## Install\n\n```bash\n# npm/pnpm/bun\nnpm install -g @steipete/bird\n\n# Homebrew (macOS, prebuilt binary)\nbrew install steipete/tap/bird\n\n# One-shot (no install)\nbunx @steipete/bird whoami\n```\n\n## Authentication\n\n`bird` uses cookie-based auth.\n\nUse `--auth-token` / `--ct0` to pass cookies directly, or `--cookie-source` for browser cookies.\n\nRun `bird check` to see which source is active. For Arc/Brave, use `--chrome-profile-dir <path>`.\n\n## Commands\n\n### Account & Auth\n\n```bash\nbird whoami                    # Show logged-in account\nbird check                     # Show credential sources\nbird query-ids --fresh         # Refresh GraphQL query ID cache\n```\n\n### Reading Tweets\n\n```bash\nbird read <url-or-id>          # Read a single tweet\nbird <url-or-id>               # Shorthand for read\nbird thread <url-or-id>        # Full conversation thread\nbird replies <url-or-id>       # List replies to a tweet\n```\n\n### Timelines\n\n```bash\nbird home                      # Home timeline (For You)\nbird home --following          # Following timeline\nbird user-tweets @handle -n 20 # User's profile timeline\nbird mentions                  # Tweets mentioning you\nbird mentions --user @handle   # Mentions of another user\n```\n\n### Search\n\n```bash\nbird search \"query\" -n 10\nbird search \"from:steipete\" --all --max-pages 3\n```\n\n### News & Trending\n\n```bash\nbird news -n 10                # AI-curated from Explore tabs\nbird news --ai-only            # Filter to AI-curated only\nbird news --sports             # Sports tab\nbird news --with-tweets        # Include related tweets\nbird trending                  # Alias for news\n```\n\n### Lists\n\n```bash\nbird lists                     # Your lists\nbird lists --member-of         # Lists you're a member of\nbird list-timeline <id> -n 20  # Tweets from a list\n```\n\n### Bookmarks & Likes\n\n```bash\nbird bookmarks -n 10\nbird bookmarks --folder-id <id>           # Specific folder\nbird bookmarks --include-parent           # Include parent tweet\nbird bookmarks --author-chain             # Author's self-reply chain\nbird bookmarks --full-chain-only          # Full reply chain\nbird unbookmark <url-or-id>\nbird likes -n 10\n```\n\n### Social Graph\n\n```bash\nbird following -n 20           # Users you follow\nbird followers -n 20           # Users following you\nbird following --user <id>     # Another user's following\nbird about @handle             # Account origin/location info\n```\n\n### Engagement Actions\n\n```bash\nbird follow @handle            # Follow a user\nbird unfollow @handle          # Unfollow a user\n```\n\n### Posting\n\n```bash\nbird tweet \"hello world\"\nbird reply <url-or-id> \"nice thread!\"\nbird tweet \"check this out\" --media image.png --alt \"description\"\n```\n\n**⚠️ Posting risks**: Posting is more likely to be rate limited; if blocked, use the browser tool instead.\n\n## Media Uploads\n\n```bash\nbird tweet \"hi\" --media img.png --alt \"description\"\nbird tweet \"pics\" --media a.jpg --media b.jpg  # Up to 4 images\nbird tweet \"video\" --media clip.mp4            # Or 1 video\n```\n\n## Pagination\n\nCommands supporting pagination: `replies`, `thread`, `search`, `bookmarks`, `likes`, `list-timeline`, `following`, `followers`, `user-tweets`\n\n```bash\nbird bookmarks --all                    # Fetch all pages\nbird bookmarks --max-pages 3            # Limit pages\nbird bookmarks --cursor <cursor>        # Resume from cursor\nbird replies <id> --all --delay 1000    # Delay between pages (ms)\n```\n\n## Output Options\n\n```bash\n--json          # JSON output\n--json-full     # JSON with raw API response\n--plain         # No emoji, no color (script-friendly)\n--no-emoji      # Disable emoji\n--no-color      # Disable ANSI colors (or set NO_COLOR=1)\n--quote-depth n # Max quoted tweet depth in JSON (default: 1)\n```\n\n## Global Options\n\n```bash\n--auth-token <token>       # Set auth_token cookie\n--ct0 <token>              # Set ct0 cookie\n--cookie-source <source>   # Cookie source for browser cookies (repeatable)\n--chrome-profile <name>    # Chrome profile name\n--chrome-profile-dir <path> # Chrome/Chromium profile dir or cookie DB path\n--firefox-profile <name>   # Firefox profile\n--timeout <ms>             # Request timeout\n--cookie-timeout <ms>      # Cookie extraction timeout\n```\n\n## Config File\n\n`~/.config/bird/config.json5` (global) or `./.birdrc.json5` (project):\n\n```json5\n{\n  cookieSource: [\"chrome\"],\n  chromeProfileDir: \"/path/to/Arc/Profile\",\n  timeoutMs: 20000,\n  quoteDepth: 1\n}\n```\n\nEnvironment variables: `BIRD_TIMEOUT_MS`, `BIRD_COOKIE_TIMEOUT_MS`, `BIRD_QUOTE_DEPTH`\n\n## Troubleshooting\n\n### Query IDs stale (404 errors)\n```bash\nbird query-ids --fresh\n```\n\n### Cookie extraction fails\n- Check browser is logged into X\n- Try different `--cookie-source`\n- For Arc/Brave: use `--chrome-profile-dir`\n\n---\n\n**TL;DR**: Read/search/engage with CLI. Post carefully or use browser. 🐦""",
                examples=[],
                gotchas=[],
                homepage="https://bird.fast",
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Review warnings in documentation before use",
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "bird", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["bird"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "bird":
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
        if tool_name != "bird":
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

        if tool_name != "bird":
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
        binaries = ["'bird'"]
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
