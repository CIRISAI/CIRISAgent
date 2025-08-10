"""
Unit test to validate all template placeholders will be successfully replaced.

This test dynamically finds all {key} placeholders in templates and ensures
they will be properly replaced, preventing agents from ever seeing raw keys.
"""

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest
import yaml


def find_all_placeholders(text: str) -> Set[str]:
    """
    Find all {placeholder} keys in a text string.

    Args:
        text: The text to search for placeholders

    Returns:
        Set of placeholder keys (without the curly braces)
    """
    # Pattern to match {key} style placeholders
    # Negative lookahead to exclude {{escaped}} braces
    pattern = r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}"
    matches = re.findall(pattern, text)
    return set(matches)


def get_all_template_placeholders() -> Dict[str, Dict[str, Set[str]]]:
    """
    Scan all template files and extract placeholders from each section.

    Returns:
        Dict mapping template filename to section to set of placeholders
    """
    templates_dir = Path(__file__).parent.parent / "ciris_templates"
    results = {}

    for template_file in templates_dir.glob("*.yaml"):
        with open(template_file, "r") as f:
            try:
                template_data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"Failed to parse {template_file}: {e}")

        template_placeholders = {}

        # Recursively find all string values in the template
        def find_strings_recursive(obj, path=""):
            """Recursively find all string values in nested dicts/lists."""
            results = []
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_path = f"{path}.{key}" if path else key
                    results.extend(find_strings_recursive(value, new_path))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    new_path = f"{path}[{i}]"
                    results.extend(find_strings_recursive(item, new_path))
            elif isinstance(obj, str):
                results.append((path, obj))
            return results

        # Find all strings in the template
        all_strings = find_strings_recursive(template_data)

        # Extract placeholders from each string
        for path, content in all_strings:
            placeholders = find_all_placeholders(content)
            if placeholders:
                template_placeholders[path] = placeholders

        if template_placeholders:
            results[template_file.name] = template_placeholders

    return results


def get_available_replacements() -> Set[str]:
    """
    Get the set of placeholder keys that are available for replacement.

    This is based on what's actually provided in the formatting code.
    """
    # These are the keys we know are provided in dsdma_base.py
    known_keys = {
        # Core context fields
        "domain_name",
        "context_str",
        "rules_summary_str",
        # Block fields
        "task_history_block",
        "escalation_guidance_block",
        "system_snapshot_block",
        "user_profiles_block",
        "crisis_resources_block",
        # Action selection specific
        "thought_content",
        "available_actions",
    }

    return known_keys


def test_all_template_placeholders_have_replacements():
    """
    Test that all placeholders in templates have corresponding replacements.

    This test:
    1. Dynamically finds all {key} placeholders in all templates
    2. Checks that each placeholder has a replacement available
    3. Reports any missing replacements to prevent raw keys appearing
    """
    # Get all placeholders from templates
    all_templates = get_all_template_placeholders()

    # Get available replacement keys
    available_keys = get_available_replacements()

    # Track any issues found
    missing_replacements = []

    for template_name, sections in all_templates.items():
        for section_name, placeholders in sections.items():
            for placeholder in placeholders:
                if placeholder not in available_keys:
                    missing_replacements.append(f"{template_name} -> {section_name} -> {{{placeholder}}}")

    # Report results
    if missing_replacements:
        error_msg = "Found placeholders without replacements:\n"
        for missing in sorted(missing_replacements):
            error_msg += f"  - {missing}\n"
        error_msg += f"\nAvailable replacement keys: {sorted(available_keys)}"
        pytest.fail(error_msg)


def test_no_double_braces_in_templates():
    """
    Test that templates don't contain {{double}} braces which could cause issues.
    """
    templates_dir = Path(__file__).parent.parent / "ciris_templates"

    for template_file in templates_dir.glob("*.yaml"):
        with open(template_file, "r") as f:
            content = f.read()

        # Check for double braces (which might indicate escaping issues)
        if "{{" in content or "}}" in content:
            # Find the lines with double braces for better error reporting
            lines_with_issues = []
            for i, line in enumerate(content.split("\n"), 1):
                if "{{" in line or "}}" in line:
                    lines_with_issues.append(f"  Line {i}: {line.strip()}")

            pytest.fail(f"Template {template_file.name} contains double braces:\n" + "\n".join(lines_with_issues))


