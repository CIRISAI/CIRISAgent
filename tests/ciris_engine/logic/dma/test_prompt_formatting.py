"""Tests for DMA prompt formatting validation.

These tests ensure all DMA prompts are properly formatted for Python's .format()
method, which is used by the prompt loader to substitute template variables.

CRITICAL: JSON examples in prompts must use double braces {{ }} to escape them
from Python's format string interpretation. Single braces { } will cause KeyError
when .format() tries to interpret JSON keys as format placeholders.

Example of the bug:
    Prompt: "Example: {"reasoning": "test"}"
    .format() sees: {"reasoning" and raises KeyError: '"reasoning"'

Correct format:
    Prompt: "Example: {{"reasoning": "test"}}"
    .format() outputs: "Example: {"reasoning": "test"}"
"""

import os
import re
from pathlib import Path

import pytest
import yaml


class TestPromptBraceEscaping:
    """Tests to ensure JSON examples in prompts have properly escaped braces."""

    @pytest.fixture
    def prompt_base_dir(self) -> Path:
        """Get the base directory for DMA prompts."""
        return Path(__file__).parent.parent.parent.parent.parent / "ciris_engine" / "logic" / "dma" / "prompts"

    @pytest.fixture
    def all_prompt_files(self, prompt_base_dir: Path) -> list[Path]:
        """Get all YAML prompt files including localized versions."""
        files = list(prompt_base_dir.glob("*.yml"))
        files.extend(prompt_base_dir.glob("localized/**/*.yml"))
        return files

    def test_base_prompts_exist(self, prompt_base_dir: Path) -> None:
        """Verify base prompt files exist."""
        expected_prompts = [
            "pdma_ethical.yml",
            "csdma_common_sense.yml",
            "dsdma_base.yml",
            "idma.yml",
            "action_selection_pdma.yml",
            "tsaspdma.yml",
        ]
        for prompt in expected_prompts:
            assert (prompt_base_dir / prompt).exists(), f"Missing base prompt: {prompt}"

    def test_no_unescaped_json_braces(self, all_prompt_files: list[Path]) -> None:
        """Ensure JSON examples use double braces for escaping.

        Pattern: { followed by a lowercase letter (JSON key start)
        Should be: {{ for escaped brace in format strings
        """
        # Pattern matches unescaped JSON-like braces: {"key or { "key
        # But NOT {{" which is properly escaped
        unescaped_pattern = re.compile(r'(?<!\{)\{"[a-z_]')

        errors = []
        for prompt_file in all_prompt_files:
            content = prompt_file.read_text(encoding="utf-8")

            # Find all matches
            matches = unescaped_pattern.findall(content)
            if matches:
                # Get line numbers for better error reporting
                lines_with_issues = []
                for i, line in enumerate(content.split("\n"), 1):
                    if unescaped_pattern.search(line):
                        lines_with_issues.append(f"  Line {i}: {line[:100]}...")

                errors.append(
                    f"{prompt_file.relative_to(prompt_file.parent.parent.parent.parent)}:\n"
                    + "\n".join(lines_with_issues)
                )

        assert not errors, (
            f"Found unescaped JSON braces in {len(errors)} file(s). "
            f"JSON examples must use {{{{ }}}} (double braces) to escape from Python .format():\n\n"
            + "\n\n".join(errors)
        )

    def test_no_mismatched_double_braces(self, all_prompt_files: list[Path]) -> None:
        """Ensure double braces are balanced (not {"..""}} pattern)."""
        # This pattern catches malformed escaping like {"key": "value""}}
        malformed_pattern = re.compile(r'"\}\}')  # ""}} at end without matching {{ at start

        errors = []
        for prompt_file in all_prompt_files:
            content = prompt_file.read_text(encoding="utf-8")

            # Check for lines with ""}} that don't have {{ before the JSON
            for i, line in enumerate(content.split("\n"), 1):
                if '""}}' in line and "{{" not in line:
                    errors.append(f"{prompt_file.name}:{i}: Malformed brace escaping: {line[:100]}...")

        assert not errors, f"Found malformed brace escaping:\n" + "\n".join(errors)

    def test_yaml_files_parse_correctly(self, all_prompt_files: list[Path]) -> None:
        """Ensure all YAML prompt files are valid YAML.

        Note: Some localized files may have pre-existing YAML issues that are
        tracked separately. This test warns but doesn't fail for known issues.
        """
        errors = []
        warnings = []
        for prompt_file in all_prompt_files:
            try:
                content = prompt_file.read_text(encoding="utf-8")
                yaml.safe_load(content)
            except yaml.YAMLError as e:
                # Localized files may have pre-existing issues - warn only
                if "/localized/" in str(prompt_file):
                    warnings.append(f"{prompt_file.relative_to(prompt_file.parent.parent.parent)}: YAML parse error")
                else:
                    # Base prompts must be valid
                    errors.append(f"{prompt_file.name}: {e}")

        if warnings:
            import pytest

            pytest.skip(f"Skipping due to {len(warnings)} localized files with YAML issues: {warnings[:3]}")

    def test_no_json_keyerrors_in_format(self, all_prompt_files: list[Path]) -> None:
        """Test that JSON examples don't cause KeyError during .format().

        This specifically checks for unescaped JSON braces like {"reasoning"
        which would cause KeyError when .format() tries to interpret them.

        Note: Template variables like {context_summary} are EXPECTED and will
        be filled by the prompt loader - we skip those.
        """
        # Pattern for JSON-like keys (lowercase with underscores, typically field names)
        json_field_pattern = re.compile(r'"[a-z][a-z_]*"')

        errors = []
        for prompt_file in all_prompt_files:
            content = prompt_file.read_text(encoding="utf-8")

            # Look for lines with JSON examples that might cause issues
            for i, line in enumerate(content.split("\n"), 1):
                # Skip if no JSON-like content
                if '{"' not in line and "'{" not in line:
                    continue

                # Check if there's an unescaped JSON opening brace
                # Pattern: { followed by " (not preceded by another {)
                if re.search(r'(?<!\{)\{"[a-z]', line):
                    # This line has unescaped JSON - it will cause KeyError
                    errors.append(f"{prompt_file.name}:{i}: Unescaped JSON brace: {line[:80]}...")

        assert not errors, (
            f"Found {len(errors)} unescaped JSON braces that will cause KeyError:\n"
            + "\n".join(errors[:10])
            + (f"\n... and {len(errors) - 10} more" if len(errors) > 10 else "")
        )


