"""Tests for skill-to-adapter converter."""

import json
import tempfile
from pathlib import Path

import pytest

from ciris_engine.logic.services.skill_import.converter import SkillToAdapterConverter, _sanitize_module_name
from ciris_engine.logic.services.skill_import.parser import (
    OpenClawSkillParser,
    ParsedSkill,
    SkillInstallSpec,
    SkillMetadata,
    SkillRequirements,
)


# ============================================================================
# Fixtures
# ============================================================================

FULL_SKILL_MD = """\
---
name: todoist-cli
description: Manage Todoist tasks from the command line
version: 1.2.0
metadata:
  openclaw:
    requires:
      env:
        - TODOIST_API_KEY
      bins:
        - curl
    primaryEnv: TODOIST_API_KEY
    emoji: "✅"
    homepage: https://example.com/todoist
    os:
      - linux
      - darwin
    install:
      - kind: brew
        formula: curl
        bins:
          - curl
---

# Todoist CLI

You are a task management assistant.

## Steps
1. Auth with TODOIST_API_KEY
2. List tasks
"""


@pytest.fixture
def parser():
    return OpenClawSkillParser()


@pytest.fixture
def full_skill(parser: OpenClawSkillParser) -> ParsedSkill:
    return parser.parse_skill_md(FULL_SKILL_MD, source_url="https://clawhub.com/todoist-cli")


# ============================================================================
# Tests: Module Name Sanitization
# ============================================================================


class TestSanitizeModuleName:
    def test_basic_hyphenated(self):
        assert _sanitize_module_name("my-cool-skill") == "imported_my_cool_skill"

    def test_already_underscored(self):
        assert _sanitize_module_name("my_tool") == "imported_my_tool"

    def test_special_characters(self):
        assert _sanitize_module_name("my@tool!v2") == "imported_my_tool_v2"

    def test_uppercase(self):
        assert _sanitize_module_name("MyTool") == "imported_mytool"


# ============================================================================
# Tests: Converter
# ============================================================================


