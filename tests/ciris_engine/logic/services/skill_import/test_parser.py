"""Tests for OpenClaw SKILL.md parser."""

import pytest
from pathlib import Path
import tempfile

from ciris_engine.logic.services.skill_import.parser import OpenClawSkillParser, ParsedSkill


# ============================================================================
# Fixtures
# ============================================================================

MINIMAL_SKILL = """\
---
name: my-tool
description: A simple test tool
---

Use this tool to do things.
"""

FULL_SKILL = """\
---
name: todoist-cli
description: Manage Todoist tasks from the command line
version: 1.2.0
user-invocable: true
command-dispatch: tool
command-tool: todoist
metadata:
  openclaw:
    requires:
      env:
        - TODOIST_API_KEY
      bins:
        - curl
        - jq
      anyBins:
        - bat
        - cat
      config:
        - todoist.yaml
    primaryEnv: TODOIST_API_KEY
    emoji: "✅"
    homepage: https://github.com/example/todoist-cli
    os:
      - linux
      - darwin
    install:
      - kind: brew
        formula: jq
        bins:
          - jq
      - kind: node
        package: todoist-cli
        bins:
          - todoist
    always: false
    skillKey: todoist
---

# Todoist CLI Skill

You are a Todoist task management assistant.

## Instructions

1. Use the TODOIST_API_KEY to authenticate
2. Support CRUD operations on tasks
3. Format output as markdown tables
"""

CLAWDBOT_NAMESPACE = """\
---
name: legacy-skill
description: Uses clawdbot namespace
metadata:
  clawdbot:
    requires:
      env:
        - API_KEY
    primaryEnv: API_KEY
---

Legacy instructions here.
"""

FULL_FRONTMATTER_SKILL = """\
---
name: full-fields
description: Tests all frontmatter fields
version: 2.0.0
homepage: https://example.com/full
user-invocable: false
disable-model-invocation: true
command-dispatch: tool
command-tool: mytool
command-arg-mode: raw
metadata:
  openclaw:
    requires:
      env:
        - API_KEY
      bins:
        - curl
      anyBins:
        - bat
        - cat
      config:
        - myconfig.yaml
    primaryEnv: API_KEY
    homepage: https://metadata-homepage.com
    emoji: "🔧"
    os:
      - linux
    always: true
    skillKey: custom-key
    install:
      - kind: brew
        formula: curl
        bins:
          - curl
---

Full frontmatter instructions.
"""

NO_FRONTMATTER = """\
This is just plain markdown with no frontmatter.
It should fail because no name is provided.
"""


@pytest.fixture
def parser():
    return OpenClawSkillParser()


# ============================================================================
# Tests: parse_skill_md
# ============================================================================


