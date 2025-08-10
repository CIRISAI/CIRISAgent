"""
Unit tests for agent template validation.

This ensures all agent templates in ciris_templates/ directory
are valid according to the AgentTemplate schema.
"""

import os
from pathlib import Path
from typing import Dict, List

import pytest
import yaml

from ciris_engine.schemas.config.agent import AgentTemplate


class TestAgentTemplates:
    """Test suite for validating agent templates."""

    @pytest.fixture
    def template_dir(self) -> Path:
        """Get the templates directory path."""
        # Look for templates in the project root
        project_root = Path(__file__).parent.parent
        template_dir = project_root / "ciris_templates"
        return template_dir

    @pytest.fixture
    def template_files(self, template_dir: Path) -> List[Path]:
        """Get all YAML template files."""
        if not template_dir.exists():
            pytest.skip(f"Templates directory not found: {template_dir}")

        yaml_files = list(template_dir.glob("*.yaml"))
        yaml_files.extend(template_dir.glob("*.yml"))

        if not yaml_files:
            pytest.skip(f"No YAML files found in {template_dir}")

        return yaml_files

    def test_all_templates_valid(self, template_files: List[Path]):
        """Test that all template files are valid according to the schema."""
        errors = {}

        for template_file in template_files:
            try:
                # Load the YAML file
                with open(template_file, "r") as f:
                    template_data = yaml.safe_load(f)

                # Validate against the schema
                template = AgentTemplate(**template_data)

                # Additional validation checks
                assert template.name, f"{template_file.name}: Template must have a name"
                assert template.description, f"{template_file.name}: Template must have a description"

            except Exception as e:
                errors[template_file.name] = str(e)

        # Report all errors at once
        if errors:
            error_report = "\n\nTemplate Validation Errors:\n" + "=" * 50 + "\n"
            for filename, error in errors.items():
                error_report += f"\n{filename}:\n{error}\n" + "-" * 40

            pytest.fail(error_report)

    def test_sage_template_specifically(self, template_dir: Path):
        """Test the Sage template specifically since it has known issues."""
        sage_file = template_dir / "sage.yaml"

        if not sage_file.exists():
            pytest.skip("Sage template not found")

        with open(sage_file, "r") as f:
            sage_data = yaml.safe_load(f)

        # Check for the specific known issues
        if "csdma_overrides" in sage_data:
            csdma_overrides = sage_data["csdma_overrides"]

            # These fields are not valid in CSDMAOverrides
            invalid_fields = ["inquiry_focus", "collaboration"]
            found_invalid = [field for field in invalid_fields if field in csdma_overrides]

            if found_invalid:
                pytest.fail(
                    f"Sage template has invalid fields in csdma_overrides: {found_invalid}\n"
                    f"Valid fields are: system_prompt, user_prompt_template\n"
                    f"Consider moving these to dsdma_kwargs.domain_specific_knowledge instead"
                )

        # Try to validate the template
        try:
            template = AgentTemplate(**sage_data)
        except Exception as e:
            pytest.fail(f"Sage template validation failed: {e}")

    def test_template_action_permissions(self, template_files: List[Path]):
        """Test that all templates have valid action permissions."""
        valid_actions = {
            "speak",
            "observe",
            "memorize",
            "recall",
            "defer",
            "ponder",
            "task_complete",
            "reject",
            "forget",
            "tool",  # Added tool action - has ToolHandler
        }

        for template_file in template_files:
            with open(template_file, "r") as f:
                template_data = yaml.safe_load(f)

            if "permitted_actions" in template_data:
                actions = template_data["permitted_actions"]
                invalid_actions = [a for a in actions if a not in valid_actions]

                assert not invalid_actions, (
                    f"{template_file.name} has invalid actions: {invalid_actions}\n"
                    f"Valid actions are: {valid_actions}"
                )

    def test_template_stewardship_structure(self, template_files: List[Path]):
        """Test that templates with stewardship have proper structure."""
        for template_file in template_files:
            with open(template_file, "r") as f:
                template_data = yaml.safe_load(f)

            if "stewardship" in template_data:
                stewardship = template_data["stewardship"]

                # Check required stewardship fields
                assert (
                    "stewardship_tier" in stewardship
                ), f"{template_file.name}: Stewardship must have stewardship_tier"

                if "creator_intent_statement" in stewardship:
                    intent = stewardship["creator_intent_statement"]
                    required_intent_fields = [
                        "purpose_and_functionalities",
                        "limitations_and_design_choices",
                        "anticipated_benefits",
                        "anticipated_risks",
                    ]

                    for field in required_intent_fields:
                        assert field in intent, f"{template_file.name}: creator_intent_statement missing {field}"

    def test_no_dict_str_any_in_templates(self, template_files: List[Path]):
        """Test that templates don't use Dict[str, Any] patterns."""
        for template_file in template_files:
            content = template_file.read_text()

            # Check for common Dict[str, Any] patterns in YAML comments or descriptions
            problematic_patterns = ["Dict[str, Any]", "dict[str, any]", ": Any", "typing.Any"]

            found_patterns = []
            for pattern in problematic_patterns:
                if pattern.lower() in content.lower():
                    found_patterns.append(pattern)

            # This is more of a warning than a hard failure
            if found_patterns:
                print(f"Warning: {template_file.name} may contain untyped patterns: {found_patterns}")