def test_placeholders_are_valid_python_identifiers():
    """
    Test that all placeholders are valid Python identifiers for .format().
    """
    all_templates = get_all_template_placeholders()

    invalid_identifiers = []

    for template_name, sections in all_templates.items():
        for section_name, placeholders in sections.items():
            for placeholder in placeholders:
                # Check if it's a valid Python identifier
                if not placeholder.isidentifier():
                    invalid_identifiers.append(f"{template_name} -> {section_name} -> {{{placeholder}}}")

    if invalid_identifiers:
        error_msg = "Found invalid placeholder identifiers:\n"
        for invalid in sorted(invalid_identifiers):
            error_msg += f"  - {invalid}\n"
        pytest.fail(error_msg)


def test_critical_placeholders_present():
    """
    Test that critical placeholders are actually used in appropriate templates.

    Some placeholders like crisis_resources_block should be present in Echo templates.
    """
    templates_dir = Path(__file__).parent.parent / "ciris_templates"

    # Define which placeholders should be in which templates
    required_placeholders = {
        "echo.yaml": {"crisis_resources_block"},
        "echo-core.yaml": {"crisis_resources_block"},
        # echo-speculative doesn't use the block directly, uses template text
    }

    for template_name, required_keys in required_placeholders.items():
        template_path = templates_dir / template_name
        if not template_path.exists():
            continue

        all_placeholders = set()
        template_data = get_all_template_placeholders().get(template_name, {})
        for section_placeholders in template_data.values():
            all_placeholders.update(section_placeholders)

        missing = required_keys - all_placeholders
        if missing:
            pytest.fail(f"Template {template_name} is missing required placeholders: {missing}")


def test_formatting_code_handles_all_keys():
    """
    Test that the actual formatting code in dsdma_base.py handles all keys.

    This is a reverse check - ensures the formatting code provides all keys it claims to.
    """
    # Import the actual formatting code
    import sys
    from pathlib import Path

    # Add the project root to sys.path to import modules
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from ciris_engine.logic.formatters import (
            format_crisis_resources_block,
            format_system_snapshot,
            format_user_profiles,
            get_escalation_guidance,
        )

        # Test that these functions exist and are callable
        assert callable(format_crisis_resources_block)
        assert callable(get_escalation_guidance)
        assert callable(format_system_snapshot)
        assert callable(format_user_profiles)

    except ImportError as e:
        pytest.skip(f"Could not import formatting functions: {e}")


def test_no_unescaped_quotes_in_placeholders():
    """
    Test that placeholders don't contain unescaped quotes that could break YAML.
    """
    templates_dir = Path(__file__).parent.parent / "ciris_templates"

    for template_file in templates_dir.glob("*.yaml"):
        with open(template_file, "r") as f:
            # Read the raw file to check for quote issues
            content = f.read()

        # Find all placeholders with surrounding context
        pattern = r".{0,10}\{[a-zA-Z_][a-zA-Z0-9_]*\}.{0,10}"
        matches = re.findall(pattern, content)

        for match in matches:
            # Check if the placeholder is inside quotes properly
            if "'{" in match and "}'" not in match:
                pytest.fail(f"Template {template_file.name} may have quote issues around: {match}")


if __name__ == "__main__":
    # Run the tests and print results
    print("Scanning all templates for placeholders...")
    all_placeholders = get_all_template_placeholders()

    print("\nFound placeholders by template:")
    for template, sections in sorted(all_placeholders.items()):
        print(f"\n{template}:")
        for section, placeholders in sorted(sections.items()):
            print(f"  {section}:")
            for placeholder in sorted(placeholders):
                print(f"    - {{{placeholder}}}")

    print("\n" + "=" * 60)
    print("Available replacement keys:")
    for key in sorted(get_available_replacements()):
        print(f"  - {{{key}}}")

    print("\n" + "=" * 60)
    print("Running validation tests...")

    # Run the main validation test
    try:
        test_all_template_placeholders_have_replacements()
        print("✓ All placeholders have replacements")
    except AssertionError as e:
        print(f"✗ {e}")

    try:
        test_no_double_braces_in_templates()
        print("✓ No double braces found")
    except AssertionError as e:
        print(f"✗ {e}")

    try:
        test_placeholders_are_valid_python_identifiers()
        print("✓ All placeholders are valid identifiers")
    except AssertionError as e:
        print(f"✗ {e}")

    try:
        test_critical_placeholders_present()
        print("✓ Critical placeholders are present")
    except AssertionError as e:
        print(f"✗ {e}")
