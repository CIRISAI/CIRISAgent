"""Quality reporting with actionable insights."""

import json
from datetime import datetime
from typing import Any, Dict, List


class QualityReporter:
    """Generate actionable quality reports."""

    def __init__(self):
        self.report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def generate_coverage_report(self, analysis: Dict[str, Any]) -> str:
        """Generate comprehensive coverage improvement report."""
        lines = [
            "=" * 80,
            "CIRIS Code Coverage Analysis Report",
            f"Generated: {self.report_time}",
            "=" * 80,
            "",
            "## Current Status",
            f"- Coverage: {analysis['current_coverage']:.1f}% (Target: 80.0%)",
            f"- Gap: {analysis['coverage_gap']:.1f}%",
            f"- Uncovered Lines: {analysis['uncovered_lines']:,} / {analysis['lines_to_cover']:,}",
            f"- Estimated files to review: {analysis['estimated_files_to_80_percent']}",
            "",
        ]

        # Quick wins section
        if analysis["quick_wins"]:
            lines.extend(
                [
                    "## Quick Wins (Low effort, good impact)",
                    "These files have low coverage but are small and simple to test:",
                    "⚡ Time estimates: Pre-AI hours → AI-accelerated hours (÷15)",
                    "",
                ]
            )

            for i, win in enumerate(analysis["quick_wins"][:5], 1):
                lines.append(
                    f"{i}. {win['path']}"
                    f"\n   Coverage: {win['coverage']:.1f}% | "
                    f"Lines: {win['uncovered_lines']} | "
                    f"Time: {win['estimated_hours']:.1f}h → {win['ai_hours']:.1f}h with AI"
                )
            lines.append("")

        # Strategic targets
        if analysis["strategic_targets"]:
            lines.extend(
                [
                    "## Strategic Targets (Best ROI)",
                    "Files with highest impact relative to effort:",
                    "🚀 ROI scores adjusted for AI-accelerated development (×15)",
                    "",
                ]
            )

            for i, target in enumerate(analysis["strategic_targets"][:10], 1):
                lines.append(
                    f"{i}. {target['path']}"
                    f"\n   Coverage: {target['current_coverage']:.1f}% | "
                    f"Uncovered: {target['uncovered_lines']} lines | "
                    f"AI Time: {target['ai_effort_hours']:.1f}h | "
                    f"ROI: {target['roi_score']:.1f}"
                )
            lines.append("")

        # Package analysis
        if analysis["package_analysis"]:
            lines.extend(["## Package Analysis", "Modules with most uncovered code:", ""])

            for package, stats in list(analysis["package_analysis"].items())[:5]:
                lines.append(
                    f"- {package}"
                    f"\n  Files: {stats['files']} | "
                    f"Avg Coverage: {stats['avg_coverage']:.1f}% | "
                    f"Uncovered: {stats['total_uncovered_lines']:,} lines"
                )
            lines.append("")

        # Action plan
        lines.extend(
            [
                "## Recommended Action Plan",
                "",
                "1. **Immediate** (This week):",
                "   - Focus on quick wins listed above",
                "   - Each can be completed in < 4 hours",
                "",
                "2. **Short-term** (Next 2 weeks):",
                "   - Work through strategic targets",
                "   - Focus on files with ROI score > 1.0",
                "",
                "3. **Strategic** (This month):",
                "   - Address low-coverage packages systematically",
                "   - Consider adding integration tests for complex flows",
                "",
                "=" * 80,
            ]
        )

        return "\n".join(lines)

    def generate_tech_debt_report(self, issues: List[Dict], debt_files: List[Dict]) -> str:
        """Generate technical debt report."""
        lines = ["=" * 80, "CIRIS Technical Debt Report", f"Generated: {self.report_time}", "=" * 80, ""]

        # Issue summary
        severity_counts = {}
        type_counts = {}

        for issue in issues:
            sev = issue.get("severity", "UNKNOWN")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

            rule = issue.get("rule", "").split(":")[-1]
            type_counts[rule] = type_counts.get(rule, 0) + 1

        lines.extend(["## Issue Summary", f"Total Issues: {len(issues)}", "", "By Severity:"])

        for sev in ["CRITICAL", "MAJOR", "MINOR", "INFO"]:
            if sev in severity_counts:
                lines.append(f"  - {sev}: {severity_counts[sev]}")

        lines.extend(["", "Top Issue Types:"])

        for rule, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            lines.append(f"  - {rule}: {count} occurrences")

        # High debt files
        if debt_files:
            lines.extend(["", "## Files with Highest Technical Debt", ""])

            for i, file in enumerate(debt_files[:10], 1):
                debt_hours = file["tech_debt_minutes"] / 60
                lines.append(
                    f"{i}. {file['path']}"
                    f"\n   Debt: {debt_hours:.1f} hours | "
                    f"Code Smells: {file['code_smells']} | "
                    f"Complexity: {file['cognitive_complexity']}"
                )

        lines.extend(["", "=" * 80])
        return "\n".join(lines)

    def generate_action_summary(self, analysis: Dict[str, Any]) -> str:
        """Generate a concise action summary for immediate use."""
        lines = ["CIRIS Quality Action Summary", "=" * 40, "", "🎯 TOP 5 FILES TO TEST NOW:", ""]

        # Top 5 strategic targets
        for i, target in enumerate(analysis["strategic_targets"][:5], 1):
            lines.append(
                f"{i}. {target['path']} "
                f"({target['uncovered_lines']} lines, "
                f"~{target['ai_effort_hours']:.1f}h with AI)"
            )

        lines.extend(
            [
                "",
                "📊 If you test these 5 files:",
                f"   - Coverage gain: ~{sum(t['coverage_gain'] for t in analysis['strategic_targets'][:5]):.1f}%",
                f"   - Total AI time: ~{sum(t['ai_effort_hours'] for t in analysis['strategic_targets'][:5]):.1f} hours",
                f"   - (Pre-AI estimate: {sum(t['estimated_effort_hours'] for t in analysis['strategic_targets'][:5]):.0f} hours)",
                "",
                "💡 With AI assistance, you can tackle all 5 in a single day!",
                "",
            ]
        )

        return "\n".join(lines)

    def export_json_report(self, analysis: Dict[str, Any], filename: str = "sonar_analysis.json") -> None:
        """Export analysis as JSON for further processing."""
        with open(filename, "w") as f:
            json.dump(analysis, f, indent=2, default=str)
        print(f"Analysis exported to {filename}")