class TestSkillToAdapterConverter:
    def test_creates_adapter_directory(self, full_skill: ParsedSkill):
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            adapter_path = converter.convert(full_skill)

            assert adapter_path.exists()
            assert adapter_path.name == "imported_todoist_cli"
            assert (adapter_path / "__init__.py").exists()
            assert (adapter_path / "adapter.py").exists()
            assert (adapter_path / "services.py").exists()
            assert (adapter_path / "manifest.json").exists()
            assert (adapter_path / "SKILL.md").exists()

    def test_manifest_content(self, full_skill: ParsedSkill):
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            adapter_path = converter.convert(full_skill)

            manifest = json.loads((adapter_path / "manifest.json").read_text())

            # Module info
            assert manifest["module"]["name"] == "imported_todoist_cli"
            assert manifest["module"]["version"] == "1.2.0"
            assert manifest["module"]["description"] == "Manage Todoist tasks from the command line"
            assert manifest["module"]["auto_load"] is True

            # Services
            assert len(manifest["services"]) == 1
            assert manifest["services"][0]["type"] == "TOOL"
            assert manifest["services"][0]["class"] == "imported_todoist_cli.services.ImportedSkillToolService"

            # Capabilities
            assert "tool:skill:todoist-cli" in manifest["capabilities"]

            # Metadata
            assert manifest["metadata"]["imported_from"] == "openclaw"
            assert manifest["metadata"]["original_skill_name"] == "todoist-cli"
            assert manifest["metadata"]["source_url"] == "https://clawhub.com/todoist-cli"

            # Configuration from env vars
            assert "todoist_api_key" in manifest["configuration"]
            assert manifest["configuration"]["todoist_api_key"]["env"] == "TODOIST_API_KEY"

    def test_adapter_py_content(self, full_skill: ParsedSkill):
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            adapter_path = converter.convert(full_skill)

            content = (adapter_path / "adapter.py").read_text()

            # Must have the Adapter export
            assert "Adapter = ImportedSkillAdapter" in content
            # Must reference the tool service
            assert "ImportedSkillToolService" in content
            # Must implement lifecycle methods
            assert "async def start(self)" in content
            assert "async def stop(self)" in content
            assert "async def run_lifecycle(self" in content
            assert "def get_services_to_register(self)" in content

    def test_services_py_content(self, full_skill: ParsedSkill):
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            adapter_path = converter.convert(full_skill)

            content = (adapter_path / "services.py").read_text()

            # Tool definitions
            assert 'skill:todoist-cli' in content
            assert 'skill:todoist-cli:info' in content

            # Instructions preserved
            assert "You are a task management assistant" in content
            assert "Auth with TODOIST_API_KEY" in content

            # Requirements mapped
            assert "BinaryRequirement" in content
            assert "EnvVarRequirement" in content
            assert "TODOIST_API_KEY" in content

            # Protocol methods
            assert "async def execute_tool" in content
            assert "async def get_all_tool_info" in content
            assert "async def get_available_tools" in content

    def test_skill_md_preserved(self, full_skill: ParsedSkill):
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            adapter_path = converter.convert(full_skill)

            content = (adapter_path / "SKILL.md").read_text()
            assert "todoist-cli" in content
            assert "task management assistant" in content

    def test_supporting_files_written(self):
        skill = ParsedSkill(
            name="test-skill",
            description="Test",
            instructions="Do the thing",
            supporting_files={
                "references/docs.md": "# Docs\nContent here",
                "scripts/run.sh": "#!/bin/bash\necho hi",
            },
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            adapter_path = converter.convert(skill)

            supporting_dir = adapter_path / "supporting"
            assert supporting_dir.exists()
            assert (supporting_dir / "docs.md").read_text() == "# Docs\nContent here"
            assert (supporting_dir / "run.sh").read_text() == "#!/bin/bash\necho hi"

    def test_idempotent_overwrite(self, full_skill: ParsedSkill):
        """Converting the same skill twice should overwrite cleanly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            path1 = converter.convert(full_skill)
            path2 = converter.convert(full_skill)
            assert path1 == path2
            assert (path2 / "manifest.json").exists()


# ============================================================================
# Tests: Field Consumption Verification
# ============================================================================


class TestFieldConsumption:
    """Verify every OpenClaw skill field is consumed in the adapter output."""

    def test_name_consumed(self, full_skill: ParsedSkill):
        """name -> manifest module.name, tool names, adapter references."""
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            path = converter.convert(full_skill)
            manifest = json.loads((path / "manifest.json").read_text())
            assert "todoist" in manifest["module"]["name"]
            assert "todoist-cli" in manifest["metadata"]["original_skill_name"]

    def test_description_consumed(self, full_skill: ParsedSkill):
        """description -> manifest description, tool description."""
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            path = converter.convert(full_skill)
            services = (path / "services.py").read_text()
            assert "Manage Todoist tasks" in services

    def test_version_consumed(self, full_skill: ParsedSkill):
        """version -> manifest version, tool version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            path = converter.convert(full_skill)
            manifest = json.loads((path / "manifest.json").read_text())
            assert manifest["module"]["version"] == "1.2.0"
            services = (path / "services.py").read_text()
            assert "1.2.0" in services

    def test_env_requirements_consumed(self, full_skill: ParsedSkill):
        """requires.env -> manifest configuration, tool requirements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            path = converter.convert(full_skill)
            manifest = json.loads((path / "manifest.json").read_text())
            assert "todoist_api_key" in manifest["configuration"]
            services = (path / "services.py").read_text()
            assert "TODOIST_API_KEY" in services

    def test_bins_requirements_consumed(self, full_skill: ParsedSkill):
        """requires.bins -> tool requirements BinaryRequirement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            path = converter.convert(full_skill)
            services = (path / "services.py").read_text()
            assert "'curl'" in services
            assert "BinaryRequirement" in services

    def test_instructions_consumed(self, full_skill: ParsedSkill):
        """instructions -> SKILL_INSTRUCTIONS constant, tool documentation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            path = converter.convert(full_skill)
            services = (path / "services.py").read_text()
            assert "SKILL_INSTRUCTIONS" in services
            assert "task management assistant" in services
            assert "ToolDocumentation" in services

    def test_homepage_consumed(self, full_skill: ParsedSkill):
        """metadata.homepage -> tool documentation homepage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            path = converter.convert(full_skill)
            services = (path / "services.py").read_text()
            assert "https://example.com/todoist" in services

    def test_source_url_consumed(self, full_skill: ParsedSkill):
        """source_url -> manifest metadata, info tool output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            path = converter.convert(full_skill)
            manifest = json.loads((path / "manifest.json").read_text())
            assert manifest["metadata"]["source_url"] == "https://clawhub.com/todoist-cli"
            services = (path / "services.py").read_text()
            assert "clawhub.com/todoist-cli" in services

    def test_supporting_files_consumed(self):
        """supporting_files -> supporting/ directory, runtime access."""
        skill = ParsedSkill(
            name="with-files",
            description="Has files",
            instructions="Use the docs",
            supporting_files={"docs.md": "# Docs"},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            converter = SkillToAdapterConverter(output_dir=Path(tmpdir))
            path = converter.convert(skill)
            assert (path / "supporting" / "docs.md").exists()
            # Services reference the supporting dir
            services = (path / "services.py").read_text()
            assert "_SUPPORTING_DIR" in services
