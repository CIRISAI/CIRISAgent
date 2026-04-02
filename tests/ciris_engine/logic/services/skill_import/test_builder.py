"""Tests for the skill builder (HyperCard-style card system)."""

import json
import tempfile
from pathlib import Path

import pytest

from ciris_engine.logic.services.skill_import.builder import (
    BehaviorCard,
    IdentityCard,
    InstructCard,
    RequiresCard,
    SkillBuilder,
    SkillDraft,
    ToolCard,
    ToolParameter,
    ToolsCard,
    get_all_card_schemas,
    get_card_schema,
)


OPENCLAW_SKILL = """\
---
name: todoist-cli
description: Manage Todoist tasks
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
    always: true
    install:
      - kind: brew
        formula: curl
        bins:
          - curl
---

You are a task management assistant.
Use the TODOIST_API_KEY to authenticate.
"""


@pytest.fixture
def builder():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield SkillBuilder(drafts_dir=Path(tmpdir))


# ============================================================================
# Schema Introspection
# ============================================================================


class TestCardSchemas:
    def test_get_all_card_schemas(self):
        result = get_all_card_schemas()
        assert "cards" in result
        assert "draft_schema" in result
        assert len(result["cards"]) == 6

    def test_card_has_metadata_and_schema(self):
        result = get_all_card_schemas()
        for card in result["cards"]:
            assert "id" in card
            assert "title" in card
            assert "emoji" in card
            assert "schema" in card
            assert "properties" in card["schema"]

    def test_identity_schema_has_fields(self):
        schema = get_card_schema("identity")
        props = schema["properties"]
        assert "name" in props
        assert "description" in props
        assert "version" in props
        assert "emoji" in props

    def test_behavior_schema_has_safety_fields(self):
        schema = get_card_schema("behavior")
        props = schema["properties"]
        assert "requires_approval" in props
        assert "min_confidence" in props
        assert "always_active" in props

    def test_unknown_card_raises(self):
        with pytest.raises(ValueError, match="Unknown card"):
            get_card_schema("nonexistent")

    def test_schemas_are_valid_json_schema(self):
        """Every card schema should be a valid JSON Schema object."""
        for card_id in ["identity", "tools", "requires", "instruct", "behavior", "install"]:
            schema = get_card_schema(card_id)
            assert schema["type"] == "object"
            assert "properties" in schema


# ============================================================================
# Draft CRUD
# ============================================================================


class TestDraftLifecycle:
    def test_create_blank_draft(self, builder: SkillBuilder):
        draft = builder.create_draft()
        assert draft.draft_id
        assert draft.identity.name == ""
        assert draft.tools.tools == []

    def test_save_and_load_draft(self, builder: SkillBuilder):
        draft = builder.create_draft()
        draft.identity.name = "test-skill"
        draft.identity.description = "A test skill"
        builder.save_draft(draft)

        loaded = builder.load_draft(draft.draft_id)
        assert loaded is not None
        assert loaded.identity.name == "test-skill"
        assert loaded.draft_id == draft.draft_id

    def test_list_drafts(self, builder: SkillBuilder):
        d1 = builder.create_draft()
        d1.identity.name = "skill-a"
        builder.save_draft(d1)

        d2 = builder.create_draft()
        d2.identity.name = "skill-b"
        builder.save_draft(d2)

        drafts = builder.list_drafts()
        assert len(drafts) == 2
        names = {d.identity.name for d in drafts}
        assert names == {"skill-a", "skill-b"}

    def test_delete_draft(self, builder: SkillBuilder):
        draft = builder.create_draft()
        builder.save_draft(draft)
        assert builder.delete_draft(draft.draft_id)
        assert builder.load_draft(draft.draft_id) is None

    def test_load_nonexistent_returns_none(self, builder: SkillBuilder):
        assert builder.load_draft("nonexistent") is None


# ============================================================================
# OpenClaw Import -> Draft
# ============================================================================


class TestOpenClawImport:
    def test_import_creates_draft(self, builder: SkillBuilder):
        draft = builder.create_from_openclaw(OPENCLAW_SKILL)

        assert draft.identity.name == "todoist-cli"
        assert draft.identity.description == "Manage Todoist tasks"
        assert draft.identity.version == "1.2.0"
        assert draft.identity.emoji == "✅"

    def test_import_maps_requirements(self, builder: SkillBuilder):
        draft = builder.create_from_openclaw(OPENCLAW_SKILL)

        assert "TODOIST_API_KEY" in draft.requires.env_vars
        assert "curl" in draft.requires.binaries

    def test_import_maps_instructions(self, builder: SkillBuilder):
        draft = builder.create_from_openclaw(OPENCLAW_SKILL)

        assert "task management assistant" in draft.instruct.instructions
        assert "TODOIST_API_KEY" in draft.instruct.instructions

    def test_import_maps_behavior(self, builder: SkillBuilder):
        draft = builder.create_from_openclaw(OPENCLAW_SKILL)

        assert draft.behavior.requires_approval is True  # Default for imports
        assert draft.behavior.always_active is True  # From always: true

    def test_import_creates_tool_card(self, builder: SkillBuilder):
        draft = builder.create_from_openclaw(OPENCLAW_SKILL)

        assert len(draft.tools.tools) == 1
        tool = draft.tools.tools[0]
        assert tool.name == "todoist-cli"
        assert len(tool.parameters) == 2  # input + args

    def test_import_preserves_provenance(self, builder: SkillBuilder):
        draft = builder.create_from_openclaw(OPENCLAW_SKILL, source_url="https://clawhub.com/todoist")

        assert draft.imported_from == "openclaw"
        assert draft.source_url == "https://clawhub.com/todoist"

    def test_import_maps_install_steps(self, builder: SkillBuilder):
        draft = builder.create_from_openclaw(OPENCLAW_SKILL)

        assert len(draft.install.steps) == 1
        assert draft.install.steps[0].kind == "brew"


