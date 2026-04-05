"""Skill-to-adapter converter.

Transforms a parsed OpenClaw skill into a CIRIS adapter directory
that can be loaded by the AdapterDiscoveryService.

Generated adapters are placed in ~/ciris/adapters/ (user-installed path)
so they're automatically discovered on next startup.
"""

import json
import logging
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

from .parser import ParsedSkill, SkillInstallSpec

logger = logging.getLogger(__name__)

# Default user adapter directory
_USER_ADAPTERS_DIR = Path.home() / "ciris" / "adapters"


def _sanitize_module_name(skill_name: str) -> str:
    """Convert a skill name to a valid Python module name.

    'my-cool-skill' -> 'imported_my_cool_skill'
    """
    sanitized = re.sub(r"[^a-z0-9_]", "_", skill_name.lower())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return f"imported_{sanitized}"


def _map_install_kind(kind: str) -> str:
    """Map OpenClaw install kinds to CIRIS InstallStep kinds."""
    mapping = {
        "brew": "brew",
        "node": "npm",
        "go": "manual",
        "uv": "pip",
        "pip": "pip",
        "apt": "apt",
        "manual": "manual",
    }
    return mapping.get(kind, "manual")


def _build_install_steps(specs: List[SkillInstallSpec]) -> List[Dict[str, Any]]:
    """Convert OpenClaw install specs to CIRIS InstallStep dicts.

    Maps all OpenClaw install fields to CIRIS InstallStep fields.
    For 'download' kind specs, the URL is stored in the 'url' field
    and a manual command is generated.
    """
    steps = []
    for i, spec in enumerate(specs):
        label = getattr(spec, "label", None) or f"Install via {spec.kind}"
        step_id = getattr(spec, "id", None) or f"install_{i}"
        step: Dict[str, Any] = {
            "id": step_id,
            "kind": _map_install_kind(spec.kind),
            "label": label,
            "provides_binaries": spec.bins,
        }
        if spec.formula:
            step["formula"] = spec.formula
        if spec.package:
            step["package"] = spec.package
        # Handle download-type specs: url, archive, stripComponents, targetDir
        url = getattr(spec, "url", None)
        if url:
            step["url"] = url
            # Build a manual command for download specs
            archive = getattr(spec, "archive", None)
            target_dir = getattr(spec, "targetDir", None) or getattr(spec, "target_dir", None)
            strip = getattr(spec, "stripComponents", None) or getattr(spec, "strip_components", None)
            if archive and target_dir:
                strip_flag = f" --strip-components={strip}" if strip else ""
                step["command"] = f"curl -L {url} | tar xz{strip_flag} -C {target_dir}"
                step["kind"] = "manual"
        steps.append(step)
    return steps


def _generate_alias_code(skill: ParsedSkill) -> str:
    """Generate Python code lines for registering tool aliases.

    Registers aliases for:
    - skillKey (OpenClaw invocation override)
    - command_tool (direct dispatch tool name)
    - bare skill name (e.g., "todoist-cli" -> "skill:todoist-cli")
    """
    lines = []
    canonical = f"skill:{skill.name}"
    registered: set[str] = set()

    # skillKey alias (e.g., "todoist" -> "skill:todoist-cli")
    if skill.metadata and skill.metadata.skill_key:
        key = skill.metadata.skill_key
        if key != skill.name and key not in registered:
            lines.append(f'                        tool_bus.register_tool_alias("{key}", "{canonical}")')
            registered.add(key)

    # command_tool alias (e.g., "todoist" -> "skill:todoist-cli")
    if skill.command_tool:
        tool = skill.command_tool
        if tool != skill.name and tool not in registered:
            lines.append(f'                        tool_bus.register_tool_alias("{tool}", "{canonical}")')
            registered.add(tool)

    # Always register bare name as alias (e.g., "todoist-cli" -> "skill:todoist-cli")
    lines.append(f'                        tool_bus.register_tool_alias("{skill.name}", "{canonical}")')

    return "\n".join(lines) if lines else "                        pass"


