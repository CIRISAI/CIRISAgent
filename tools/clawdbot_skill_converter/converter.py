"""
CIRIS Adapter Generator from Clawdbot Skills.

Generates complete CIRIS adapter packages from parsed Clawdbot skills.

FIXES from original:
1. Removed repr() from binary/env var lists - was adding extra quotes
2. Fixed protocol path to runtime.tool.ToolServiceProtocol
3. Removed 'source' field from manifest (not in schema)
4. Changed 'sensitive' to 'sensitivity: HIGH' in configuration
5. Added 'description' to confirm steps (required by schema)
6. Handle class names starting with numbers (e.g., 1password -> OnePassword)
"""

import json
import re
from pathlib import Path
from typing import List

from .parser import ParsedSkill, SkillParser


class SkillConverter:
    """Converts Clawdbot skills to CIRIS adapters."""

    def __init__(self, output_dir: Path):
        """Initialize converter.

        Args:
            output_dir: Base directory for generated adapters (e.g., ciris_adapters/)
        """
        self.output_dir = Path(output_dir)
        self.parser = SkillParser()

    def convert(self, skill: ParsedSkill) -> Path:
        """Convert a parsed skill to a CIRIS adapter.

        Args:
            skill: Parsed skill object

        Returns:
            Path to generated adapter directory
        """
        adapter_name = skill.to_adapter_name()
        adapter_dir = self.output_dir / adapter_name

        # Create adapter directory
        adapter_dir.mkdir(parents=True, exist_ok=True)

        # Generate all files
        self._write_manifest(adapter_dir, skill)
        self._write_init(adapter_dir, skill)
        self._write_adapter(adapter_dir, skill)
        self._write_service(adapter_dir, skill)
        self._write_readme(adapter_dir, skill)

        return adapter_dir

    def convert_from_file(self, skill_path: Path) -> Path:
        """Convert a SKILL.md file to a CIRIS adapter.

        Args:
            skill_path: Path to SKILL.md file

        Returns:
            Path to generated adapter directory
        """
        skill = self.parser.parse_file(skill_path)
        return self.convert(skill)

    def _write_manifest(self, adapter_dir: Path, skill: ParsedSkill) -> None:
        """Generate manifest.json."""
        adapter_name = skill.to_adapter_name()
        tool_name = skill.to_tool_name()
        class_name = skill.to_class_name()

        # Build capabilities list
        capabilities = [f"tool:{tool_name}"]
        if skill.requirements.binaries:
            capabilities.append("requires:binaries")
        if skill.requirements.env_vars:
            capabilities.append("requires:env")

        # Build configuration section - FIX: use 'sensitivity' not 'sensitive'
        configuration = {}
        for env_var in skill.requirements.env_vars:
            config_key = env_var.lower()
            is_secret = "key" in env_var.lower() or "token" in env_var.lower() or "secret" in env_var.lower()
            config_entry = {
                "type": "string",
                "env": env_var,
                "description": f"Environment variable {env_var}",
            }
            if is_secret:
                config_entry["sensitivity"] = "HIGH"  # FIX: was 'sensitive: true'
            configuration[config_key] = config_entry

        manifest = {
            "module": {
                "name": adapter_name,
                "version": "1.0.0",
                "description": skill.description,
                "author": "CIRIS Team (converted from Clawdbot)",
                # FIX: Removed 'source' field - not in manifest schema
                "homepage": skill.homepage,
            },
            "services": [
                {
                    "type": "TOOL",
                    "priority": "NORMAL",
                    "class": f"{adapter_name}.service.{class_name}ToolService",
                    "capabilities": capabilities,
                }
            ],
            "capabilities": capabilities,
            "dependencies": {
                # FIX: Correct protocol path
                "protocols": ["ciris_engine.protocols.services.runtime.tool.ToolServiceProtocol"],
                "schemas": ["ciris_engine.schemas.adapters.tools"],
            },
            "exports": {
                "service_class": f"{adapter_name}.service.{class_name}ToolService",
            },
            "configuration": configuration,
        }

        # Add interactive config if there are required env vars
        if skill.requirements.env_vars:
            manifest["interactive_config"] = self._build_interactive_config(skill)

        manifest_path = adapter_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _build_interactive_config(self, skill: ParsedSkill) -> dict:
        """Build interactive configuration for the manifest."""
        steps = []

        # Add input steps for each env var
        for i, env_var in enumerate(skill.requirements.env_vars):
            is_secret = "key" in env_var.lower() or "token" in env_var.lower() or "secret" in env_var.lower()
            steps.append(
                {
                    "step_id": f"env_{i}",
                    "step_type": "input",
                    "title": f"Configure {env_var}",
                    "description": f"Enter the value for {env_var}",
                    "fields": [
                        {
                            "name": env_var.lower(),
                            "type": "string",
                            "label": env_var,
                            "required": True,
                            "sensitive": is_secret,  # OK in fields - ConfigurationFieldDefinition allows extra
                        }
                    ],
                }
            )

        # FIX: Add description to confirm step (required by ConfigurationStep schema)
        steps.append(
            {
                "step_id": "confirm",
                "step_type": "confirm",
                "title": "Confirm Configuration",
                "description": "Review and confirm your configuration",  # FIX: was missing
            }
        )

        return {
            "required": len(skill.requirements.env_vars) > 0,
            "workflow_type": "simple_config",
            "steps": steps,
            "completion_method": "apply_config",
        }

    def _write_init(self, adapter_dir: Path, skill: ParsedSkill) -> None:
        """Generate __init__.py."""
        class_name = skill.to_class_name()

        content = f'''"""
{class_name} Adapter - Converted from Clawdbot skill: {skill.name}

{skill.description}

Original source: {skill.source_path}
"""

from .adapter import {class_name}Adapter
from .service import {class_name}ToolService

# Export as Adapter for load_adapter() compatibility
Adapter = {class_name}Adapter

__all__ = [
    "Adapter",
    "{class_name}Adapter",
    "{class_name}ToolService",
]
'''
        init_path = adapter_dir / "__init__.py"
        init_path.write_text(content, encoding="utf-8")

    def _write_adapter(self, adapter_dir: Path, skill: ParsedSkill) -> None:
        """Generate adapter.py."""
        class_name = skill.to_class_name()
        adapter_name = skill.to_adapter_name()
        tool_name = skill.to_tool_name()

        content = f'''"""
{class_name} Adapter for CIRIS.

Converted from Clawdbot skill: {skill.name}
{skill.description}
"""

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .service import {class_name}ToolService

logger = logging.getLogger(__name__)


class {class_name}Adapter(Service):
    """
    {class_name} adapter for CIRIS.

    Provides tool guidance for: {skill.description}

    Original Clawdbot skill: {skill.name}
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize {class_name} adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        adapter_config = kwargs.get("adapter_config", {{}})
        self.tool_service = {class_name}ToolService(config=adapter_config)

        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info("{class_name} adapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        return [
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "tool:{tool_name}",
                    "domain:{tool_name}",
                ],
            )
        ]

    async def start(self) -> None:
        """Start the adapter."""
        logger.info("Starting {class_name} adapter")
        await self.tool_service.start()
        self._running = True
        logger.info("{class_name} adapter started")

    async def stop(self) -> None:
        """Stop the adapter."""
        logger.info("Stopping {class_name} adapter")
        self._running = False

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        await self.tool_service.stop()
        logger.info("{class_name} adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle."""
        logger.info("{class_name} adapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("{class_name} adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="{adapter_name}",
            enabled=self._running,
            settings={{}},
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="{adapter_name}",
            adapter_type="{adapter_name}",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = {class_name}Adapter
'''
        adapter_path = adapter_dir / "adapter.py"
        adapter_path.write_text(content, encoding="utf-8")

    def _write_service(self, adapter_dir: Path, skill: ParsedSkill) -> None:
        """Generate service.py with enhanced ToolInfo."""
        class_name = skill.to_class_name()
        tool_name = skill.to_tool_name()

        # Build requirements code
        requirements_code = self._build_requirements_code(skill)
        install_steps_code = self._build_install_steps_code(skill)
        documentation_code = self._build_documentation_code(skill)
        dma_guidance_code = self._build_dma_guidance_code(skill)

        # FIX: Build the actual lists without repr() - just the string values
        binaries_list = skill.requirements.binaries
        any_binaries_list = skill.requirements.any_binaries
        env_vars_list = skill.requirements.env_vars

        content = f'''"""
{class_name} Tool Service for CIRIS.

Converted from Clawdbot skill: {skill.name}
{skill.description}

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


class {class_name}ToolService:
    """
    {class_name} tool service providing skill-based guidance.

    Original skill: {skill.name}
    Description: {skill.description}
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {{}}
        self._call_count = 0
        logger.info("{class_name}ToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("{class_name}ToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("{class_name}ToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="{tool_name}",
            description="""{self._escape_string(skill.description)}""",
            parameters=ToolParameterSchema(
                type="object",
                properties={{
                    "command": {{
                        "type": "string",
                        "description": "The command to execute (will be validated against skill guidance)",
                    }},
                    "working_dir": {{
                        "type": "string",
                        "description": "Working directory for command execution (optional)",
                    }},
                }},
                required=["command"],
            ),
            category="skill",
            when_to_use="""{self._escape_string(self._extract_when_to_use(skill))}""",
            {requirements_code}
            {install_steps_code}
            {documentation_code}
            {dma_guidance_code}
            tags={self._build_tags(skill)},
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["{tool_name}"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "{tool_name}":
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
        if tool_name != "{tool_name}":
            return False
        return "command" in parameters

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of previously executed tool."""
        return None

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return list of available tools (legacy format)."""
        tool_info = self._build_tool_info()
        return [
            {{
                "name": tool_info.name,
                "description": tool_info.description,
                "parameters": tool_info.parameters.model_dump() if tool_info.parameters else {{}},
            }}
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

        if tool_name != "{tool_name}":
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown tool: {{tool_name}}",
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
                    data={{"missing_requirements": missing}},
                    error=f"Missing requirements: {{', '.join(missing)}}",
                    correlation_id=correlation_id,
                )

            # Return guidance for executing the command
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data={{
                    "command": command,
                    "guidance": "Use bash tool to execute this command",
                    "skill_instructions": tool_info.documentation.quick_start if tool_info.documentation else None,
                    "requirements_met": requirements_met,
                }},
                error=None,
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(f"Error executing tool {{tool_name}}: {{e}}")
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
                missing.append(f"binary:{{bin_req.name}}")

        # Check any_binaries (at least one)
        if req.any_binaries:
            found = any(shutil.which(b.name) for b in req.any_binaries)
            if not found:
                names = [b.name for b in req.any_binaries]
                missing.append(f"any_binary:{{','.join(names)}}")

        # Check env vars
        for env_req in req.env_vars:
            if not os.environ.get(env_req.name):
                missing.append(f"env:{{env_req.name}}")

        # Check config keys (skip for now - would need config service)
        # for config_req in req.config_keys:
        #     ...

        return len(missing) == 0, missing
'''
        service_path = adapter_dir / "service.py"
        service_path.write_text(content, encoding="utf-8")

    def _write_readme(self, adapter_dir: Path, skill: ParsedSkill) -> None:
        """Generate README.md."""
        class_name = skill.to_class_name()
        adapter_name = skill.to_adapter_name()

        # Build requirements section
        req_lines = []
        if skill.requirements.binaries:
            req_lines.append(f"- **Binaries**: {', '.join(skill.requirements.binaries)}")
        if skill.requirements.any_binaries:
            req_lines.append(f"- **Any of**: {', '.join(skill.requirements.any_binaries)}")
        if skill.requirements.env_vars:
            req_lines.append(f"- **Environment**: {', '.join(skill.requirements.env_vars)}")
        if skill.requirements.platforms:
            req_lines.append(f"- **Platforms**: {', '.join(skill.requirements.platforms)}")

        requirements_section = "\n".join(req_lines) if req_lines else "None"

        content = f"""# {class_name} Adapter

> Converted from Clawdbot skill: `{skill.name}`

{skill.description}

## Requirements

{requirements_section}

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter {adapter_name}
```

## Original Skill Documentation

{skill.detailed_instructions}

---

*Converted by CIRIS Skill Converter*
*Source: {skill.source_path}*
"""
        readme_path = adapter_dir / "README.md"
        readme_path.write_text(content, encoding="utf-8")

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _escape_string(self, s: str) -> str:
        """Escape a string for use in Python code."""
        if not s:
            return ""
        # Replace backslashes first, then quotes
        s = s.replace("\\", "\\\\")
        s = s.replace('"', '\\"')
        s = s.replace("\n", "\\n")
        return s

    def _extract_when_to_use(self, skill: ParsedSkill) -> str:
        """Extract when_to_use guidance from skill description."""
        desc = skill.description
        if len(desc) > 100:
            desc = desc[:100] + "..."
        return f"When you need to {desc.lower()}"

    def _build_tags(self, skill: ParsedSkill) -> List[str]:
        """Build tags list for the skill."""
        tags = ["skill", "clawdbot"]
        tags.append(skill.to_tool_name())
        if skill.requirements.binaries:
            tags.append("cli")
        if skill.requirements.env_vars:
            tags.append("api")
        return tags

    def _build_requirements_code(self, skill: ParsedSkill) -> str:
        """Build Python code for ToolRequirements."""
        if not any(
            [
                skill.requirements.binaries,
                skill.requirements.any_binaries,
                skill.requirements.env_vars,
                skill.requirements.config_keys,
                skill.requirements.platforms,
            ]
        ):
            return "requirements=None,"

        lines = ["requirements=ToolRequirements("]

        if skill.requirements.binaries:
            lines.append("    binaries=[")
            for b in skill.requirements.binaries:
                lines.append(f'        BinaryRequirement(name="{b}"),')
            lines.append("    ],")

        if skill.requirements.any_binaries:
            lines.append("    any_binaries=[")
            for b in skill.requirements.any_binaries:
                lines.append(f'        BinaryRequirement(name="{b}"),')
            lines.append("    ],")

        if skill.requirements.env_vars:
            lines.append("    env_vars=[")
            for e in skill.requirements.env_vars:
                lines.append(f'        EnvVarRequirement(name="{e}"),')
            lines.append("    ],")

        if skill.requirements.config_keys:
            lines.append("    config_keys=[")
            for c in skill.requirements.config_keys:
                lines.append(f'        ConfigRequirement(key="{c}"),')
            lines.append("    ],")

        if skill.requirements.platforms:
            lines.append(f"    platforms={skill.requirements.platforms},")

        lines.append("),")
        return "\n            ".join(lines)

    def _build_install_steps_code(self, skill: ParsedSkill) -> str:
        """Build Python code for install_steps."""
        if not skill.install_steps:
            return "install_steps=[],"

        lines = ["install_steps=["]
        for step in skill.install_steps:
            step_parts = [
                f'id="{step.id}"',
                f'kind="{step.kind}"',
                f'label="{self._escape_string(step.label)}"',
            ]
            if step.formula:
                step_parts.append(f'formula="{step.formula}"')
            if step.package:
                step_parts.append(f'package="{step.package}"')
            if step.binaries:
                step_parts.append(f"provides_binaries={step.binaries}")
            if step.platforms:
                step_parts.append(f"platforms={step.platforms}")

            lines.append(f"    InstallStep({', '.join(step_parts)}),")
        lines.append("],")
        return "\n            ".join(lines)

    def _build_documentation_code(self, skill: ParsedSkill) -> str:
        """Build Python code for ToolDocumentation."""
        # Extract quick start from first few lines of instructions
        quick_start = ""
        if skill.detailed_instructions:
            lines = skill.detailed_instructions.split("\n")
            # Find first non-header, non-empty line
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    quick_start = stripped[:200]
                    break

        # Escape the detailed instructions for embedding
        escaped_instructions = self._escape_string(skill.detailed_instructions[:5000])

        lines = ["documentation=ToolDocumentation("]
        if quick_start:
            lines.append(f'    quick_start="{self._escape_string(quick_start)}",')
        lines.append(f'    detailed_instructions="""{escaped_instructions}""",')
        lines.append("    examples=[],")  # Could parse code blocks later
        lines.append("    gotchas=[],")  # Could parse warnings later
        if skill.homepage:
            lines.append(f'    homepage="{skill.homepage}",')
        lines.append("),")
        return "\n            ".join(lines)

    def _build_dma_guidance_code(self, skill: ParsedSkill) -> str:
        """Build Python code for ToolDMAGuidance."""
        lines = ["dma_guidance=ToolDMAGuidance("]

        # Extract any warnings from instructions for when_not_to_use
        when_not_to_use = None
        if skill.detailed_instructions:
            if "\u26a0\ufe0f" in skill.detailed_instructions or "WARNING" in skill.detailed_instructions.upper():
                when_not_to_use = "Review warnings in documentation before use"

        if when_not_to_use:
            lines.append(f'    when_not_to_use="{when_not_to_use}",')

        # If it requires secrets, note that
        if skill.requirements.env_vars:
            lines.append('    ethical_considerations="Requires API credentials - ensure proper authorization",')

        lines.append("    requires_approval=False,")
        lines.append("),")
        return "\n            ".join(lines)


def convert_skill(skill_path: Path, output_dir: Path) -> Path:
    """Convert a single skill file to a CIRIS adapter.

    Args:
        skill_path: Path to SKILL.md file
        output_dir: Output directory for generated adapter

    Returns:
        Path to generated adapter directory
    """
    converter = SkillConverter(output_dir)
    return converter.convert_from_file(skill_path)


def convert_skills_batch(skills_dir: Path, output_dir: Path) -> List[Path]:
    """Convert all skills in a directory to CIRIS adapters.

    Args:
        skills_dir: Directory containing skill subdirectories
        output_dir: Output directory for generated adapters

    Returns:
        List of paths to generated adapter directories
    """
    converter = SkillConverter(output_dir)
    parser = SkillParser()

    skills = parser.parse_directory(skills_dir)
    results = []

    for skill in skills:
        try:
            adapter_path = converter.convert(skill)
            results.append(adapter_path)
            print(f"\u2713 Converted {skill.name} \u2192 {adapter_path.name}")
        except Exception as e:
            print(f"\u2717 Failed to convert {skill.name}: {e}")

    return results
