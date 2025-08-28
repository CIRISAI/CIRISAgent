#!/usr/bin/env python3
"""
CIRIS Orphan Code Analyzer

This tool analyzes supposedly orphaned classes to determine if they're actually used.
Many classes might appear orphaned due to dynamic imports, string-based loading,
or usage in configuration files.
"""
import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Set


class OrphanAnalyzer:
    """Analyzes orphaned classes to find hidden usage."""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.ciris_root = self.project_root / "ciris_engine"

        # Load audit results
        import json

        with open("ciris_audit_report.json", "r") as f:
            self.audit_data = json.load(f)

        self.orphaned_classes = set()
        self.usage_patterns = defaultdict(list)
        self.dynamic_imports = []
        self.string_references = defaultdict(list)

    def analyze(self):
        """Run comprehensive orphan analysis."""
        print("🔍 Analyzing Orphaned Classes...\n")

        # Get orphaned classes
        self._identify_orphans()

        # Check for dynamic imports
        self._find_dynamic_imports()

        # Check for string-based references
        self._find_string_references()

        # Check configuration files
        self._check_config_files()

        # Check entry points
        self._check_entry_points()

        # Categorize orphans
        self._categorize_orphans()

        # Generate report
        self._generate_report()

    def _identify_orphans(self):
        """Identify orphaned classes from audit."""
        for finding in self.audit_data.get("findings", {}).get("orphaned_code", []):
            self.orphaned_classes.add(finding["class"])
        print(f"📊 Found {len(self.orphaned_classes)} potentially orphaned classes")

    def _find_dynamic_imports(self):
        """Find dynamic imports that might use orphaned classes."""
        print("\n🔎 Searching for dynamic imports...")

        patterns = [
            r'importlib\.import_module\(["\']([^"\']+)["\']\)',
            r'__import__\(["\']([^"\']+)["\']\)',
            r'getattr\(.*,\s*["\'](\w+)["\']\)',
            r'globals\(\)\[["\'](\w+)["\']\]',
        ]

        for file_path in self.ciris_root.rglob("*.py"):
            try:
                content = file_path.read_text()
                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    if matches:
                        self.dynamic_imports.extend(
                            [{"file": str(file_path), "match": m, "pattern": pattern} for m in matches]
                        )
            except Exception:
                pass

        print(f"  ✓ Found {len(self.dynamic_imports)} dynamic imports")

    def _find_string_references(self):
        """Find string-based class references."""
        print("\n🔤 Searching for string references...")

        for class_name in self.orphaned_classes:
            # Search for the class name as a string
            for file_path in self.ciris_root.rglob("*.py"):
                try:
                    content = file_path.read_text()
                    if f'"{class_name}"' in content or f"'{class_name}'" in content:
                        # Find context
                        lines = content.split("\n")
                        for i, line in enumerate(lines):
                            if class_name in line and (f'"{class_name}"' in line or f"'{class_name}'" in line):
                                context = {
                                    "file": str(file_path.relative_to(self.project_root)),
                                    "line": i + 1,
                                    "content": line.strip(),
                                    "usage_type": self._determine_usage_type(line),
                                }
                                self.string_references[class_name].append(context)
                except Exception:
                    pass

        found_count = sum(len(refs) for refs in self.string_references.values())
        print(f"  ✓ Found {found_count} string references to orphaned classes")

    def _determine_usage_type(self, line: str) -> str:
        """Determine how a string reference is used."""
        if "register" in line.lower():
            return "registration"
        elif "config" in line.lower():
            return "configuration"
        elif "type" in line.lower() or "class" in line.lower():
            return "type_reference"
        elif "handler" in line.lower():
            return "handler_mapping"
        elif "adapter" in line.lower():
            return "adapter_reference"
        else:
            return "unknown"

    def _check_config_files(self):
        """Check YAML/JSON config files for class references."""
        print("\n📄 Checking configuration files...")

        config_patterns = ["*.yaml", "*.yml", "*.json", "*.toml"]
        config_refs = 0

        for pattern in config_patterns:
            for file_path in self.project_root.rglob(pattern):
                if "test" in str(file_path) or "cache" in str(file_path):
                    continue

                try:
                    content = file_path.read_text()
                    for class_name in self.orphaned_classes:
                        if class_name in content:
                            self.usage_patterns[class_name].append(
                                {"type": "config_file", "file": str(file_path.relative_to(self.project_root))}
                            )
                            config_refs += 1
                except Exception:
                    pass

        print(f"  ✓ Found {config_refs} config file references")

    def _check_entry_points(self):
        """Check main entry points and runtime initialization."""
        print("\n🚀 Checking entry points...")

        entry_files = [
            "main.py",
            "ciris_engine/runtime/runtime.py",
            "ciris_engine/runtime/service_initializer.py",
            "ciris_engine/runtime/adapter_manager.py",
        ]

        for entry_file in entry_files:
            file_path = self.project_root / entry_file
            if file_path.exists():
                self._trace_imports(file_path)

    def _trace_imports(self, file_path: Path, depth: int = 0, visited: Set[str] = None):
        """Recursively trace imports from a file."""
        if visited is None:
            visited = set()

        if str(file_path) in visited or depth > 3:
            return

        visited.add(str(file_path))

        try:
            tree = ast.parse(file_path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name
                        # Check if any orphaned class might be in this module
                        for class_name in self.orphaned_classes:
                            if class_name in module_name:
                                self.usage_patterns[class_name].append(
                                    {
                                        "type": "import_chain",
                                        "file": str(file_path.relative_to(self.project_root)),
                                        "depth": depth,
                                    }
                                )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    # Similar check for from imports
                    for name in node.names:
                        if isinstance(name, ast.alias) and name.name in self.orphaned_classes:
                            self.usage_patterns[class_name].append(
                                {
                                    "type": "direct_import",
                                    "file": str(file_path.relative_to(self.project_root)),
                                    "depth": depth,
                                }
                            )
        except Exception:
            pass

    def _categorize_orphans(self):
        """Categorize orphans by their characteristics."""
        self.orphan_categories = {
            "test_related": [],
            "old_versions": [],
            "examples": [],
            "actually_used": [],
            "config_driven": [],
            "truly_orphaned": [],
        }

        for class_name in self.orphaned_classes:
            class_info = self.audit_data["all_classes"].get(class_name, {})
            file_path = class_info.get("file", "")

            # Categorization logic
            if "test" in file_path.lower() or "mock" in class_name.lower():
                self.orphan_categories["test_related"].append(class_name)
            elif any(v in class_name.lower() for v in ["v1", "v2", "old", "legacy", "deprecated"]):
                self.orphan_categories["old_versions"].append(class_name)
            elif "example" in file_path.lower() or "sample" in file_path.lower():
                self.orphan_categories["examples"].append(class_name)
            elif class_name in self.string_references or class_name in self.usage_patterns:
                self.orphan_categories["actually_used"].append(class_name)
            elif any(ref.get("type") == "configuration" for ref in self.string_references.get(class_name, [])):
                self.orphan_categories["config_driven"].append(class_name)
            else:
                self.orphan_categories["truly_orphaned"].append(class_name)

    def _generate_report(self):
        """Generate detailed orphan analysis report."""
        print("\n" + "=" * 60)
        print("📊 Orphan Analysis Report")
        print("=" * 60)

        # Summary
        print("\n📈 Summary:")
        print(f"   Total Orphaned Classes: {len(self.orphaned_classes)}")
        print(f"   Actually Used (hidden): {len(self.orphan_categories['actually_used'])}")
        print(f"   Test Related: {len(self.orphan_categories['test_related'])}")
        print(f"   Old Versions: {len(self.orphan_categories['old_versions'])}")
        print(f"   Config Driven: {len(self.orphan_categories['config_driven'])}")
        print(f"   Truly Orphaned: {len(self.orphan_categories['truly_orphaned'])}")

        # Actually used details
        if self.orphan_categories["actually_used"]:
            print(f"\n✅ Actually Used Classes ({len(self.orphan_categories['actually_used'])}):")
            for class_name in self.orphan_categories["actually_used"][:10]:
                print(f"\n   • {class_name}")
                if class_name in self.string_references:
                    for ref in self.string_references[class_name][:3]:
                        print(f"     - {ref['file']}:{ref['line']} ({ref['usage_type']})")
                if class_name in self.usage_patterns:
                    for usage in self.usage_patterns[class_name][:3]:
                        print(f"     - {usage['type']}: {usage['file']}")

        # Recommendations
        print("\n🎯 Recommendations:")
        print(f"\n1. **Keep These** ({len(self.orphan_categories['actually_used'])}):")
        print("   These classes are used via dynamic imports or configuration")

        print(f"\n2. **Safe to Delete** ({len(self.orphan_categories['test_related'])}):")
        print("   Test-related classes not needed in production")

        print(f"\n3. **Archive These** ({len(self.orphan_categories['old_versions'])}):")
        print("   Old versions that might have historical value")

        print(f"\n4. **Review Carefully** ({len(self.orphan_categories['truly_orphaned'])}):")
        print("   No usage found - verify before deletion")

        # Save detailed results
        import json

        results = {
            "summary": {
                "total_orphans": len(self.orphaned_classes),
                "actually_used": len(self.orphan_categories["actually_used"]),
                "test_related": len(self.orphan_categories["test_related"]),
                "old_versions": len(self.orphan_categories["old_versions"]),
                "truly_orphaned": len(self.orphan_categories["truly_orphaned"]),
            },
            "categories": self.orphan_categories,
            "string_references": {k: v for k, v in self.string_references.items()},
            "usage_patterns": {k: v for k, v in self.usage_patterns.items()},
            "dynamic_imports": self.dynamic_imports,
        }

        with open("orphan_analysis_results.json", "w") as f:
            json.dump(results, f, indent=2)
        print("\n💾 Detailed results saved to orphan_analysis_results.json")


if __name__ == "__main__":
    analyzer = OrphanAnalyzer()
    analyzer.analyze()