# ============================================================================
# Validation
# ============================================================================


class TestValidation:
    def test_blank_draft_has_errors(self, builder: SkillBuilder):
        draft = builder.create_draft()
        errors = builder.validate_draft(draft)
        assert len(errors) > 0
        assert any("name" in e.lower() for e in errors)

    def test_valid_draft_passes(self, builder: SkillBuilder):
        draft = builder.create_draft()
        draft.identity.name = "my-skill"
        draft.identity.description = "Does things"
        draft.tools.tools = [
            ToolCard(name="my-tool", description="Does a thing")
        ]
        errors = builder.validate_draft(draft)
        assert errors == []

    def test_invalid_name_rejected(self, builder: SkillBuilder):
        draft = builder.create_draft()
        draft.identity.name = "Invalid Name!"
        draft.identity.description = "Test"
        draft.tools.tools = [ToolCard(name="tool", description="test")]
        errors = builder.validate_draft(draft)
        assert any("lowercase" in e.lower() for e in errors)

    def test_validate_card_data(self, builder: SkillBuilder):
        # Valid identity card
        errors = builder.validate_card("identity", {
            "name": "test", "description": "test", "version": "1.0.0"
        })
        assert errors == []

    def test_validate_card_rejects_bad_data(self, builder: SkillBuilder):
        # Extra fields not allowed
        errors = builder.validate_card("identity", {
            "name": "test", "unknown_field": True
        })
        assert len(errors) > 0


# ============================================================================
# Build Adapter
# ============================================================================


class TestBuildAdapter:
    def test_build_creates_adapter(self, builder: SkillBuilder):
        draft = builder.create_draft()
        draft.identity.name = "my-skill"
        draft.identity.description = "A test skill"
        draft.tools.tools = [
            ToolCard(
                name="greet",
                description="Say hello",
                parameters=[
                    ToolParameter(name="name", type="string", description="Who to greet", required=True),
                ],
            )
        ]
        draft.instruct.instructions = "Greet the user by name."
        draft.behavior.requires_approval = False
        draft.behavior.min_confidence = 0.5

        adapter_path = builder.build_adapter(draft)
        assert adapter_path.exists()
        assert (adapter_path / "manifest.json").exists()
        assert (adapter_path / "adapter.py").exists()
        assert (adapter_path / "services.py").exists()

    def test_build_includes_dma_guidance(self, builder: SkillBuilder):
        draft = builder.create_draft()
        draft.identity.name = "safe-skill"
        draft.identity.description = "Requires approval"
        draft.tools.tools = [ToolCard(name="do-thing", description="Does a thing")]
        draft.instruct.instructions = "Do the thing carefully."
        draft.behavior.requires_approval = True
        draft.behavior.min_confidence = 0.95
        draft.behavior.ethical_considerations = "Consider user privacy"

        adapter_path = builder.build_adapter(draft)
        services = (adapter_path / "services.py").read_text()

        assert "ToolDMAGuidance" in services
        assert "requires_approval=True" in services
        assert "min_confidence=0.95" in services
        assert "Consider user privacy" in services

    def test_build_rejects_invalid_draft(self, builder: SkillBuilder):
        draft = builder.create_draft()  # blank = invalid
        with pytest.raises(ValueError, match="validation errors"):
            builder.build_adapter(draft)


# ============================================================================
# ToolCard -> ToolParameterSchema
# ============================================================================


class TestToolCardConversion:
    def test_to_tool_parameter_schema(self):
        card = ToolCard(
            name="search",
            description="Search for items",
            parameters=[
                ToolParameter(name="query", type="string", description="Search query", required=True),
                ToolParameter(name="limit", type="integer", description="Max results", required=False),
            ],
        )
        schema = card.to_tool_parameter_schema()
        assert schema.type == "object"
        assert "query" in schema.properties
        assert "limit" in schema.properties
        assert schema.required == ["query"]
        assert schema.properties["query"]["type"] == "string"
        assert schema.properties["limit"]["type"] == "integer"

    def test_empty_parameters(self):
        card = ToolCard(name="status", description="Get status")
        schema = card.to_tool_parameter_schema()
        assert schema.type == "object"
        assert schema.properties == {}
        assert schema.required == []