class TestParseSkillMd:
    """Tests for parsing SKILL.md content strings."""

    def test_minimal_skill(self, parser: OpenClawSkillParser):
        skill = parser.parse_skill_md(MINIMAL_SKILL)
        assert skill.name == "my-tool"
        assert skill.description == "A simple test tool"
        assert skill.version == "1.0.0"
        assert skill.instructions == "Use this tool to do things."
        assert skill.metadata is None

    def test_full_skill_basic_fields(self, parser: OpenClawSkillParser):
        skill = parser.parse_skill_md(FULL_SKILL)
        assert skill.name == "todoist-cli"
        assert skill.description == "Manage Todoist tasks from the command line"
        assert skill.version == "1.2.0"
        assert skill.user_invocable is True
        assert skill.command_dispatch == "tool"
        assert skill.command_tool == "todoist"

    def test_full_skill_metadata(self, parser: OpenClawSkillParser):
        skill = parser.parse_skill_md(FULL_SKILL)
        assert skill.metadata is not None
        assert skill.metadata.primary_env == "TODOIST_API_KEY"
        assert skill.metadata.emoji == "✅"
        assert skill.metadata.homepage == "https://github.com/example/todoist-cli"
        assert skill.metadata.os == ["linux", "darwin"]
        assert skill.metadata.always is False
        assert skill.metadata.skill_key == "todoist"

    def test_full_skill_requirements(self, parser: OpenClawSkillParser):
        skill = parser.parse_skill_md(FULL_SKILL)
        assert skill.metadata is not None
        req = skill.metadata.requires
        assert req is not None
        assert req.env == ["TODOIST_API_KEY"]
        assert req.bins == ["curl", "jq"]
        assert req.any_bins == ["bat", "cat"]
        assert req.config == ["todoist.yaml"]

    def test_full_skill_install_specs(self, parser: OpenClawSkillParser):
        skill = parser.parse_skill_md(FULL_SKILL)
        assert skill.metadata is not None
        assert len(skill.metadata.install) == 2
        assert skill.metadata.install[0].kind == "brew"
        assert skill.metadata.install[0].formula == "jq"
        assert skill.metadata.install[0].bins == ["jq"]
        assert skill.metadata.install[1].kind == "node"
        assert skill.metadata.install[1].package == "todoist-cli"

    def test_full_skill_instructions(self, parser: OpenClawSkillParser):
        skill = parser.parse_skill_md(FULL_SKILL)
        assert "# Todoist CLI Skill" in skill.instructions
        assert "TODOIST_API_KEY to authenticate" in skill.instructions
        assert "markdown tables" in skill.instructions

    def test_clawdbot_namespace(self, parser: OpenClawSkillParser):
        """Test that clawdbot namespace is accepted as an alias."""
        skill = parser.parse_skill_md(CLAWDBOT_NAMESPACE)
        assert skill.name == "legacy-skill"
        assert skill.metadata is not None
        assert skill.metadata.primary_env == "API_KEY"
        assert skill.metadata.requires is not None
        assert skill.metadata.requires.env == ["API_KEY"]

    def test_no_frontmatter_raises(self, parser: OpenClawSkillParser):
        with pytest.raises(ValueError, match="must have a 'name' field"):
            parser.parse_skill_md(NO_FRONTMATTER)

    def test_source_url_preserved(self, parser: OpenClawSkillParser):
        skill = parser.parse_skill_md(
            MINIMAL_SKILL,
            source_url="https://clawhub.com/skills/my-tool"
        )
        assert skill.source_url == "https://clawhub.com/skills/my-tool"

    def test_raw_frontmatter_preserved(self, parser: OpenClawSkillParser):
        skill = parser.parse_skill_md(FULL_SKILL)
        assert skill.raw_frontmatter["name"] == "todoist-cli"
        assert "metadata" in skill.raw_frontmatter

    def test_all_frontmatter_fields(self, parser: OpenClawSkillParser):
        """Verify every OpenClaw frontmatter field is parsed."""
        skill = parser.parse_skill_md(FULL_FRONTMATTER_SKILL)
        # Top-level frontmatter
        assert skill.name == "full-fields"
        assert skill.description == "Tests all frontmatter fields"
        assert skill.version == "2.0.0"
        assert skill.homepage == "https://example.com/full"  # top-level wins
        assert skill.user_invocable is False
        assert skill.disable_model_invocation is True
        assert skill.command_dispatch == "tool"
        assert skill.command_tool == "mytool"
        assert skill.command_arg_mode == "raw"

    def test_homepage_fallback_to_metadata(self, parser: OpenClawSkillParser):
        """When top-level homepage is absent, fall back to metadata.homepage."""
        skill = parser.parse_skill_md(FULL_SKILL)
        # FULL_SKILL has no top-level homepage but has metadata.openclaw.homepage
        assert skill.homepage == "https://github.com/example/todoist-cli"

    def test_all_metadata_fields(self, parser: OpenClawSkillParser):
        """Verify every metadata.openclaw field is parsed."""
        skill = parser.parse_skill_md(FULL_FRONTMATTER_SKILL)
        assert skill.metadata is not None
        assert skill.metadata.primary_env == "API_KEY"
        assert skill.metadata.emoji == "🔧"
        assert skill.metadata.os == ["linux"]
        assert skill.metadata.always is True
        assert skill.metadata.skill_key == "custom-key"
        assert skill.metadata.requires is not None
        assert skill.metadata.requires.any_bins == ["bat", "cat"]
        assert skill.metadata.requires.config == ["myconfig.yaml"]


# ============================================================================
# Tests: parse_directory
# ============================================================================


class TestParseDirectory:
    """Tests for parsing skill directories."""

    def test_parse_directory_with_supporting_files(self, parser: OpenClawSkillParser):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)

            # Write SKILL.md
            (skill_dir / "SKILL.md").write_text(MINIMAL_SKILL)

            # Write supporting files
            refs_dir = skill_dir / "references"
            refs_dir.mkdir()
            (refs_dir / "api-docs.md").write_text("# API Documentation\n\nSome docs.")
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "setup.sh").write_text("#!/bin/bash\necho setup")

            skill = parser.parse_directory(skill_dir)

            assert skill.name == "my-tool"
            assert len(skill.supporting_files) == 2
            assert "references/api-docs.md" in skill.supporting_files
            assert "scripts/setup.sh" in skill.supporting_files

    def test_parse_directory_case_insensitive(self, parser: OpenClawSkillParser):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            (skill_dir / "skill.md").write_text(MINIMAL_SKILL)
            skill = parser.parse_directory(skill_dir)
            assert skill.name == "my-tool"

    def test_parse_directory_no_skill_md(self, parser: OpenClawSkillParser):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError, match="No SKILL.md"):
                parser.parse_directory(Path(tmpdir))

    def test_parse_directory_skips_hidden(self, parser: OpenClawSkillParser):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            (skill_dir / "SKILL.md").write_text(MINIMAL_SKILL)

            # Hidden dirs should be skipped
            clawhub_dir = skill_dir / ".clawhub"
            clawhub_dir.mkdir()
            (clawhub_dir / "origin.json").write_text("{}")

            git_dir = skill_dir / ".git"
            git_dir.mkdir()
            (git_dir / "config").write_text("")

            skill = parser.parse_directory(skill_dir)
            assert len(skill.supporting_files) == 0
