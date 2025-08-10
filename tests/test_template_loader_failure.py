"""
Test that invalid templates cause failures instead of falling back to default.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from ciris_engine.logic.utils.profile_loader import load_template


class TestTemplateLoaderFailure:
    """Test that template loader fails properly instead of falling back."""

    @pytest.mark.asyncio
    async def test_missing_template_file_raises_error(self):
        """Test that a missing template file raises FileNotFoundError."""
        non_existent_path = Path("/tmp/non_existent_template.yaml")

        with pytest.raises(FileNotFoundError) as exc_info:
            await load_template(non_existent_path)

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_yaml_raises_error(self):
        """Test that invalid YAML raises ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            # Write invalid YAML
            f.write("invalid: yaml: content: [[[")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError) as exc_info:
                await load_template(temp_path)

            assert "Error parsing YAML" in str(exc_info.value)
        finally:
            temp_path.unlink()

    @pytest.mark.asyncio
    async def test_validation_error_raises_error(self):
        """Test that template validation errors raise ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            # Write valid YAML but invalid template schema
            invalid_template = {
                "name": "invalid",
                "description": "Invalid template",
                # Missing required field: role_description
                "csdma_overrides": {
                    # Invalid fields that should fail validation
                    "invalid_field": "should fail",
                    "another_invalid": "also should fail",
                },
            }
            yaml.dump(invalid_template, f)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError) as exc_info:
                await load_template(temp_path)

            assert "Template validation failed" in str(exc_info.value) or "Extra inputs are not permitted" in str(
                exc_info.value
            )
        finally:
            temp_path.unlink()

    @pytest.mark.asyncio
    async def test_valid_template_loads_successfully(self):
        """Test that a valid template loads successfully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            # Write a valid minimal template
            valid_template = {
                "name": "test",
                "description": "Test template",
                "role_description": "Test role",
                "permitted_actions": ["speak", "observe"],
            }
            yaml.dump(valid_template, f)
            temp_path = Path(f.name)

        try:
            template = await load_template(temp_path)
            assert template is not None
            assert template.name == "test"
            assert template.description == "Test template"
        finally:
            temp_path.unlink()

    @pytest.mark.asyncio
    async def test_no_fallback_to_default(self):
        """Ensure there's no fallback to default template on error."""
        # Create an invalid template
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            invalid_template = {
                "name": "invalid",
                # Invalid: missing required fields
            }
            yaml.dump(invalid_template, f)
            temp_path = Path(f.name)

        try:
            # This should raise an error, not fall back to default
            with pytest.raises(ValueError):
                await load_template(temp_path)

            # If we get here without an exception, the test should fail
            # because it means the loader returned a default template
        finally:
            temp_path.unlink()
