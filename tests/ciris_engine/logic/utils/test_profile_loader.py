from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ciris_engine.logic.utils.profile_loader import DEFAULT_TEMPLATE_PATH, load_template
from ciris_engine.schemas.config.agent import AgentTemplate
from ciris_engine.schemas.runtime.enums import HandlerActionType


@pytest.fixture
def valid_template_dict():
    """Provides a valid dictionary for creating an AgentTemplate."""
    return {
        "name": "test_agent",
        "description": "A test agent.",
        "role_description": "An agent that is used for testing purposes.",
        "personality": "helpful",
        "permitted_actions": ["speak", "defer"],
    }


@pytest.fixture
def create_yaml_file(tmp_path):
    def _create_yaml(filename, data):
        file_path = tmp_path / filename
        with open(file_path, "w") as f:
            yaml.dump(data, f)
        return file_path

    return _create_yaml


@pytest.mark.asyncio
class TestLoadTemplate:
    async def test_load_from_explicit_path(self, create_yaml_file, valid_template_dict):
        template_path = create_yaml_file("test.yaml", valid_template_dict)
        template = await load_template(template_path)

        assert isinstance(template, AgentTemplate)
        assert template.name == "test_agent"
        assert HandlerActionType.SPEAK in template.permitted_actions
        assert HandlerActionType.DEFER in template.permitted_actions

    async def test_load_from_default_path(self, monkeypatch, create_yaml_file, valid_template_dict):
        default_path = create_yaml_file("default.yaml", valid_template_dict)
        monkeypatch.setattr("ciris_engine.logic.utils.profile_loader.DEFAULT_TEMPLATE_PATH", default_path)
        template = await load_template(None)
        assert template is not None
        assert template.name == "test_agent"

    async def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            await load_template(Path("non_existent_file.yaml"))

    async def test_empty_yaml_file(self, create_yaml_file):
        template_path = create_yaml_file("empty.yaml", None)
        template = await load_template(template_path)
        assert template is None

    async def test_invalid_yaml_file(self, create_yaml_file):
        template_path = create_yaml_file("invalid.yaml", None)
        with open(template_path, "w") as f:
            f.write("key: value: another_value")  # Invalid YAML

        with pytest.raises(ValueError, match="Error parsing YAML"):
            await load_template(template_path)

    async def test_pydantic_validation_error(self, create_yaml_file, valid_template_dict):
        # A more reliable way to cause a validation error is to set a required field to None
        valid_template_dict["name"] = None
        template_path = create_yaml_file("invalid_schema.yaml", valid_template_dict)

        with pytest.raises(ValueError, match="Template validation failed"):
            await load_template(template_path)

    async def test_infer_name_from_filename(self, create_yaml_file, valid_template_dict, caplog):
        del valid_template_dict["name"]
        template_path = create_yaml_file("my_agent.yaml", valid_template_dict)

        template = await load_template(template_path)
        assert template.name == "my_agent"
        assert "Template 'name' not found in YAML" in caplog.text

    async def test_permitted_actions_conversion(self, create_yaml_file, valid_template_dict, caplog):
        # Test various formats and an unknown action
        valid_template_dict["permitted_actions"] = ["speak", "DEFER", "observe", "unknown_action"]
        template_path = create_yaml_file("actions.yaml", valid_template_dict)

        template = await load_template(template_path)

        assert HandlerActionType.SPEAK in template.permitted_actions
        assert HandlerActionType.DEFER in template.permitted_actions
        assert HandlerActionType.OBSERVE in template.permitted_actions
        assert len(template.permitted_actions) == 3  # unknown_action should be skipped
        assert "Unknown action 'unknown_action'" in caplog.text

    async def test_permitted_actions_handles_mixed_and_invalid_types(
        self, create_yaml_file, valid_template_dict, caplog
    ):
        # A YAML file can't contain a Python enum object, so we test with strings and other primitives.
        valid_template_dict["permitted_actions"] = [
            "speak",
            123,  # Invalid type
            "oBsErVe",  # Case-insensitive value match
        ]
        template_path = create_yaml_file("mixed_actions.yaml", valid_template_dict)

        template = await load_template(template_path)

        assert HandlerActionType.SPEAK in template.permitted_actions
        assert HandlerActionType.OBSERVE in template.permitted_actions
        assert len(template.permitted_actions) == 2
        assert "Invalid action type <class 'int'>" in caplog.text
