"""Command handling for the sonar tool."""

import sys

from .analyzer import CoverageAnalyzer
from .client import SonarClient
from .reporter import QualityReporter


class CommandHandler:
    """Handle sonar tool commands."""

    def __init__(self, token: str):
        self.client = SonarClient(token)
        self.analyzer = CoverageAnalyzer(self.client)
        self.reporter = QualityReporter()

    def analyze_coverage(self, export_json: bool = False) -> None:
        """Run comprehensive coverage analysis."""
        print("Analyzing coverage opportunities...")

        try:
            analysis = self.analyzer.analyze_coverage_opportunities()

            # Generate reports
            coverage_report = self.reporter.generate_coverage_report(analysis)
            print(coverage_report)

            # Also print action summary
            print("\n" + "=" * 80 + "\n")
            action_summary = self.reporter.generate_action_summary(analysis)
            print(action_summary)

            if export_json:
                self.reporter.export_json_report(analysis)

        except Exception as e:
            print(f"Error during analysis: {e}")
            sys.exit(1)

    def analyze_tech_debt(self) -> None:
        """Analyze technical debt."""
        print("Analyzing technical debt...")

        try:
            # Get issues and debt files
            issues = self.client.search_issues(limit=100)
            debt_files = self.client.get_tech_debt_files(limit=30)

            # Generate report
            report = self.reporter.generate_tech_debt_report(issues, debt_files)
            print(report)

        except Exception as e:
            print(f"Error during analysis: {e}")
            sys.exit(1)

    def quick_status(self) -> None:
        """Show quick quality status."""
        try:
            # Get metrics
            metrics = self.client.get_coverage_metrics()
            qg_status = self.client.get_quality_gate_status()

            print("CIRIS Quality Status")
            print("=" * 40)
            print(f"Coverage: {metrics.get('coverage', 0)}% (Target: 80%)")
            print(f"Quality Gate: {qg_status['status']}")

            # Show failing conditions
            failing = [c for c in qg_status.get("conditions", []) if c["status"] != "OK"]

            if failing:
                print("\nFailing conditions:")
                for cond in failing:
                    print(
                        f"  - {cond['metricKey']}: {cond['actualValue']} "
                        f"(needs {cond['comparator']} {cond['errorThreshold']})"
                    )

        except Exception as e:
            print(f"Error getting status: {e}")
            sys.exit(1)

    def list_hotspots(self, status: str = "TO_REVIEW") -> None:
        """List security hotspots."""
        try:
            hotspots = self.client.get_hotspots(status=status)

            if not hotspots:
                print(f"No hotspots with status {status}")
                return

            print(f"\nSecurity Hotspots ({status}):")
            print("=" * 60)

            for hs in hotspots:
                print(f"\n[{hs['vulnerabilityProbability']}] {hs['key']}")
                print(f"  File: {hs['component']}:{hs.get('line', '?')}")
                print(f"  Message: {hs['message']}")

        except Exception as e:
            print(f"Error listing hotspots: {e}")
            sys.exit(1)

    def find_file_coverage(self, path_pattern: str) -> None:
        """Find coverage for specific files."""
        try:
            files = self.client.get_uncovered_files(limit=200)

            matching = [f for f in files if path_pattern.lower() in f["path"].lower()]

            if not matching:
                print(f"No files found matching '{path_pattern}'")
                return

            print(f"\nFiles matching '{path_pattern}':")
            print("=" * 60)

            for file in sorted(matching, key=lambda x: x["coverage"]):
                print(f"{file['coverage']:5.1f}% - {file['path']} " f"({file['uncovered_lines']} uncovered lines)")

        except Exception as e:
            print(f"Error finding files: {e}")
            sys.exit(1)
