"""
Schema Alignment Fixer - Automatically fixes schema compliance issues
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class SchemaAlignmentFixer:
    """
    Automatically fixes schema alignment issues.

    Handles:
    - Converting dict usage to proper schema classes
    - Updating deprecated schema imports to v1
    - Fixing legacy field usage
    """

    def __init__(self, target_dir: Path, schemas_dir: Path):
        self.target_dir = Path(target_dir)
        self.schemas_dir = Path(schemas_dir)
        self.fixes_applied = 0

    def propose_schema_fixes(self) -> Dict[str, Any]:
        """Propose schema alignment fixes for agent review."""
        logger.info(" Analyzing schema alignment issues for agent review...")
        return {"total_proposed": 0, "changes": []}  # Stub for now

    def apply_approved_fixes(self, approved_changes: Dict[str, Any]) -> int:
        """Apply agent-approved schema fixes."""
        logger.info(" Applying agent-approved schema fixes...")
        return 0  # Stub for now

    def _fix_schema_imports(self) -> int:
        """Update non-v1 schema imports to v1 versions."""
        fixes = 0

        for py_file in self.target_dir.rglob("*.py"):
            if "__pycache__" in str(py_file) or "schemas" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                original_content = content

                # Update schema imports to v1 versions
                schema_replacements = [
                    (r"from ciris_engine\.schemas\.([^_\s]+) import", r"from ciris_engine.schemas.\1_v1 import"),
                    (r"from \.\.schemas\.([^_\s]+) import", r"from ..schemas.\1_v1 import"),
                    (r"import ciris_engine\.schemas\.([^_\s]+)", r"import ciris_engine.schemas.\1_v1"),
                ]

                for pattern, replacement in schema_replacements:
                    content = re.sub(pattern, replacement, content)

                if content != original_content:
                    with open(py_file, "w") as f:
                        f.write(content)

                    # Count the number of import fixes
                    import_fixes = len(re.findall(r"_v1 import", content)) - len(
                        re.findall(r"_v1 import", original_content)
                    )
                    fixes += import_fixes
                    self.fixes_applied += import_fixes

                    if import_fixes > 0:
                        logger.debug(f"Updated {import_fixes} schema imports in {py_file}")

            except Exception as e:
                logger.warning(f"Could not fix schema imports in {py_file}: {e}")

        return fixes

    def _fix_legacy_field_usage(self) -> int:
        """Replace legacy field names with v1 equivalents."""
        fixes = 0

        # Map of legacy field names to v1 equivalents
        field_replacements = {
            r"\.processing_context": ".context  # Updated to v1 field",
            r"\.legacy_\w+": ".# TODO: Replace with v1 field",
            r'context\["processing_context"\]': 'context["context"]  # Updated to v1',
            r'getattr\([^,]+,\s*["\']processing_context["\']': 'getattr(obj, "context"  # Updated to v1',
        }

        for py_file in self.target_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                original_content = content

                for pattern, replacement in field_replacements.items():
                    if re.search(pattern, content):
                        content = re.sub(pattern, replacement, content)
                        fixes += 1

                if content != original_content:
                    with open(py_file, "w") as f:
                        f.write(content)

                    self.fixes_applied += fixes
                    logger.debug(f"Fixed legacy field usage in {py_file}")

            except Exception as e:
                logger.warning(f"Could not fix legacy field usage in {py_file}: {e}")

        return fixes

    def _add_schema_todos(self) -> int:
        """Add TODO comments for dict usage that should be schemas."""
        fixes = 0

        for py_file in self.target_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    lines = f.readlines()

                modified = False

                for i, line in enumerate(lines):
                    # Look for dict literals that could be schemas
                    schema_patterns = [
                        (r'\{\s*["\']task_id["\']', "Task schema"),
                        (r'\{\s*["\']thought_id["\']', "Thought schema"),
                        (r'\{\s*["\']action_type["\']', "Action schema"),
                        (r'\{\s*["\']status["\'].*["\']timestamp["\']', "Status schema"),
                        (r"result\s*=\s*\{", "Result schema"),
                    ]

                    for pattern, schema_type in schema_patterns:
                        if re.search(pattern, line) and "TODO" not in line:
                            # Add TODO comment on the line above
                            indent = re.match(r"^(\s*)", line).group(1)
                            todo_line = f"{indent}# TODO: Consider using {schema_type} instead of dict\n"
                            lines.insert(i, todo_line)
                            modified = True
                            fixes += 1
                            break  # Only add one TODO per line

                if modified:
                    with open(py_file, "w") as f:
                        f.writelines(lines)

                    self.fixes_applied += fixes
                    logger.debug(f"Added schema TODOs to {py_file}")

            except Exception as e:
                logger.warning(f"Could not add schema TODOs to {py_file}: {e}")

        return fixes
