"""
Core CIRIS MyPy Toolkit - Main orchestrator for type safety and compliance
"""

import logging
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import all required modules - exit if any are broken (no fallbacks)
from .analyzers import ProtocolAnalyzer, SchemaValidator, UnusedCodeDetector
from .error_fixers import ProtocolComplianceFixer, SchemaAlignmentFixer, TypeAnnotationFixer

# Import our updated schema compliance checker and security analyzer

logger = logging.getLogger(__name__)


class CIRISMypyToolkit:
    """
    Main toolkit orchestrator for ensuring CIRIS schema and protocol compliance.

    This toolkit helps developers and agents building CIRIS adapters/modules
    ensure they follow proper schemas, protocols, and type safety.
    """

    def __init__(self, target_dir: str = "ciris_engine", schemas_dir: str = "ciris_engine/schemas"):
        self.target_dir = Path(target_dir)
        self.schemas_dir = Path(schemas_dir)

        # Initialize analyzers
        self.schema_validator = SchemaValidator(self.schemas_dir)
        self.protocol_analyzer = ProtocolAnalyzer(self.target_dir)
        self.unused_code_detector = UnusedCodeDetector(self.target_dir)

        # Initialize error fixers
        self.type_fixer = TypeAnnotationFixer(self.target_dir)
        self.protocol_fixer = ProtocolComplianceFixer(self.target_dir, self.schemas_dir)
        self.schema_fixer = SchemaAlignmentFixer(self.target_dir, self.schemas_dir)

        self.fixes_applied = 0

    def get_mypy_errors(self) -> List[Dict[str, Any]]:
        """Run mypy and parse errors with 100% accuracy."""
        cmd = f"python -m mypy {self.target_dir} --ignore-missing-imports --show-error-codes --no-error-summary"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        errors = []
        # MyPy sends output to stderr, but let's check both streams
        full_output = result.stderr + result.stdout

        # Parse multi-line mypy output
        lines = full_output.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i]

            # Look for error lines: file:line: error: message or file:line:col: error: message
            match = re.search(r"^([^:]+):(\d+)(?::(\d+))?\s*:\s*error:\s*(.+)", line)
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                col_num = int(match.group(3)) if match.group(3) else 0
                message = match.group(4).strip()

                # Look ahead for error code on next line
                error_code = "unknown"
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    # Error code is on line that starts with space and contains [code]
                    if next_line.strip().startswith("[") and next_line.strip().endswith("]"):
                        error_code = next_line.strip()[1:-1]  # Remove [ and ]
                        i += 1  # Skip the code line
                    elif "[" in next_line and "]" in next_line:
                        code_match = re.search(r"\[([^\]]+)\]", next_line)
                        if code_match:
                            error_code = code_match.group(1)
                            i += 1  # Skip the code line

                errors.append(
                    {"file": file_path, "line": line_num, "col": col_num, "message": message, "code": error_code}
                )

            i += 1

        logger.debug(f"Parsed {len(errors)} mypy errors from output")
        return errors

    def analyze_compliance(self) -> Dict[str, Any]:
        """
        Comprehensive compliance analysis for CIRIS codebase.

        Returns:
            Analysis report with schema, protocol, and type safety issues
        """
        logger.info(" Starting CIRIS compliance analysis...")

        # Get mypy errors
        mypy_errors = self.get_mypy_errors()

        # Analyze schema compliance
        schema_issues = self.schema_validator.validate_all_files()

        # Analyze protocol usage
        protocol_results = self.protocol_analyzer.check_all_services()
        protocol_issues = protocol_results.get("issues", [])

        # Detect unused/uncalled code
        unused_code = self.unused_code_detector.find_unused_code()

        # Categorize mypy errors
        error_categories = self._categorize_errors(mypy_errors)

        report = {
            "total_mypy_errors": len(mypy_errors),
            "error_categories": error_categories,
            "schema_compliance": {"total_issues": len(schema_issues), "issues": schema_issues},
            "protocol_compliance": {
                "total_issues": len(protocol_issues),
                "issues": protocol_issues,
                "summary": {
                    "total_services": protocol_results.get("total_services", 0),
                    "aligned_services": protocol_results.get("aligned_services", 0),
                    "misaligned_services": protocol_results.get("misaligned_services", 0),
                },
            },
            "unused_code": {"total_items": len(unused_code), "items": unused_code},
            "recommendations": self._generate_recommendations(mypy_errors, schema_issues, protocol_issues, unused_code),
        }

        return report

    def propose_fixes(self, categories: Optional[List[str]] = None, output_file: str = "proposed_fixes.json") -> str:
        """
        Analyze issues and propose fixes without making changes.

        Args:
            categories: Specific categories to analyze
            output_file: File to write proposed changes to

        Returns:
            Path to the proposal file
        """
        logger.info(" Analyzing issues and proposing fixes...")

        # Default categories in order of safety/impact
        if categories is None:
            categories = ["type_annotations", "schema_alignment", "protocol_compliance", "unused_code_removal"]

        initial_errors = self.get_mypy_errors()

        proposal = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "initial_mypy_errors": len(initial_errors),
                "categories_analyzed": categories,
                "validation_required": True,
                "mode": "aggressive_pre_beta",
                "target": "100_percent_cleanliness",
            },
            "current_errors": [
                {
                    "file": error["file"],
                    "line": error["line"],
                    "message": error["message"],
                    "code": error.get("code", "unknown"),
                }
                for error in initial_errors[:50]  # Show more errors for aggressive mode
            ],
            "error_summary": self._categorize_errors(initial_errors),
            "proposed_changes": {},
        }

        for category in categories:
            logger.info(f" Analyzing {category} issues...")

            if category == "type_annotations":
                changes = self.type_fixer.propose_type_fixes()
                proposal["proposed_changes"]["type_annotations"] = changes

            elif category == "schema_alignment":
                changes = self.schema_fixer.propose_schema_fixes()
                proposal["proposed_changes"]["schema_alignment"] = changes

            elif category == "protocol_compliance":
                changes = self.protocol_fixer.propose_protocol_fixes()
                proposal["proposed_changes"]["protocol_compliance"] = changes

            elif category == "unused_code_removal":
                changes = self.unused_code_detector.propose_cleanup()
                proposal["proposed_changes"]["unused_code_removal"] = changes

        # Write proposal to file
        import json

        with open(output_file, "w") as f:
            json.dump(proposal, f, indent=2)

        logger.info(f" Proposed changes written to {output_file}")
        logger.info("[WARN] REVIEW THE PROPOSED CHANGES BEFORE APPLYING!")
        logger.info(f" To apply: python -m ciris_mypy_toolkit.cli execute {output_file}")

        return output_file

    def execute_approved_fixes(self, proposal_file: str) -> Dict[str, int]:
        """
        Execute fixes from an approved proposal file.

        Args:
            proposal_file: Path to the approved proposal JSON file

        Returns:
            Dictionary of fixes applied per category
        """
        logger.info(f" Executing approved fixes from {proposal_file}")

        import json

        with open(proposal_file, "r") as f:
            proposal = json.load(f)

        if not proposal["metadata"]["validation_required"]:
            logger.warning("[WARN] This proposal was not marked for validation!")

        fixes_summary = {}
        initial_errors = len(self.get_mypy_errors())

        for category, changes in proposal["proposed_changes"].items():
            if not changes:  # Skip empty change sets
                continue

            logger.info(f" Applying {category} fixes...")

            if category == "type_annotations":
                fixes = self.type_fixer.apply_approved_fixes(changes)
                fixes_summary["type_annotations"] = fixes

            elif category == "schema_alignment":
                fixes = self.schema_fixer.apply_approved_fixes(changes)
                fixes_summary["schema_alignment"] = fixes

            elif category == "protocol_compliance":
                fixes = self.protocol_fixer.apply_approved_fixes(changes)
                fixes_summary["protocol_compliance"] = fixes

            elif category == "unused_code_removal":
                fixes = self.unused_code_detector.apply_approved_cleanup(changes)
                fixes_summary["unused_code_removal"] = fixes

        final_errors = len(self.get_mypy_errors())
        fixes_summary["total_errors_eliminated"] = initial_errors - final_errors

        logger.info(f"[OK] Applied fixes. Errors: {initial_errors} → {final_errors}")

        return fixes_summary

    def validate_adapter_compliance(self, adapter_path: str) -> Dict[str, Any]:
        """
        Validate a specific adapter for CIRIS compliance.

        Args:
            adapter_path: Path to the adapter module

        Returns:
            Compliance report for the adapter
        """
        adapter_path = Path(adapter_path)

        if not adapter_path.exists():  # type: ignore[attr-defined]
            return {"error": f"Adapter path {adapter_path} does not exist"}

        # Validate adapter follows CIRIS patterns
        validation_results = {
            "schema_usage": self.schema_validator.validate_file(adapter_path),
            "protocol_implementation": self.protocol_analyzer.validate_adapter(adapter_path),
            "type_safety": self._check_adapter_types(adapter_path),
            "compliance_score": 0.0,
        }

        # Calculate compliance score
        total_checks = 0
        passed_checks = 0

        for category, results in validation_results.items():
            if isinstance(results, dict) and "passed" in results:
                total_checks += results.get("total", 0)
                passed_checks += results.get("passed", 0)

        if total_checks > 0:
            validation_results["compliance_score"] = passed_checks / total_checks

        return validation_results

    def _categorize_errors(self, errors: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Categorize mypy errors for systematic fixing."""
        categories = defaultdict(list)

        for error in errors:
            message = error["message"]

            if "Function is missing" in message:
                categories["missing_type_annotations"].append(error)
            elif "has no attribute" in message:
                categories["attribute_access_errors"].append(error)
            elif "Incompatible types" in message:
                categories["type_mismatches"].append(error)
            elif "Returning Any" in message:
                categories["return_type_issues"].append(error)
            elif "Statement is unreachable" in message:
                categories["unreachable_code"].append(error)
            elif "union-attr" in error.get("code", ""):
                categories["union_attribute_access"].append(error)
            else:
                categories["other"].append(error)

        return dict(categories)

    def _generate_recommendations(self, mypy_errors, schema_issues, protocol_issues, unused_code) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        if len(mypy_errors) > 50:
            recommendations.append("High number of type errors detected. Consider running systematic fixing.")

        if len(schema_issues) > 0:
            recommendations.append("Schema compliance issues found. Update code to use current v1 schemas.")

        if len(protocol_issues) > 0:
            recommendations.append("Protocol violations detected. Refactor to use protocol interfaces only.")

        if len(unused_code) > 10:
            recommendations.append("Significant unused code detected. Consider cleanup to improve maintainability.")

        return recommendations

    def _check_adapter_types(self, adapter_path: Path) -> Dict[str, Any]:
        """Check type safety of an adapter."""
        # Run mypy specifically on this adapter
        cmd = f"python -m mypy {adapter_path} --ignore-missing-imports --show-error-codes"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        errors = []
        for line in result.stderr.splitlines():
            if "error:" in line:
                errors.append(line.strip())

        return {"total_errors": len(errors), "errors": errors, "type_safe": len(errors) == 0}

    def generate_compliance_report(self, output_file: Optional[str] = None) -> str:
        """Generate a comprehensive compliance report."""
        analysis = self.analyze_compliance()

        report_lines = [
            "# CIRIS Codebase Compliance Report",
            "=" * 50,
            "",
            "## MyPy Type Safety",
            f"Total Errors: {analysis['total_mypy_errors']}",
            "",
        ]

        # Add error category breakdown
        for category, errors in analysis["error_categories"].items():
            report_lines.append(f"- {category}: {len(errors)} errors")

        report_lines.extend(
            [
                "",
                "## Schema Compliance",
                f"Issues Found: {analysis['schema_compliance']['total_issues']}",
                "",
                "## Protocol Compliance",
                f"Issues Found: {analysis['protocol_compliance']['total_issues']}",
                "",
                "## Code Quality",
                f"Unused Code Items: {analysis['unused_code']['total_items']}",
                "",
                "## Recommendations",
            ]
        )

        for rec in analysis["recommendations"]:
            report_lines.append(f"- {rec}")

        report_content = "\n".join(report_lines)

        if output_file:
            with open(output_file, "w") as f:
                f.write(report_content)
            logger.info(f"Compliance report written to {output_file}")

        return report_content
