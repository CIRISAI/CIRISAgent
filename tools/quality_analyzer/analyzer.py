#!/usr/bin/env python3
"""Quality Analyzer - Unified analysis using existing CIRIS tools.

This tool orchestrates:
1. ciris_mypy_toolkit - For type safety and Dict[str, Any] analysis
2. sonar_tool - For code quality metrics and coverage
3. Combines results into a unified improvement plan
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

# Import our tools
sys.path.insert(0, str(Path(__file__).parent.parent))
from analysis.sonar_tool.analyzer import CoverageAnalyzer
from analysis.sonar_tool.client import SonarClient
from ciris_mypy_toolkit.core import CIRISMypyToolkit
from ciris_mypy_toolkit.schema_compliance import SchemaComplianceChecker


@dataclass
class UnifiedIssue:
    """A file with combined quality metrics."""

    path: str
    dict_any_count: int = 0
    mypy_errors: int = 0
    cognitive_complexity: int = 0
    tech_debt_hours: float = 0
    coverage_percent: float = 100
    uncovered_lines: int = 0
    code_smells: int = 0
    priority_score: float = 0

    def calculate_priority(self):
        """Calculate priority based on all factors."""
        # Higher score = higher priority
        type_safety_factor = min(self.dict_any_count * 10, 100)
        mypy_factor = min(self.mypy_errors * 5, 50)
        complexity_factor = min(self.cognitive_complexity / 15 * 100, 100) if self.cognitive_complexity > 15 else 0
        coverage_factor = 100 - self.coverage_percent
        debt_factor = min(self.tech_debt_hours * 10, 100)

        self.priority_score = (
            type_safety_factor * 0.25
            + mypy_factor * 0.15
            + complexity_factor * 0.25
            + coverage_factor * 0.20
            + debt_factor * 0.15
        )


class UnifiedAnalyzer:
    """Orchestrates multiple analysis tools."""

    def __init__(self):
        # Initialize tools
        self.mypy_toolkit = CIRISMypyToolkit("ciris_engine", "ciris_engine/schemas")
        self.schema_checker = SchemaComplianceChecker()

        # Load SonarCloud token
        token_file = Path.home() / ".sonartoken"
        if token_file.exists():
            self.sonar_token = token_file.read_text().strip()
            self.sonar_client = SonarClient(self.sonar_token)
            self.coverage_analyzer = CoverageAnalyzer(self.sonar_client)
        else:
            self.sonar_token = None
            self.sonar_client = None
            self.coverage_analyzer = None

    def analyze_type_safety(self) -> Dict[str, UnifiedIssue]:
        """Get type safety issues from mypy toolkit."""
        issues = {}

        # Get MyPy errors
        mypy_errors = self.mypy_toolkit.get_mypy_errors()
        for error in mypy_errors:
            path = error.get("file", "")
            if path not in issues:
                issues[path] = UnifiedIssue(path=path)
            issues[path].mypy_errors += 1

        # Get Dict[str, Any] usage from schema compliance
        target_dir = Path("ciris_engine")
        for py_file in target_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            result = self.schema_checker.check_schema_usage(str(py_file))
            if result["violations"]:
                path = str(py_file)
                if path not in issues:
                    issues[path] = UnifiedIssue(path=path)

                # Count Dict[str, Any] occurrences
                for violation in result["violations"]:
                    if "Dict[str, Any]" in violation["issue"]:
                        issues[path].dict_any_count += 1

        return issues

    def analyze_code_quality(self, issues: Dict[str, UnifiedIssue]) -> Dict[str, UnifiedIssue]:
        """Add SonarCloud metrics to issues."""
        if not self.sonar_client:
            print("⚠️  SonarCloud token not found. Skipping quality metrics.")
            return issues

        try:
            # Get tech debt files
            tech_debt_files = self.sonar_client.get_tech_debt_files(limit=100)
            for file_data in tech_debt_files:
                path = file_data["path"]
                if path not in issues:
                    issues[path] = UnifiedIssue(path=path)
                issues[path].tech_debt_hours = file_data["tech_debt_minutes"] / 60
                issues[path].code_smells = file_data["code_smells"]
                issues[path].cognitive_complexity = file_data["cognitive_complexity"]

            # Get coverage data
            uncovered_files = self.sonar_client.get_uncovered_files(limit=200)
            for file_data in uncovered_files:
                path = file_data["path"]
                if path not in issues:
                    issues[path] = UnifiedIssue(path=path)
                issues[path].coverage_percent = file_data["coverage"]
                issues[path].uncovered_lines = file_data["uncovered_lines"]

        except Exception as e:
            print(f"⚠️  Error getting SonarCloud data: {e}")

        return issues

    def generate_report(self, issues: Dict[str, UnifiedIssue]):
        """Generate unified improvement report."""
        # Calculate priorities
        for issue in issues.values():
            issue.calculate_priority()

        # Sort by priority
        sorted_issues = sorted(issues.values(), key=lambda x: x.priority_score, reverse=True)

        print("=" * 80)
        print("UNIFIED CIRIS QUALITY ANALYSIS")
        print("Using: ciris_mypy_toolkit + sonar_tool")
        print("=" * 80)
        print()

        # Top priority files
        print("🎯 TOP 15 PRIORITY FILES:")
        print()

        for i, issue in enumerate(sorted_issues[:15], 1):
            print(f"{i}. {issue.path}")
            print(f"   Priority Score: {issue.priority_score:.1f}/100")

            problems = []
            if issue.dict_any_count > 0:
                problems.append(f"Dict[str,Any]: {issue.dict_any_count}")
            if issue.mypy_errors > 0:
                problems.append(f"MyPy errors: {issue.mypy_errors}")
            if issue.cognitive_complexity > 15:
                problems.append(f"Complexity: {issue.cognitive_complexity}")
            if issue.coverage_percent < 50:
                problems.append(f"Coverage: {issue.coverage_percent:.1f}%")
            if issue.tech_debt_hours > 1:
                problems.append(f"Debt: {issue.tech_debt_hours:.1f}h")

            if problems:
                print(f"   Issues: {' | '.join(problems)}")

            # Estimate effort with AI
            type_time = (issue.dict_any_count * 0.5 + issue.mypy_errors * 0.3) / 15
            test_time = issue.uncovered_lines / 300  # AI-accelerated
            refactor_time = issue.tech_debt_hours / 15  # AI-accelerated
            total_time = type_time + test_time + refactor_time

            if total_time > 0.1:
                print(f"   AI Time: ~{total_time:.1f} hours")
            print()

        # Statistics by category
        print("=" * 80)
        print("📊 ISSUE BREAKDOWN:")
        print()

        # Type safety issues
        type_safety_files = [i for i in sorted_issues if i.dict_any_count > 0 or i.mypy_errors > 0]
        print(f"Type Safety Issues: {len(type_safety_files)} files")
        if type_safety_files:
            total_dict_any = sum(i.dict_any_count for i in type_safety_files)
            total_mypy = sum(i.mypy_errors for i in type_safety_files)
            print(f"  - Dict[str, Any]: {total_dict_any} occurrences")
            print(f"  - MyPy errors: {total_mypy} errors")
        print()

        # Coverage issues
        low_coverage = [i for i in sorted_issues if i.coverage_percent < 50]
        print(f"Low Coverage: {len(low_coverage)} files < 50%")
        if low_coverage:
            total_uncovered = sum(i.uncovered_lines for i in low_coverage)
            print(f"  - Total uncovered lines: {total_uncovered:,}")
        print()

        # Complexity issues
        high_complexity = [i for i in sorted_issues if i.cognitive_complexity > 15]
        print(f"High Complexity: {len(high_complexity)} files")
        if high_complexity:
            total_debt = sum(i.tech_debt_hours for i in high_complexity)
            print(f"  - Total tech debt: {total_debt:.1f} hours")
        print()

        # Quick wins
        print("=" * 80)
        print("⚡ QUICK WINS:")
        print()

        # Type safety quick wins (few Dict[str, Any], no other issues)
        type_quick_wins = [
            i
            for i in sorted_issues
            if i.dict_any_count > 0
            and i.dict_any_count <= 3
            and i.cognitive_complexity <= 15
            and i.coverage_percent > 50
        ]
        if type_quick_wins:
            print("1. Easy Type Safety Fixes:")
            for issue in type_quick_wins[:5]:
                print(f"   - {issue.path} ({issue.dict_any_count} Dict[str,Any])")
            print()

        # Coverage quick wins (small files with no coverage)
        coverage_quick_wins = [
            i
            for i in sorted_issues
            if i.coverage_percent == 0 and i.uncovered_lines < 100 and i.cognitive_complexity <= 15
        ]
        if coverage_quick_wins:
            print("2. Small Files Needing Tests:")
            for issue in coverage_quick_wins[:5]:
                print(f"   - {issue.path} ({issue.uncovered_lines} lines)")
            print()

        # Total effort
        print("=" * 80)
        print("💪 TOTAL EFFORT ESTIMATE:")
        print()

        all_issues = list(issues.values())
        total_dict_any = sum(i.dict_any_count for i in all_issues)
        total_mypy = sum(i.mypy_errors for i in all_issues)
        total_uncovered = sum(i.uncovered_lines for i in all_issues)
        total_debt = sum(i.tech_debt_hours for i in all_issues)

        type_work = (total_dict_any * 0.5 + total_mypy * 0.3) / 15
        test_work = total_uncovered / 300
        refactor_work = total_debt / 15
        total_work = type_work + test_work + refactor_work

        print("With AI assistance (÷15):")
        print(f"  - Type safety: ~{type_work:.1f} hours")
        print(f"  - Test coverage: ~{test_work:.1f} hours")
        print(f"  - Refactoring: ~{refactor_work:.1f} hours")
        print(f"  - TOTAL: ~{total_work:.1f} hours")
        print()
        print("🚀 Start with the top 5 files for maximum impact!")


def generate_unified_plan():
    """Main entry point for unified analysis."""
    analyzer = UnifiedAnalyzer()

    print("🔍 Analyzing type safety with ciris_mypy_toolkit...")
    issues = analyzer.analyze_type_safety()

    print("📊 Analyzing code quality with sonar_tool...")
    issues = analyzer.analyze_code_quality(issues)

    print("📝 Generating unified report...\n")
    analyzer.generate_report(issues)


if __name__ == "__main__":
    generate_unified_plan()
