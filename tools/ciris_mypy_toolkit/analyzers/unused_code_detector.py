"""
Unused Code Detector - Finds uncalled logic and unused internal methods
"""

import ast
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


class UnusedCodeDetector:
    """
    Detects unused and uncalled code in the CIRIS codebase.

    Key detection:
    - Unused functions and methods
    - Unreferenced classes
    - Dead code branches
    - Unused imports
    - Internal methods that should be public or removed
    """

    def __init__(self, target_dir: Path):
        self.target_dir = Path(target_dir)
        self.all_definitions = {}  # file -> {type: name -> line}
        self.all_references = {}  # file -> {name -> [lines]}
        self.scan_complete = False
        self.whitelist = self._load_whitelist()
        self.pydantic_decorators = {
            "field_validator",
            "model_validator",
            "field_serializer",
            "model_serializer",
            "computed_field",
            "property",
        }

    def _load_whitelist(self) -> Set[str]:
        """Load vulture whitelist if it exists."""
        whitelist_names = set()
        whitelist_path = self.target_dir.parent / "vulture_whitelist.py"

        if whitelist_path.exists():
            try:
                with open(whitelist_path, "r") as f:
                    content = f.read()
                # Extract whitelisted names from _. patterns
                import re

                matches = re.findall(r"_\.(\w+)", content)
                whitelist_names.update(matches)
                logger.info(f"Loaded {len(whitelist_names)} names from vulture whitelist")
            except Exception as e:
                logger.warning(f"Could not load vulture whitelist: {e}")

        return whitelist_names

    def find_unused_code(self) -> List[Dict[str, Any]]:
        """Find all types of unused code across the codebase."""
        if not self.scan_complete:
            self._scan_codebase()

        unused_items = []

        # Find unused functions and methods
        unused_items.extend(self._find_unused_functions())

        # Find unused classes
        unused_items.extend(self._find_unused_classes())

        # Find unused imports
        unused_items.extend(self._find_unused_imports())

        # Find dead code branches
        unused_items.extend(self._find_dead_code())

        # Find internal methods that could be removed
        unused_items.extend(self._find_questionable_internal_methods())

        return unused_items

    def _scan_codebase(self):
        """Scan entire codebase to build definition and reference maps."""
        logger.info("Scanning codebase for definitions and references...")

        for py_file in self.target_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                # Parse definitions and references
                self.all_definitions[str(py_file)] = self._extract_definitions(content)
                self.all_references[str(py_file)] = self._extract_references(content)

            except Exception as e:
                logger.warning(f"Could not scan {py_file}: {e}")

        self.scan_complete = True

    def _extract_definitions(self, content: str) -> Dict[str, Dict[str, int]]:
        """Extract all function, class, and variable definitions."""
        definitions = {"functions": {}, "classes": {}, "methods": {}, "variables": {}}

        try:
            tree = ast.parse(content)

            # First pass: mark parent relationships
            for parent in ast.walk(tree):
                for child in ast.iter_child_nodes(parent):
                    child.parent = parent

            # Second pass: extract definitions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    # Determine if it's a method or function
                    parent = getattr(node, "parent", None)
                    if isinstance(parent, ast.ClassDef):
                        definitions["methods"][node.name] = node.lineno
                    else:
                        definitions["functions"][node.name] = node.lineno

                elif isinstance(node, ast.ClassDef):
                    definitions["classes"][node.name] = node.lineno

                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            definitions["variables"][target.id] = node.lineno

        except SyntaxError:
            # Skip files with syntax errors
            pass

        return definitions

    def _extract_references(self, content: str) -> Dict[str, List[int]]:
        """Extract all name references (function calls, variable usage, etc.)."""
        references = defaultdict(list)

        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    references[node.id].append(node.lineno)
                elif isinstance(node, ast.Call):
                    # Handle different call types safely
                    if hasattr(node, "func"):
                        if isinstance(node.func, ast.Name):
                            references[node.func.id].append(node.lineno)
                        elif isinstance(node.func, ast.Attribute) and hasattr(node.func, "attr"):
                            references[node.func.attr].append(node.lineno)
                elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                    if hasattr(node, "attr"):
                        references[node.attr].append(node.lineno)

        except (SyntaxError, AttributeError) as e:
            logger.debug(f"Could not extract references: {e}")

        return dict(references)

    def _find_unused_functions(self) -> List[Dict[str, Any]]:
        """Find functions that are defined but never called."""
        unused = []

        for file_path, definitions in self.all_definitions.items():
            for func_name, line_num in definitions.get("functions", {}).items():
                # Skip special functions
                if func_name.startswith("__") or func_name in ["main"]:
                    continue

                # Skip whitelisted names
                if func_name in self.whitelist:
                    continue

                # Skip FastAPI route handlers (common pattern)
                if self._is_route_handler(file_path, func_name):
                    continue

                # Check if function is referenced anywhere
                is_referenced = self._is_name_referenced(func_name)

                if not is_referenced:
                    unused.append(
                        {
                            "type": "unused_function",
                            "file": file_path,
                            "line": line_num,
                            "name": func_name,
                            "issue": f"Function '{func_name}' is defined but never called",
                            "fix_suggestion": "Remove function or add proper usage",
                        }
                    )

        return unused

    def _find_unused_classes(self) -> List[Dict[str, Any]]:
        """Find classes that are defined but never instantiated or referenced."""
        unused = []

        for file_path, definitions in self.all_definitions.items():
            for class_name, line_num in definitions.get("classes", {}).items():
                # Skip special classes and base classes
                if class_name.startswith("Base") or class_name.endswith("Interface"):
                    continue

                # Skip whitelisted names
                if class_name in self.whitelist:
                    continue

                # Skip Pydantic models and schemas (often used for validation/serialization)
                if class_name.endswith(("Model", "Schema", "Config", "Request", "Response")):
                    continue

                is_referenced = self._is_name_referenced(class_name)

                if not is_referenced:
                    unused.append(
                        {
                            "type": "unused_class",
                            "file": file_path,
                            "line": line_num,
                            "name": class_name,
                            "issue": f"Class '{class_name}' is defined but never used",
                            "fix_suggestion": "Remove class or add proper usage",
                        }
                    )

        return unused

    def _find_unused_imports(self) -> List[Dict[str, Any]]:
        """Find imports that are never used."""
        unused = []

        for py_file in self.target_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                # Find import statements
                import_names = self._extract_import_names(content)
                references = self.all_references.get(str(py_file), {})

                for import_name, line_num in import_names.items():
                    if import_name not in references:
                        unused.append(
                            {
                                "type": "unused_import",
                                "file": str(py_file),
                                "line": line_num,
                                "name": import_name,
                                "issue": f"Import '{import_name}' is never used",
                                "fix_suggestion": "Remove unused import",
                            }
                        )

            except Exception as e:
                logger.warning(f"Could not check imports in {py_file}: {e}")

        return unused

    def _extract_import_names(self, content: str) -> Dict[str, int]:
        """Extract imported names and their line numbers."""
        imports = {}

        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name.split(".")[0]
                        imports[name] = node.lineno

                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        if name != "*":  # Skip wildcard imports
                            imports[name] = node.lineno

        except SyntaxError:
            pass

        return imports

    def _find_dead_code(self) -> List[Dict[str, Any]]:
        """Find unreachable code branches."""
        dead_code = []

        for py_file in self.target_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                # Look for obvious dead code patterns
                lines = content.split("\n")

                for i, line in enumerate(lines, 1):
                    stripped = line.strip()

                    # Code after return/raise statements
                    if i < len(lines) and (stripped.startswith("return ") or stripped.startswith("raise ")):
                        next_line = lines[i].strip() if i < len(lines) else ""
                        if next_line and not next_line.startswith(("def ", "class ", "#", "except", "finally")):
                            dead_code.append(
                                {
                                    "type": "dead_code",
                                    "file": str(py_file),
                                    "line": i + 1,
                                    "issue": "Code after return/raise statement is unreachable",
                                    "fix_suggestion": "Remove unreachable code",
                                }
                            )

                    # Code in if False blocks
                    if stripped.startswith("if False:"):
                        dead_code.append(
                            {
                                "type": "dead_code",
                                "file": str(py_file),
                                "line": i,
                                "issue": "Code in 'if False:' block is unreachable",
                                "fix_suggestion": "Remove dead conditional block",
                            }
                        )

            except Exception as e:
                logger.warning(f"Could not check dead code in {py_file}: {e}")

        return dead_code

    def _find_questionable_internal_methods(self) -> List[Dict[str, Any]]:
        """Find internal methods that might be unnecessary or should be public."""
        questionable = []

        for file_path, definitions in self.all_definitions.items():
            for method_name, line_num in definitions.get("methods", {}).items():
                # Check private methods that are only called within the same file
                if method_name.startswith("_") and not method_name.startswith("__"):
                    references = self.all_references.get(file_path, {})

                    # Count references to this method
                    ref_count = len(references.get(method_name, []))

                    # If private method is called less than 2 times, question its necessity
                    if ref_count <= 1:
                        questionable.append(
                            {
                                "type": "questionable_private_method",
                                "file": file_path,
                                "line": line_num,
                                "name": method_name,
                                "issue": f"Private method '{method_name}' is rarely used (refs: {ref_count})",
                                "fix_suggestion": "Consider removing or making public if needed elsewhere",
                            }
                        )

        return questionable

    def _is_name_referenced(self, name: str) -> bool:
        """Check if a name is referenced anywhere in the codebase."""
        for file_references in self.all_references.values():
            if name in file_references:
                return True
        return False

    def _is_route_handler(self, file_path: str, func_name: str) -> bool:
        """Check if a function is likely a FastAPI/Flask route handler."""
        if "/routes/" in file_path or "/api/" in file_path:
            # In API route files, most functions are handlers
            return True

        # Check if the file contains route decorators
        try:
            with open(file_path, "r") as f:
                content = f.read()
                # Look for route decorators before the function
                import re

                pattern = rf"@\w+\.(get|post|put|delete|patch|websocket).*\n.*def {func_name}"
                if re.search(pattern, content, re.MULTILINE):
                    return True
        except:
            pass

        return False

    def _is_pydantic_field(self, file_path: str, var_name: str) -> bool:
        """Check if a variable is a Pydantic model field."""
        try:
            with open(file_path, "r") as f:
                content = f.read()
                # Check if in a class that inherits from BaseModel/BaseSchema
                if "BaseModel" in content or "BaseSchema" in content:
                    # Simple heuristic: field assignments in classes
                    import re

                    # Look for class definition and field assignment
                    class_pattern = r"class\s+\w+.*(?:BaseModel|BaseSchema)"
                    field_pattern = rf"^\s+{var_name}\s*[:=]"
                    if re.search(class_pattern, content) and re.search(field_pattern, content, re.MULTILINE):
                        return True
        except:
            pass

        return False

    def propose_cleanup(self) -> Dict[str, Any]:
        """Propose cleanup actions for agent review."""
        logger.info(" Analyzing cleanup opportunities for agent review...")
        return {"total_proposed": 0, "changes": []}  # Stub for now

    def apply_approved_cleanup(self, approved_changes: Dict[str, Any]) -> int:
        """Apply agent-approved cleanup."""
        logger.info(" Applying agent-approved cleanup...")
        return 0  # Stub for now

    def remove_unused_code(self, categories: List[str] = None) -> int:
        """
        Automatically remove safe categories of unused code.

        Args:
            categories: Categories to remove, defaults to safe ones
        """
        if categories is None:
            categories = ["unused_imports"]  # Only safe automatic removal  # type: ignore[unreachable]

        unused_items = self.find_unused_code()
        removed_count = 0

        # Group by file for efficient processing
        files_to_modify = defaultdict(list)

        for item in unused_items:
            if item["type"] in categories:
                files_to_modify[item["file"]].append(item)

        # Process each file
        for file_path, items in files_to_modify.items():
            try:
                with open(file_path, "r") as f:
                    lines = f.readlines()

                # Sort items by line number (descending) to avoid index issues
                items.sort(key=lambda x: x["line"], reverse=True)

                for item in items:
                    if item["type"] == "unused_imports":
                        # Remove the import line
                        del lines[item["line"] - 1]
                        removed_count += 1

                # Write back modified file
                with open(file_path, "w") as f:
                    f.writelines(lines)

                logger.info(f"Removed {len(items)} unused items from {file_path}")

            except Exception as e:
                logger.error(f"Could not modify {file_path}: {e}")

        return removed_count

    def generate_cleanup_report(self) -> Dict[str, Any]:
        """Generate a comprehensive cleanup report."""
        unused_items = self.find_unused_code()

        by_type: Any = defaultdict(int)
        by_file: Any = defaultdict(int)

        for item in unused_items:
            by_type[item["type"]] += 1
            by_file[item["file"]] += 1

        return {
            "total_unused_items": len(unused_items),
            "by_type": dict(by_type),
            "files_with_most_issues": sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:10],
            "safe_to_remove": len([item for item in unused_items if item["type"] in ["unused_imports", "dead_code"]]),
            "detailed_items": unused_items,
        }