class SkillToAdapterConverter:
    """Converts parsed OpenClaw skills to CIRIS adapter directories."""

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize converter.

        Args:
            output_dir: Directory where adapters will be created.
                        Defaults to ~/.ciris/adapters/
        """
        self.output_dir = output_dir or _USER_ADAPTERS_DIR

    def convert(self, skill: ParsedSkill) -> Path:
        """Convert a parsed skill into a CIRIS adapter directory.

        Creates:
            {output_dir}/{module_name}/
            ├── __init__.py
            ├── adapter.py
            ├── services.py
            ├── manifest.json
            ├── SKILL.md          (original skill content)
            └── supporting/       (any supporting files)

        Args:
            skill: The parsed OpenClaw skill

        Returns:
            Path to the created adapter directory
        """
        module_name = _sanitize_module_name(skill.name)
        adapter_dir = self.output_dir / module_name

        # Create directories
        adapter_dir.mkdir(parents=True, exist_ok=True)

        # Generate all files
        self._write_manifest(adapter_dir, module_name, skill)
        self._write_init(adapter_dir, module_name)
        self._write_adapter(adapter_dir, module_name, skill)
        self._write_services(adapter_dir, skill)
        self._write_original_skill(adapter_dir, skill)
        self._write_supporting_files(adapter_dir, skill)

        logger.info(f"Created adapter '{module_name}' at {adapter_dir}")
        return adapter_dir

    def _write_manifest(self, adapter_dir: Path, module_name: str, skill: ParsedSkill) -> None:
        """Generate manifest.json for the adapter."""
        # Build capabilities list
        tool_name = f"skill:{skill.name}"
        capabilities = [f"tool:{tool_name}"]

        # Build configuration parameters from required env vars
        configuration: Dict[str, Any] = {}
        if skill.metadata and skill.metadata.requires:
            for env_var in skill.metadata.requires.env:
                configuration[env_var.lower()] = {
                    "type": "string",
                    "env": env_var,
                    "description": f"Required: {env_var}",
                    "required": True,
                }

        # Map OpenClaw OS names to CIRIS platform requirement strings
        platform_requirements: Optional[List[str]] = None
        if skill.metadata and skill.metadata.os:
            platform_requirements = skill.metadata.os  # e.g., ["linux", "darwin"]

        manifest: Dict[str, Any] = {
            "module": {
                "name": module_name,
                "version": skill.version,
                "description": skill.description or f"Imported OpenClaw skill: {skill.name}",
                "author": "OpenClaw Import",
                "homepage": skill.homepage,
                "auto_load": True,
                "opt_in_required": False,
                "requires_consent": False,
            },
            "services": [
                {
                    "type": "TOOL",
                    "priority": "NORMAL",
                    "class": f"{module_name}.services.ImportedSkillToolService",
                    "capabilities": capabilities,
                }
            ],
            "capabilities": capabilities,
            "configuration": configuration if configuration else None,
            "metadata": {
                "imported_from": "openclaw",
                "original_skill_name": skill.name,
                "source_url": skill.source_url,
                "openclaw_always": skill.metadata.always if skill.metadata else False,
                "openclaw_skill_key": skill.metadata.skill_key if skill.metadata else None,
                "openclaw_emoji": skill.metadata.emoji if skill.metadata else None,
                "disable_model_invocation": skill.disable_model_invocation,
                "command_dispatch": skill.command_dispatch,
                "command_tool": skill.command_tool,
                "command_arg_mode": skill.command_arg_mode,
            },
        }

        # Add CLI dependencies from required binaries
        cli_deps: List[str] = []
        if skill.metadata and skill.metadata.requires:
            cli_deps.extend(skill.metadata.requires.bins)
        if cli_deps:
            manifest["cli_dependencies"] = cli_deps

        # Add platform requirements if OS restrictions exist
        if platform_requirements:
            manifest["platform_requirements"] = platform_requirements

        # Remove None values
        manifest = {k: v for k, v in manifest.items() if v is not None}

        (adapter_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def _write_init(self, adapter_dir: Path, module_name: str) -> None:
        """Generate __init__.py."""
        content = f'"""Imported OpenClaw skill adapter: {module_name}."""\n'
        (adapter_dir / "__init__.py").write_text(content, encoding="utf-8")

    def _write_adapter(self, adapter_dir: Path, module_name: str, skill: ParsedSkill) -> None:
        """Generate adapter.py implementing BaseAdapterProtocol."""
        content = textwrap.dedent(
            f'''\
            """Adapter for imported OpenClaw skill: {skill.name}."""

            import asyncio
            import logging
            from typing import Any, List, Optional

            from ciris_engine.logic.adapters.base import Service
            from ciris_engine.logic.registries.base import Priority
            from ciris_engine.schemas.adapters import AdapterServiceRegistration
            from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
            from ciris_engine.schemas.runtime.enums import ServiceType

            from .services import ImportedSkillToolService

            logger = logging.getLogger(__name__)


            class ImportedSkillAdapter(Service):
                """Adapter wrapping the imported OpenClaw skill: {skill.name}."""

                def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
                    super().__init__(config=kwargs.get("adapter_config"))
                    self.runtime = runtime
                    self.context = context
                    self.tool_service = ImportedSkillToolService(config=kwargs.get("adapter_config", {{}}))
                    self._running = False

                def get_services_to_register(self) -> List[AdapterServiceRegistration]:
                    return [
                        AdapterServiceRegistration(
                            service_type=ServiceType.TOOL,
                            provider=self.tool_service,
                            priority=Priority.NORMAL,
                            capabilities=["tool:skill:{skill.name}"],
                        )
                    ]

                async def start(self) -> None:
                    await self.tool_service.start()
                    self._running = True
                    self._register_tool_aliases()
                    logger.info("Imported skill adapter '{skill.name}' started")

                def _register_tool_aliases(self) -> None:
                    """Register tool aliases from OpenClaw skillKey if available."""
                    try:
                        bus_manager = getattr(self.runtime, "bus_manager", None)
                        if not bus_manager:
                            bus_manager = getattr(self.context, "bus_manager", None)
                        if not bus_manager:
                            return
                        tool_bus = getattr(bus_manager, "tool_bus", None)
                        if not tool_bus or not hasattr(tool_bus, "register_tool_alias"):
                            return
{_generate_alias_code(skill)}
                    except Exception as e:
                        logger.debug(f"Could not register tool aliases: {{e}}")

                async def stop(self) -> None:
                    self._running = False
                    await self.tool_service.stop()
                    logger.info("Imported skill adapter '{skill.name}' stopped")

                async def run_lifecycle(self, agent_task: Any) -> None:
                    try:
                        await agent_task
                    except asyncio.CancelledError:
                        pass
                    finally:
                        await self.stop()

                def get_config(self) -> AdapterConfig:
                    return AdapterConfig(
                        adapter_type="{module_name}",
                        enabled=self._running,
                        settings={{}},
                    )

                def get_status(self) -> RuntimeAdapterStatus:
                    return RuntimeAdapterStatus(
                        adapter_id="{module_name}",
                        adapter_type="{module_name}",
                        is_running=self._running,
                        loaded_at=None,
                        error=None,
                    )


            Adapter = ImportedSkillAdapter
        '''
        )
        (adapter_dir / "adapter.py").write_text(content, encoding="utf-8")

    def _write_services(self, adapter_dir: Path, skill: ParsedSkill) -> None:
        """Generate services.py with a ToolService that exposes the skill."""
        # Build requirements block with all OpenClaw requirement types
        # NOTE: Indentation here must match where it's inserted in the template (line ~434)
        requirements_code = "None"
        if skill.metadata and skill.metadata.requires:
            req = skill.metadata.requires
            bin_list = repr(req.bins) if req.bins else "[]"
            any_bin_list = repr(req.any_bins) if req.any_bins else "[]"
            env_list = repr(req.env) if req.env else "[]"
            config_list = repr(req.config) if req.config else "[]"
            platforms_list = repr(skill.metadata.os) if skill.metadata.os else "[]"
            requirements_code = (
                f"ToolRequirements(\n"
                f"                            binaries=[BinaryRequirement(name=b) for b in {bin_list}],\n"
                f"                            any_binaries=[BinaryRequirement(name=b) for b in {any_bin_list}],\n"
                f"                            env_vars=[EnvVarRequirement(name=e) for e in {env_list}],\n"
                f"                            config_keys=[ConfigRequirement(key=c) for c in {config_list}],\n"
                f"                            platforms={platforms_list},\n"
                f"                        )"
            )

        # Build install steps
        install_steps_code = "[]"
        if skill.metadata and skill.metadata.install:
            steps = _build_install_steps(skill.metadata.install)
            install_steps_code = repr(steps)

        # Escape the instructions for embedding as a Python string
        escaped_instructions = skill.instructions.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')

        content = textwrap.dedent(
            f'''\
            """Tool service for imported OpenClaw skill: {skill.name}."""

            import logging
            import os
            import subprocess
            from pathlib import Path
            from typing import Any, Dict, List, Optional
            from uuid import uuid4

            from ciris_engine.schemas.adapters.tools import (
                BinaryRequirement,
                ConfigRequirement,
                EnvVarRequirement,
                InstallStep,
                ToolDocumentation,
                ToolExecutionResult,
                ToolExecutionStatus,
                ToolInfo,
                ToolParameterSchema,
                ToolRequirements,
            )

            logger = logging.getLogger(__name__)

            # The original skill instructions (AI directive)
            SKILL_INSTRUCTIONS = """{escaped_instructions}"""

            # Supporting file directory
            _SUPPORTING_DIR = Path(__file__).parent / "supporting"


            class ImportedSkillToolService:
                """Tool service exposing the imported OpenClaw skill as CIRIS tools.

                Provides:
                - skill:{skill.name}: Execute the skill\'s instructions
                - skill:{skill.name}:info: Get skill metadata and instructions
                """

                TOOL_DEFINITIONS: Dict[str, ToolInfo] = {{
                    "skill:{skill.name}": ToolInfo(
                        name="skill:{skill.name}",
                        description={repr(skill.description or f"Imported skill: {skill.name}")},
                        parameters=ToolParameterSchema(
                            type="object",
                            properties={{
                                "input": {{
                                    "type": "string",
                                    "description": "Input to pass to the skill",
                                }},
                                "args": {{
                                    "type": "object",
                                    "description": "Additional arguments for the skill",
                                }},
                            }},
                            required=["input"],
                        ),
                        category="imported_skill",
                        when_to_use={repr(skill.description or f"When you need to use the {skill.name} skill")},
                        context_enrichment={bool(skill.metadata and skill.metadata.always)},
                        context_enrichment_params={{"input": "status"}} if {bool(skill.metadata and skill.metadata.always)} else None,
                        requirements={requirements_code},
                        tags={repr(self._build_tags(skill))},
                        version={repr(skill.version)},
                        documentation=ToolDocumentation(
                            quick_start=f"Imported OpenClaw skill: {skill.name}",
                            detailed_instructions=SKILL_INSTRUCTIONS,
                            homepage={repr(skill.homepage)},
                        ),
                        install_steps=[InstallStep(**s) for s in {install_steps_code}],
                    ),
                    "skill:{skill.name}:info": ToolInfo(
                        name="skill:{skill.name}:info",
                        description="Get instructions and metadata for this imported skill",
                        parameters=ToolParameterSchema(
                            type="object",
                            properties={{}},
                            required=[],
                        ),
                        category="imported_skill",
                        context_enrichment={not skill.disable_model_invocation},
                        context_enrichment_params={{}},
                        tags=["imported", "openclaw", "info"],
                    ),
                }}

                def __init__(self, config: Any = None) -> None:
                    self._config = config or {{}}
                    self._call_count = 0

                async def start(self) -> None:
                    logger.info("ImportedSkillToolService for '{skill.name}' started")

                async def stop(self) -> None:
                    logger.info("ImportedSkillToolService for '{skill.name}' stopped")

                async def execute_tool(
                    self, tool_name: str, parameters: Dict[str, Any]
                ) -> ToolExecutionResult:
                    """Execute a skill tool."""
                    self._call_count += 1
                    correlation_id = str(uuid4())

                    if tool_name == "skill:{skill.name}:info":
                        return ToolExecutionResult(
                            tool_name=tool_name,
                            status=ToolExecutionStatus.COMPLETED,
                            success=True,
                            data={{
                                "name": {repr(skill.name)},
                                "description": {repr(skill.description)},
                                "version": {repr(skill.version)},
                                "instructions": SKILL_INSTRUCTIONS,
                                "source_url": {repr(skill.source_url)},
                            }},
                            correlation_id=correlation_id,
                        )

                    if tool_name == "skill:{skill.name}":
                        return await self._execute_skill(parameters, correlation_id)

                    return ToolExecutionResult(
                        tool_name=tool_name,
                        status=ToolExecutionStatus.NOT_FOUND,
                        success=False,
                        error=f"Unknown tool: {{tool_name}}",
                        correlation_id=correlation_id,
                    )

                async def _execute_skill(
                    self, parameters: Dict[str, Any], correlation_id: str
                ) -> ToolExecutionResult:
                    """Execute the skill with given parameters.

                    The skill instructions are returned along with any supporting
                    file contents so the LLM can follow the skill\'s directives.
                    """
                    user_input = parameters.get("input", "")
                    extra_args = parameters.get("args", {{}})

                    # Gather supporting files (recursively)
                    supporting_contents: Dict[str, str] = {{}}
                    if _SUPPORTING_DIR.exists():
                        for f in _SUPPORTING_DIR.rglob("*"):
                            if f.is_file():
                                try:
                                    # Use relative path from supporting dir as key
                                    rel_path = f.relative_to(_SUPPORTING_DIR)
                                    supporting_contents[str(rel_path)] = f.read_text(encoding="utf-8")
                                except (UnicodeDecodeError, OSError):
                                    pass

                    return ToolExecutionResult(
                        tool_name="skill:{skill.name}",
                        status=ToolExecutionStatus.COMPLETED,
                        success=True,
                        data={{
                            "instructions": SKILL_INSTRUCTIONS,
                            "user_input": user_input,
                            "extra_args": extra_args,
                            "supporting_files": supporting_contents,
                        }},
                        correlation_id=correlation_id,
                    )

                async def list_tools(self) -> List[str]:
                    return list(self.TOOL_DEFINITIONS.keys())

                async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
                    info = self.TOOL_DEFINITIONS.get(tool_name)
                    return info.parameters if info else None

                async def get_available_tools(self) -> List[str]:
                    return list(self.TOOL_DEFINITIONS.keys())

                async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
                    return self.TOOL_DEFINITIONS.get(tool_name)

                async def get_all_tool_info(self) -> List[ToolInfo]:
                    return list(self.TOOL_DEFINITIONS.values())

                async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
                    return tool_name in self.TOOL_DEFINITIONS
        '''
        )
        (adapter_dir / "services.py").write_text(content, encoding="utf-8")

    def _build_tags(self, skill: ParsedSkill) -> List[str]:
        """Build tags list for the imported skill tool.

        Maps OpenClaw fields to CIRIS tags:
        - Always includes: imported, openclaw, {skill.name}
        - user_invocable=False -> adds 'internal' tag (hidden from UI tool list)
        - command_dispatch='tool' -> adds 'direct_dispatch' tag
        """
        tags = ["imported", "openclaw", skill.name]
        if not skill.user_invocable:
            tags.append("internal")
        if skill.command_dispatch == "tool":
            tags.append("direct_dispatch")
        return tags

    def _write_original_skill(self, adapter_dir: Path, skill: ParsedSkill) -> None:
        """Write the original SKILL.md for reference."""
        # Reconstruct from parsed data
        import yaml as _yaml

        frontmatter = dict(skill.raw_frontmatter) if skill.raw_frontmatter else {"name": skill.name}
        fm_str = _yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        content = f"---\n{fm_str}---\n\n{skill.instructions}\n"
        (adapter_dir / "SKILL.md").write_text(content, encoding="utf-8")

    def _write_supporting_files(self, adapter_dir: Path, skill: ParsedSkill) -> None:
        """Write supporting files to the supporting/ subdirectory."""
        if not skill.supporting_files:
            return

        supporting_dir = adapter_dir / "supporting"
        supporting_dir.mkdir(exist_ok=True)

        for rel_path, content in skill.supporting_files.items():
            # Preserve directory structure within supporting/
            target = supporting_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
