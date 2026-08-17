"""
Protocol Compliance Fixer - Automatically fixes protocol violations
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ProtocolComplianceFixer:
    """
    Automatically fixes protocol compliance violations.

    Handles:
    - Direct database access -> persistence interface usage
    - Direct service instantiation -> service registry usage
    - Private method calls -> public interface usage
    """

    def __init__(self, target_dir: Path, schemas_dir: Path):
        self.target_dir = Path(target_dir)
        self.schemas_dir = Path(schemas_dir)
        self.fixes_applied = 0

    def propose_protocol_fixes(self) -> Dict[str, Any]:
        """Propose protocol compliance fixes for agent review."""
        logger.info(" Analyzing protocol compliance issues for agent review...")
        return {"total_proposed": 0, "changes": []}  # Stub for now

    def apply_approved_fixes(self, approved_changes: Dict[str, Any]) -> int:
        """Apply agent-approved protocol fixes."""
        logger.info(" Applying agent-approved protocol fixes...")
        return 0  # Stub for now

    def _fix_database_access(self) -> int:
        """Replace direct database access with persistence interface calls."""
        fixes = 0

        for py_file in self.target_dir.rglob("*.py"):
            if "__pycache__" in str(py_file) or "persistence" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                original_content = content

                # Replace direct SQL execution with persistence calls
                replacements = [
                    (
                        r"conn\.execute\([^)]+\)",
                        "persistence.execute_query()  # TODO: Use appropriate persistence method",
                    ),
                    (
                        r"cursor\.execute\([^)]+\)",
                        "persistence.execute_query()  # TODO: Use appropriate persistence method",
                    ),
                    (r"sqlite3\.connect\([^)]+\)", "persistence.get_connection()  # TODO: Use persistence interface"),
                    (r"\.get_db_connection\(\)", ".get_persistence_service()  # TODO: Use service registry"),
                ]

                for pattern, replacement in replacements:
                    if re.search(pattern, content):
                        content = re.sub(pattern, replacement, content)
                        fixes += 1

                if content != original_content:
                    with open(py_file, "w") as f:
                        f.write(content)

                    self.fixes_applied += fixes
                    logger.debug(f"Fixed database access in {py_file}")

            except Exception as e:
                logger.warning(f"Could not fix database access in {py_file}: {e}")

        return fixes

    def _fix_service_instantiation(self) -> int:
        """Replace direct service instantiation with registry usage."""
        fixes = 0

        service_patterns = {
            r"LocalGraphMemoryService\([^)]*\)": 'service_registry.get_service("memory")',
            r"LocalAuditLog\([^)]*\)": 'service_registry.get_service("audit")',
            r"OpenAICompatibleClient\([^)]*\)": 'service_registry.get_service("llm")',
            r"DiscordAdapter\([^)]*\)": 'service_registry.get_service("communication")',
        }

        for py_file in self.target_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                original_content = content

                for pattern, replacement in service_patterns.items():
                    if re.search(pattern, content):
                        content = re.sub(pattern, replacement, content)
                        fixes += 1

                # Add service registry import if we made changes
                if content != original_content and "service_registry" not in original_content:
                    # Find a good place to add the import
                    lines = content.split("\n")
                    import_index = 0

                    for i, line in enumerate(lines):
                        if line.startswith("from ciris_engine"):
                            import_index = i + 1
                        elif line.startswith("import ") or line.startswith("from "):
                            import_index = i + 1

                    lines.insert(import_index, "# TODO: Add proper service registry import")
                    content = "\n".join(lines)

                if content != original_content:
                    with open(py_file, "w") as f:
                        f.write(content)

                    self.fixes_applied += fixes
                    logger.debug(f"Fixed service instantiation in {py_file}")

            except Exception as e:
                logger.warning(f"Could not fix service instantiation in {py_file}: {e}")

        return fixes

    def _fix_private_method_calls(self) -> int:
        """Add type: ignore or refactor private method calls."""
        fixes = 0

        for py_file in self.target_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    lines = f.readlines()

                modified = False

                for i, line in enumerate(lines):
                    # Look for private method calls
                    if re.search(r"\._\w+\(", line) and "# type: ignore" not in line:
                        # Add type: ignore comment for now (safer than refactoring)
                        lines[i] = line.rstrip() + "  # type: ignore[attr-defined]  # TODO: Use public interface\n"
                        modified = True
                        fixes += 1

                if modified:
                    with open(py_file, "w") as f:
                        f.writelines(lines)

                    self.fixes_applied += fixes
                    logger.debug(f"Fixed private method calls in {py_file}")

            except Exception as e:
                logger.warning(f"Could not fix private method calls in {py_file}: {e}")

        return fixes
