"""
SkillCreator Tool Service for CIRIS.

Converted from Clawdbot skill: skill-creator
Create or update AgentSkills. Use when designing, structuring, or packaging skills with scripts, references, and assets.

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


class SkillCreatorToolService:
    """
    SkillCreator tool service providing skill-based guidance.

    Original skill: skill-creator
    Description: Create or update AgentSkills. Use when designing, structuring, or packaging skills with scripts, references, and assets.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("SkillCreatorToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("SkillCreatorToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("SkillCreatorToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="skill_creator",
            description="""Create or update AgentSkills. Use when designing, structuring, or packaging skills with scripts, references, and assets.""",
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
            when_to_use="""When you need to create or update agentskills. use when designing, structuring, or packaging skills with scripts, ref...""",
            requirements=None,
            install_steps=[],
            documentation=ToolDocumentation(
                quick_start="This skill provides guidance for creating effective skills.",
                detailed_instructions="""# Skill Creator\n\nThis skill provides guidance for creating effective skills.\n\n## About Skills\n\nSkills are modular, self-contained packages that extend Codex's capabilities by providing\nspecialized knowledge, workflows, and tools. Think of them as \"onboarding guides\" for specific\ndomains or tasks—they transform Codex from a general-purpose agent into a specialized agent\nequipped with procedural knowledge that no model can fully possess.\n\n### What Skills Provide\n\n1. Specialized workflows - Multi-step procedures for specific domains\n2. Tool integrations - Instructions for working with specific file formats or APIs\n3. Domain expertise - Company-specific knowledge, schemas, business logic\n4. Bundled resources - Scripts, references, and assets for complex and repetitive tasks\n\n## Core Principles\n\n### Concise is Key\n\nThe context window is a public good. Skills share the context window with everything else Codex needs: system prompt, conversation history, other Skills' metadata, and the actual user request.\n\n**Default assumption: Codex is already very smart.** Only add context Codex doesn't already have. Challenge each piece of information: \"Does Codex really need this explanation?\" and \"Does this paragraph justify its token cost?\"\n\nPrefer concise examples over verbose explanations.\n\n### Set Appropriate Degrees of Freedom\n\nMatch the level of specificity to the task's fragility and variability:\n\n**High freedom (text-based instructions)**: Use when multiple approaches are valid, decisions depend on context, or heuristics guide the approach.\n\n**Medium freedom (pseudocode or scripts with parameters)**: Use when a preferred pattern exists, some variation is acceptable, or configuration affects behavior.\n\n**Low freedom (specific scripts, few parameters)**: Use when operations are fragile and error-prone, consistency is critical, or a specific sequence must be followed.\n\nThink of Codex as exploring a path: a narrow bridge with cliffs needs specific guardrails (low freedom), while an open field allows many routes (high freedom).\n\n### Anatomy of a Skill\n\nEvery skill consists of a required SKILL.md file and optional bundled resources:\n\n```\nskill-name/\n├── SKILL.md (required)\n│   ├── YAML frontmatter metadata (required)\n│   │   ├── name: (required)\n│   │   └── description: (required)\n│   └── Markdown instructions (required)\n└── Bundled Resources (optional)\n    ├── scripts/          - Executable code (Python/Bash/etc.)\n    ├── references/       - Documentation intended to be loaded into context as needed\n    └── assets/           - Files used in output (templates, icons, fonts, etc.)\n```\n\n#### SKILL.md (required)\n\nEvery SKILL.md consists of:\n\n- **Frontmatter** (YAML): Contains `name` and `description` fields. These are the only fields that Codex reads to determine when the skill gets used, thus it is very important to be clear and comprehensive in describing what the skill is, and when it should be used.\n- **Body** (Markdown): Instructions and guidance for using the skill. Only loaded AFTER the skill triggers (if at all).\n\n#### Bundled Resources (optional)\n\n##### Scripts (`scripts/`)\n\nExecutable code (Python/Bash/etc.) for tasks that require deterministic reliability or are repeatedly rewritten.\n\n- **When to include**: When the same code is being rewritten repeatedly or deterministic reliability is needed\n- **Example**: `scripts/rotate_pdf.py` for PDF rotation tasks\n- **Benefits**: Token efficient, deterministic, may be executed without loading into context\n- **Note**: Scripts may still need to be read by Codex for patching or environment-specific adjustments\n\n##### References (`references/`)\n\nDocumentation and reference material intended to be loaded as needed into context to inform Codex's process and thinking.\n\n- **When to include**: For documentation that Codex should reference while working\n- **Examples**: `references/finance.md` for financial schemas, `references/mnda.md` for company NDA template, `references/policies.md` for company policies, `references/api_docs.md` for API specifications\n- **Use cases**: Database schemas, API documentation, domain knowledge, company policies, detailed workflow guides\n- **Benefits**: Keeps SKILL.md lean, loaded only when Codex determines it's needed\n- **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md\n- **Avoid duplication**: Information should live in either SKILL.md or references files, not both. Prefer references files for detailed information unless it's truly core to the skill—this keeps SKILL.md lean while making information discoverable without hogging the context window. Keep only essential procedural instructions and workflow guidance in SKILL.md; move detailed reference material, schemas, and examples to references files.\n\n##### Assets (`assets/`)\n\nFiles not intended to be loaded into context, but rather used within the output Codex produces.\n\n- **When to include**: When the skill needs files that will be used in the final output\n- **""",
                examples=[],
                gotchas=[],
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "skill_creator"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["skill_creator"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "skill_creator":
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
        if tool_name != "skill_creator":
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

        if tool_name != "skill_creator":
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
        binaries = []
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