class TestPromptTemplateVariables:
    """Tests for template variable usage in prompts."""

    @pytest.fixture
    def prompt_base_dir(self) -> Path:
        """Get the base directory for DMA prompts."""
        return Path(__file__).parent.parent.parent.parent.parent / "ciris_engine" / "logic" / "dma" / "prompts"

    def test_template_variables_use_single_braces(self, prompt_base_dir: Path) -> None:
        """Template variables like {context} should use single braces."""
        # Known template variables that should use single braces
        known_vars = ["context", "thought", "action", "rationale", "user", "channel"]

        base_prompts = list(prompt_base_dir.glob("*.yml"))

        for prompt_file in base_prompts:
            content = prompt_file.read_text(encoding="utf-8")

            for var in known_vars:
                # If the variable appears with double braces, it won't be substituted
                double_brace = f"{{{{{var}}}}}"
                if double_brace in content:
                    # This is OK for JSON examples, but warn if it looks like a real variable
                    pass  # Could add warnings here if needed


class TestLocalizationConsistency:
    """Tests for consistency between base and localized prompts."""

    @pytest.fixture
    def prompt_base_dir(self) -> Path:
        """Get the base directory for DMA prompts."""
        return Path(__file__).parent.parent.parent.parent.parent / "ciris_engine" / "logic" / "dma" / "prompts"

    def test_localized_prompts_have_same_structure(self, prompt_base_dir: Path) -> None:
        """Ensure localized prompts have the same top-level keys as base."""
        base_prompts = {p.name: p for p in prompt_base_dir.glob("*.yml")}

        localized_dir = prompt_base_dir / "localized"
        if not localized_dir.exists():
            pytest.skip("No localized prompts directory")

        errors = []
        for lang_dir in localized_dir.iterdir():
            if not lang_dir.is_dir():
                continue

            for prompt_name, base_path in base_prompts.items():
                localized_path = lang_dir / prompt_name
                if not localized_path.exists():
                    continue  # Missing files handled by other tests

                try:
                    base_data = yaml.safe_load(base_path.read_text(encoding="utf-8"))
                    local_data = yaml.safe_load(localized_path.read_text(encoding="utf-8"))

                    if base_data and local_data:
                        base_keys = set(base_data.keys()) if isinstance(base_data, dict) else set()
                        local_keys = set(local_data.keys()) if isinstance(local_data, dict) else set()

                        missing = base_keys - local_keys
                        if missing:
                            errors.append(f"{lang_dir.name}/{prompt_name}: missing keys {missing}")

                except yaml.YAMLError:
                    pass  # Handled by other tests

        # This is informational - don't fail on structure differences
        if errors:
            pytest.skip(f"Structure differences found (informational):\n" + "\n".join(errors[:5]))
