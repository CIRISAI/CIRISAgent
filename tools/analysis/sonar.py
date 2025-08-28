#!/usr/bin/env python3
"""
SonarCloud Issue Management Tool

Simple CLI for managing SonarCloud issues for the CIRIS project.
Uses token from ~/.sonartoken for authentication.

Usage:
    python tools/sonar.py list [--severity CRITICAL] [--limit 10]
    python tools/sonar.py mark-fp ISSUE_KEY [--comment "Reason"]
    python tools/sonar.py mark-wontfix ISSUE_KEY [--comment "Reason"]
    python tools/sonar.py reopen ISSUE_KEY
    python tools/sonar.py stats
    python tools/sonar.py quality-gate
    python tools/sonar.py hotspots [--status TO_REVIEW]
    python tools/sonar.py coverage [--new-code]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# Configuration
SONAR_TOKEN_FILE = Path.home() / ".sonartoken"
SONAR_API_BASE = "https://sonarcloud.io/api"
PROJECT_KEY = "CIRISAI_CIRISAgent"


class SonarClient:
    """Simple SonarCloud API client."""

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def search_issues(
        self, severity: Optional[str] = None, resolved: bool = False, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search for issues in the project."""
        params = {"componentKeys": PROJECT_KEY, "resolved": str(resolved).lower(), "ps": limit}
        if severity:
            params["severities"] = severity.upper()

        response = self.session.get(f"{SONAR_API_BASE}/issues/search", params=params)
        response.raise_for_status()
        return response.json()["issues"]

    def transition_issue(self, issue_key: str, transition: str, comment: Optional[str] = None) -> Dict[str, Any]:
        """Transition an issue (mark as false positive, won't fix, etc)."""
        data = {"issue": issue_key, "transition": transition}
        if comment:
            data["comment"] = comment

        response = self.session.post(
            f"{SONAR_API_BASE}/issues/do_transition",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()

    def add_comment(self, issue_key: str, comment: str) -> Dict[str, Any]:
        """Add a comment to an issue."""
        data = {"issue": issue_key, "text": comment}

        response = self.session.post(
            f"{SONAR_API_BASE}/issues/add_comment",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()

    def get_stats(self) -> Dict[str, Any]:
        """Get issue statistics for the project."""
        response = self.session.get(
            f"{SONAR_API_BASE}/issues/search",
            params={"componentKeys": PROJECT_KEY, "resolved": "false", "facets": "severities,types,rules", "ps": 1},
        )
        response.raise_for_status()
        data = response.json()

        stats = {"total": data["total"], "by_severity": {}, "by_type": {}, "top_rules": []}

        for facet in data["facets"]:
            if facet["property"] == "severities":
                stats["by_severity"] = {v["val"]: v["count"] for v in facet["values"]}
            elif facet["property"] == "types":
                stats["by_type"] = {v["val"]: v["count"] for v in facet["values"]}
            elif facet["property"] == "rules":
                stats["top_rules"] = [(v["val"], v["count"]) for v in facet["values"][:5]]

        return stats

    def get_quality_gate_status(self) -> Dict[str, Any]:
        """Get quality gate status for the project."""
        response = self.session.get(f"{SONAR_API_BASE}/qualitygates/project_status", params={"projectKey": PROJECT_KEY})
        response.raise_for_status()
        return response.json()["projectStatus"]

    def search_hotspots(self, status: str = "TO_REVIEW", limit: int = 100) -> Dict[str, Any]:
        """Search for security hotspots."""
        params = {"projectKey": PROJECT_KEY, "status": status, "ps": limit}

        response = self.session.get(f"{SONAR_API_BASE}/hotspots/search", params=params)
        response.raise_for_status()
        return response.json()

    def mark_hotspot_safe(self, hotspot_key: str, comment: Optional[str] = None) -> Dict[str, Any]:
        """Mark a security hotspot as safe."""
        data = {"hotspot": hotspot_key, "status": "SAFE"}
        if comment:
            data["comment"] = comment

        response = self.session.post(f"{SONAR_API_BASE}/hotspots/change_status", data=data)
        response.raise_for_status()
        return response.json()

    def get_coverage_metrics(self, new_code: bool = False) -> Dict[str, Any]:
        """Get coverage metrics for the project."""
        metrics = []
        if new_code:
            metrics = [
                "new_coverage",
                "new_lines_to_cover",
                "new_uncovered_lines",
                "new_line_coverage",
                "new_branch_coverage",
            ]
        else:
            metrics = ["coverage", "lines_to_cover", "uncovered_lines", "line_coverage", "branch_coverage"]

        response = self.session.get(
            f"{SONAR_API_BASE}/measures/component", params={"component": PROJECT_KEY, "metricKeys": ",".join(metrics)}
        )
        response.raise_for_status()
        return response.json()


def format_hotspot(hotspot: Dict[str, Any]) -> str:
    """Format a security hotspot for display."""
    file_path = hotspot["component"].split(":")[-1]
    created = datetime.fromisoformat(hotspot["creationDate"].replace("Z", "+00:00"))
    created_str = created.strftime("%Y-%m-%d")

    return (
        f"[{hotspot['vulnerabilityProbability']} RISK] {hotspot['key']} - {hotspot['securityCategory'].upper()}\n"
        f"  File: {file_path}:{hotspot.get('line', '?')}\n"
        f"  Message: {hotspot['message']}\n"
        f"  Status: {hotspot['status']}\n"
        f"  Created: {created_str}\n"
    )


def format_issue(issue: Dict[str, Any]) -> str:
    """Format an issue for display."""
    file_path = issue["component"].split(":")[-1]
    created = datetime.fromisoformat(issue["creationDate"].replace("Z", "+00:00"))
    created_str = created.strftime("%Y-%m-%d")

    return (
        f"[{issue['severity']}] {issue['key']} - {issue['rule']}\n"
        f"  File: {file_path}:{issue.get('line', '?')}\n"
        f"  Message: {issue['message']}\n"
        f"  Created: {created_str}\n"
    )


def main():
    parser = argparse.ArgumentParser(description="SonarCloud Issue Management Tool")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List issues")
    list_parser.add_argument(
        "--severity", choices=["BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"], help="Filter by severity"
    )
    list_parser.add_argument("--limit", type=int, default=20, help="Number of issues to show")
    list_parser.add_argument("--resolved", action="store_true", help="Show resolved issues")

    # Mark false positive
    fp_parser = subparsers.add_parser("mark-fp", help="Mark issue as false positive")
    fp_parser.add_argument("issue_key", help="Issue key to mark")
    fp_parser.add_argument("--comment", help="Comment explaining why it's a false positive")

    # Mark won't fix
    wf_parser = subparsers.add_parser("mark-wontfix", help="Mark issue as won't fix")
    wf_parser.add_argument("issue_key", help="Issue key to mark")
    wf_parser.add_argument("--comment", help="Comment explaining why it won't be fixed")

    # Reopen
    reopen_parser = subparsers.add_parser("reopen", help="Reopen a resolved issue")
    reopen_parser.add_argument("issue_key", help="Issue key to reopen")

    # Stats
    stats_parser = subparsers.add_parser("stats", help="Show issue statistics")

    # Comment
    comment_parser = subparsers.add_parser("comment", help="Add comment to an issue")
    comment_parser.add_argument("issue_key", help="Issue key to comment on")
    comment_parser.add_argument("comment", help="Comment text")

    # Quality Gate
    qg_parser = subparsers.add_parser("quality-gate", help="Show quality gate status")

    # Security Hotspots
    hotspots_parser = subparsers.add_parser("hotspots", help="List security hotspots")
    hotspots_parser.add_argument(
        "--status", choices=["TO_REVIEW", "REVIEWED", "SAFE", "FIXED"], default="TO_REVIEW", help="Filter by status"
    )
    hotspots_parser.add_argument("--limit", type=int, default=20, help="Number of hotspots to show")

    # Mark hotspot safe
    safe_parser = subparsers.add_parser("mark-safe", help="Mark security hotspot as safe")
    safe_parser.add_argument("hotspot_key", help="Hotspot key to mark")
    safe_parser.add_argument("--comment", help="Comment explaining why it's safe")

    # Coverage
    coverage_parser = subparsers.add_parser("coverage", help="Show coverage metrics")
    coverage_parser.add_argument("--new-code", action="store_true", help="Show metrics for new code only")

    args = parser.parse_args()

    # Load token
    if not SONAR_TOKEN_FILE.exists():
        print(f"Error: Token file not found at {SONAR_TOKEN_FILE}")
        print("Please save your SonarCloud token to ~/.sonartoken")
        sys.exit(1)

    token = SONAR_TOKEN_FILE.read_text().strip()
    client = SonarClient(token)

    try:
        if args.command == "list":
            issues = client.search_issues(severity=args.severity, resolved=args.resolved, limit=args.limit)

            if not issues:
                print("No issues found matching criteria.")
            else:
                print(f"\nFound {len(issues)} issues:\n")
                for issue in issues:
                    print(format_issue(issue))

        elif args.command == "mark-fp":
            if args.comment:
                # Add comment first
                client.add_comment(args.issue_key, f"Marking as false positive: {args.comment}")

            result = client.transition_issue(args.issue_key, "falsepositive")
            print(f"✓ Marked {args.issue_key} as false positive")
            print(f"  Status: {result['issue']['issueStatus']}")

        elif args.command == "mark-wontfix":
            if args.comment:
                # Add comment first
                client.add_comment(args.issue_key, f"Marking as won't fix: {args.comment}")

            result = client.transition_issue(args.issue_key, "wontfix")
            print(f"✓ Marked {args.issue_key} as won't fix")
            print(f"  Status: {result['issue']['issueStatus']}")

        elif args.command == "reopen":
            result = client.transition_issue(args.issue_key, "reopen")
            print(f"✓ Reopened {args.issue_key}")
            print(f"  Status: {result['issue']['status']}")

        elif args.command == "comment":
            client.add_comment(args.issue_key, args.comment)
            print(f"✓ Added comment to {args.issue_key}")

        elif args.command == "stats":
            stats = client.get_stats()
            print(f"\nSonarCloud Statistics for {PROJECT_KEY}")
            print("=" * 50)
            print(f"Total Open Issues: {stats['total']}")

            print("\nBy Severity:")
            for severity in ["BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"]:
                count = stats["by_severity"].get(severity, 0)
                if count > 0:
                    print(f"  {severity}: {count}")

            print("\nBy Type:")
            for issue_type, count in stats["by_type"].items():
                print(f"  {issue_type}: {count}")

            print("\nTop 5 Rules:")
            for rule, count in stats["top_rules"]:
                print(f"  {rule}: {count} issues")

        elif args.command == "quality-gate":
            qg_status = client.get_quality_gate_status()
            print(f"\nQuality Gate Status: {qg_status['status']}")
            print("=" * 50)

            if qg_status.get("periods"):
                period = qg_status["periods"][0]
                print(f"Analysis Period: {period['mode']} ({period['date']})\n")

            print("Conditions:")
            for condition in qg_status["conditions"]:
                status_icon = "✓" if condition["status"] == "OK" else "✗"
                metric = condition["metricKey"].replace("_", " ").title()
                actual = condition.get("actualValue", "N/A")
                threshold = condition["errorThreshold"]
                comparator = "≥" if condition["comparator"] == "LT" else "≤"

                print(f"  {status_icon} {metric}: {actual} (needs {comparator} {threshold})")

            if qg_status["status"] != "OK":
                print("\n⚠️  Quality gate is failing! Fix the above issues to pass.")

        elif args.command == "hotspots":
            result = client.search_hotspots(status=args.status, limit=args.limit)
            hotspots = result["hotspots"]

            if not hotspots:
                print(f"No security hotspots found with status {args.status}.")
            else:
                print(f"\nFound {result['paging']['total']} security hotspots (showing {len(hotspots)}):")
                print("=" * 70)

                # Group by vulnerability probability
                by_risk = {}
                for hotspot in hotspots:
                    risk = hotspot["vulnerabilityProbability"]
                    if risk not in by_risk:
                        by_risk[risk] = []
                    by_risk[risk].append(hotspot)

                for risk in ["HIGH", "MEDIUM", "LOW"]:
                    if risk in by_risk:
                        print(f"\n{risk} RISK ({len(by_risk[risk])} hotspots):\n")
                        for hotspot in by_risk[risk]:
                            print(format_hotspot(hotspot))

        elif args.command == "mark-safe":
            if args.comment:
                comment = f"Marking as safe: {args.comment}"
            else:
                comment = "Reviewed and determined to be safe"

            result = client.mark_hotspot_safe(args.hotspot_key, comment)
            print(f"✓ Marked {args.hotspot_key} as safe")

        elif args.command == "coverage":
            metrics = client.get_coverage_metrics(new_code=args.new_code)
            component = metrics["component"]

            # Extract measures - handle both value and periods formats
            measures = {}
            for m in component.get("measures", []):
                if "value" in m:
                    measures[m["metric"]] = m["value"]
                elif "periods" in m and m["periods"]:
                    measures[m["metric"]] = m["periods"][0]["value"]

            print(f"\nCoverage Metrics for {PROJECT_KEY}")
            print("=" * 50)

            prefix = "new_" if args.new_code else ""
            scope = "New Code" if args.new_code else "Overall"

            if f"{prefix}coverage" in measures:
                coverage = float(measures[f"{prefix}coverage"])
                print(f"{scope} Coverage: {coverage:.1f}%")

                if coverage < 80 and args.new_code:
                    print("⚠️  New code coverage is below 80% threshold!")

            if f"{prefix}lines_to_cover" in measures:
                lines_to_cover = int(float(measures.get(f"{prefix}lines_to_cover", 0)))
                uncovered_lines = int(float(measures.get(f"{prefix}uncovered_lines", 0)))
                covered_lines = lines_to_cover - uncovered_lines

                print("\nLines:")
                print(f"  Total to cover: {lines_to_cover}")
                print(f"  Covered: {covered_lines}")
                print(f"  Uncovered: {uncovered_lines}")

            if f"{prefix}line_coverage" in measures:
                print(f"\nLine Coverage: {float(measures[f'{prefix}line_coverage']):.1f}%")

            if f"{prefix}branch_coverage" in measures:
                print(f"Branch Coverage: {float(measures[f'{prefix}branch_coverage']):.1f}%")

        else:
            parser.print_help()

    except requests.exceptions.HTTPError as e:
        print(f"Error: {e}")
        if e.response.status_code == 401:
            print("Authentication failed. Check your token in ~/.sonartoken")
        elif e.response.status_code == 403:
            print("Permission denied. You may not have access to perform this action.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
