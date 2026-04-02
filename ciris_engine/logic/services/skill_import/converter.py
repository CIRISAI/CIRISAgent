"""Skill-to-adapter converter.

Transforms a parsed OpenClaw skill into a CIRIS adapter directory
that can be loaded by the AdapterDiscoveryService.

Generated adapters are placed in ~/.ciris/adapters/ (user-installed path)
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
_USER_ADAPTERS_DIR = Path.home() / ".ciris" / "adapters"


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
    """Convert OpenClaw install specs to CIRIS InstallStep dicts."""
    steps = []
    for i, spec in enumerate(specs):
        step: Dict[str, Any] = {
            "id": f"install_{i}",
            "kind": _map_install_kind(spec.kind),
            "label": f"Install via {spec.kind}",
            "provides_binaries": spec.bins,
        }
        if spec.formula:
            step["formula"] = spec.formula
        if spec.package:
            step["package"] = spec.package
        steps.append(step)
    return steps


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
        self._write_services(adapter_dir, module_name, skill)
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

        manifest = {
            "module": {
                "name": module_name,
                "version": skill.version,
                "description": skill.description or f"Imported OpenClaw skill: {skill.name}",
                "author": "OpenClaw Import",
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
            },
        }

        # Remove None values
        manifest = {k: v for k, v in manifest.items() if v is not None}

        (adapter_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    def _write_init(self, adapter_dir: Path, module_name: str) -> None:
        """Generate __init__.py."""
        content = f'"""Imported OpenClaw skill adapter: {module_name}."""\n'
        (adapter_dir / "__init__.py").write_text(content, encoding="utf-8")

    def _write_adapter(self, adapter_dir: Path, module_name: str, skill: ParsedSkill) -> None:
        """Generate adapter.py implementing BaseAdapterProtocol."""
        content = textwrap.dedent(f'''\
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
                    logger.info("Imported skill adapter '{skill.name}' started")

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
        ''')
        (adapter_dir / "adapter.py").write_text(content, encoding="utf-8")

    def _write_services(self, adapter_dir: Path, module_name: str, skill: ParsedSkill) -> None:
        """Generate services.py with a ToolService that exposes the skill."""
        # Build requirements block
        requirements_code = "None"
        if skill.metadata and skill.metadata.requires:
            req = skill.metadata.requires
            bin_list = repr(req.bins) if req.bins else "[]"
            env_list = repr(req.env) if req.env else "[]"
            requirements_code = textwrap.dedent(f"""\
                ToolRequirements(
                        binaries=[BinaryRequirement(name=b) for b in {bin_list}],
                        env_vars=[EnvVarRequirement(name=e) for e in {env_list}],
                    )""")

        # Build install steps
        install_steps_code = "[]"
        if skill.metadata and skill.metadata.install:
            steps = _build_install_steps(skill.metadata.install)
            install_steps_code = repr(steps)

        # Escape the instructions for embedding as a Python string
        escaped_instructions = skill.instructions.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')

        # Build platform list
        platforms = skill.metadata.os if skill.metadata and skill.metadata.os else []

        content = textwrap.dedent(f'''\
            """Tool service for imported OpenClaw skill: {skill.name}."""

            import logging
            import os
            import subprocess
            from pathlib import Path
            from typing import Any, Dict, List, Optional
            from uuid import uuid4

            from ciris_engine.schemas.adapters.tools import (
                BinaryRequirement,
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
                        requirements={requirements_code},
                        tags=["imported", "openclaw", {repr(skill.name)}],
                        version={repr(skill.version)},
                        documentation=ToolDocumentation(
                            quick_start=f"Imported OpenClaw skill: {skill.name}",
                            detailed_instructions=SKILL_INSTRUCTIONS,
                            homepage={repr(skill.metadata.homepage if skill.metadata else None)},
                        ),
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
                        context_enrichment=True,
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

                    # Gather supporting files
                    supporting_contents: Dict[str, str] = {{}}
                    if _SUPPORTING_DIR.exists():
                        for f in _SUPPORTING_DIR.iterdir():
                            if f.is_file():
                                try:
                                    supporting_contents[f.name] = f.read_text(encoding="utf-8")
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
        ''')
        (adapter_dir / "services.py").write_text(content, encoding="utf-8")

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
            target = supporting_dir / Path(rel_path).name  # Flatten to single directory
            target.write_text(content, encoding="utf-8")
