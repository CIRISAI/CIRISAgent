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
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

    def get_quality_gate_status(
        self, branch: Optional[str] = None, pull_request: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get quality gate status for the project, branch, or PR.

        Args:
            branch: Branch name (e.g., 'main', '1.3.1')
            pull_request: Pull request ID (e.g., '432')

        Returns:
            Quality gate status with conditions and timestamp
        """
        params = {"projectKey": PROJECT_KEY}
        if pull_request:
            params["pullRequest"] = pull_request
        elif branch:
            params["branch"] = branch

        response = self.session.get(f"{SONAR_API_BASE}/qualitygates/project_status", params=params)
        response.raise_for_status()
        return response.json()["projectStatus"]

    def get_project_analyses(
        self, branch: Optional[str] = None, pull_request: Optional[str] = None, limit: int = 1
    ) -> Dict[str, Any]:
        """Get recent analyses for project, branch, or PR.

        Args:
            branch: Branch name
            pull_request: Pull request ID
            limit: Number of analyses to retrieve

        Returns:
            List of analyses with timestamps
        """
        params = {"project": PROJECT_KEY, "ps": limit}
        if pull_request:
            params["pullRequest"] = pull_request
        elif branch:
            params["branch"] = branch

        response = self.session.get(f"{SONAR_API_BASE}/project_analyses/search", params=params)
        response.raise_for_status()
        return response.json()

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

    def get_coverage_metrics(self, new_code: bool = False, pull_request: Optional[str] = None) -> Dict[str, Any]:
        """Get coverage metrics for the project or a specific PR."""
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

        params = {"component": PROJECT_KEY, "metricKeys": ",".join(metrics)}
        if pull_request:
            params["pullRequest"] = pull_request

        response = self.session.get(f"{SONAR_API_BASE}/measures/component", params=params)
        response.raise_for_status()
        return response.json()

    def get_pr_analysis(self, pull_request: str) -> Dict[str, Any]:
        """Get analysis for a specific pull request."""
        params = {"pullRequest": pull_request, "component": PROJECT_KEY}

        # Get PR quality gate status
        qg_response = self.session.get(f"{SONAR_API_BASE}/qualitygates/project_status", params=params)
        qg_response.raise_for_status()
        quality_gate = qg_response.json()

        # Get PR coverage metrics
        coverage_metrics = self.get_coverage_metrics(new_code=True, pull_request=pull_request)

        # Get PR issues
        issues_params = {
            "componentKeys": PROJECT_KEY,
            "pullRequest": pull_request,
            "resolved": "false",
            "ps": 100,
        }
        issues_response = self.session.get(f"{SONAR_API_BASE}/issues/search", params=issues_params)
        issues_response.raise_for_status()
        issues_data = issues_response.json()

        return {
            "quality_gate": quality_gate,
            "coverage": coverage_metrics,
            "issues": issues_data,
        }


def get_recent_prs(limit: int = 2) -> List[Tuple[str, str]]:
    """Get recent open PRs from GitHub.

    Returns:
        List of (PR number, branch name) tuples
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--limit", str(limit), "--json", "number,headRefName"],
            capture_output=True,
            text=True,
            check=True,
        )
        prs = json.loads(result.stdout)
        return [(str(pr["number"]), pr["headRefName"]) for pr in prs]
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        return []


def format_time_ago(iso_timestamp: str) -> str:
    """Format ISO timestamp as 'X minutes ago' or 'X hours ago'.

    Args:
        iso_timestamp: ISO format timestamp

    Returns:
        Human-readable time ago string
    """
    try:
        # Parse ISO timestamp
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt

        # Calculate time ago
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours}h ago"
        else:
            days = seconds // 86400
            return f"{days}d ago"
    except (ValueError, AttributeError):
        return "unknown"


def format_quality_gate_summary(qg_status: Dict[str, Any], label: str, timestamp: Optional[str] = None) -> str:
    """Format quality gate status as a summary line.

    Args:
        qg_status: Quality gate status from API
        label: Label for this check (e.g., "Main", "PR #432")
        timestamp: Optional analysis timestamp

    Returns:
        Formatted summary string
    """
    status = qg_status["status"]
    status_icon = "✅" if status == "OK" else "❌"

    time_str = ""
    if timestamp:
        time_str = f" ({format_time_ago(timestamp)})"

    # Find failed conditions
    failed_conditions = []
    if qg_status.get("conditions"):
        for condition in qg_status["conditions"]:
            if condition["status"] != "OK":
                metric = condition["metricKey"].replace("_", " ").replace("new ", "").title()
                actual = condition.get("actualValue", "?")
                threshold = condition["errorThreshold"]
                comparator = "≥" if condition["comparator"] == "LT" else "≤"
                failed_conditions.append(f"{metric}: {actual}% (needs {comparator} {threshold}%)")

    result = f"{status_icon} {label}: {status}{time_str}"
    if failed_conditions:
        result += "\n    " + "\n    ".join(failed_conditions)

    return result


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
    coverage_parser.add_argument("--pr", type=str, help="Pull request number (e.g., 430)")

    # PR Analysis
    pr_parser = subparsers.add_parser("pr", help="Analyze a specific pull request")
    pr_parser.add_argument("pr_number", type=str, help="Pull request number")

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
            print("\n🔍 SonarCloud Quality Gate Status")
            print("=" * 70)
            print("\nℹ️  Note: SonarCloud analysis runs after successful CI (~15 minutes)")
            print("=" * 70)

            # Get main branch status
            try:
                main_qg = client.get_quality_gate_status(branch="main")
                main_analyses = client.get_project_analyses(branch="main", limit=1)
                main_timestamp = None
                if main_analyses.get("analyses"):
                    main_timestamp = main_analyses["analyses"][0]["date"]
                print(f"\n{format_quality_gate_summary(main_qg, 'Main', main_timestamp)}")
            except Exception as e:
                print(f"\n❌ Main: Could not retrieve status ({e})")

            # Get recent PRs
            recent_prs = get_recent_prs(limit=2)
            if recent_prs:
                print("\nRecent Pull Requests:")
                for pr_num, branch_name in recent_prs:
                    try:
                        # Try PR-based query first
                        pr_qg = client.get_quality_gate_status(pull_request=pr_num)
                        pr_analyses = client.get_project_analyses(pull_request=pr_num, limit=1)
                        pr_timestamp = None
                        if pr_analyses.get("analyses"):
                            pr_timestamp = pr_analyses["analyses"][0]["date"]
                        print(f"{format_quality_gate_summary(pr_qg, f'PR #{pr_num} ({branch_name})', pr_timestamp)}")
                    except requests.exceptions.HTTPError as pr_error:
                        # Fall back to branch-based query
                        try:
                            branch_qg = client.get_quality_gate_status(branch=branch_name)
                            branch_analyses = client.get_project_analyses(branch=branch_name, limit=1)
                            branch_timestamp = None
                            if branch_analyses.get("analyses"):
                                branch_timestamp = branch_analyses["analyses"][0]["date"]
                            print(
                                f"{format_quality_gate_summary(branch_qg, f'PR #{pr_num} ({branch_name})', branch_timestamp)}"
                            )
                        except Exception as branch_error:
                            print(f"❌ PR #{pr_num} ({branch_name}): No SonarCloud analysis yet")
            else:
                print("\nNo recent open PRs found.")

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
            pr_number = getattr(args, "pr", None)
            metrics = client.get_coverage_metrics(new_code=args.new_code, pull_request=pr_number)
            component = metrics["component"]

            # Extract measures - handle both value and periods formats
            measures = {}
            for m in component.get("measures", []):
                if "value" in m:
                    measures[m["metric"]] = m["value"]
                elif "periods" in m and m["periods"]:
                    measures[m["metric"]] = m["periods"][0]["value"]

            scope_label = f"PR #{pr_number}" if pr_number else PROJECT_KEY
            print(f"\nCoverage Metrics for {scope_label}")
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

        elif args.command == "pr":
            # Get PR and branch info from GitHub
            try:
                pr_result = subprocess.run(
                    ["gh", "pr", "view", args.pr_number, "--json", "headRefName"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                pr_info = json.loads(pr_result.stdout)
                branch_name = pr_info["headRefName"]
            except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
                print(f"Error: Could not retrieve PR #{args.pr_number} from GitHub")
                sys.exit(1)

            print(f"\n🔍 Pull Request #{args.pr_number} ({branch_name}) Analysis")
            print("=" * 70)

            # Try branch-based quality gate query
            try:
                qg_status = client.get_quality_gate_status(branch=branch_name)
                status = qg_status["status"]
                status_icon = "✅" if status == "OK" else "❌"
                print(f"\nQuality Gate: {status_icon} {status}")

                if qg_status.get("conditions"):
                    print("\nConditions:")
                    for condition in qg_status["conditions"]:
                        cond_status = "✓" if condition["status"] == "OK" else "✗"
                        metric = condition["metricKey"].replace("_", " ").title()
                        actual = condition.get("actualValue", "N/A")
                        threshold = condition["errorThreshold"]
                        comparator = "≥" if condition["comparator"] == "LT" else "≤"
                        print(f"  {cond_status} {metric}: {actual} (needs {comparator} {threshold})")
            except Exception as e:
                print(f"\n❌ Quality Gate: Could not retrieve status ({e})")

            # Coverage Metrics
            try:
                coverage_metrics = client.get_coverage_metrics(new_code=True, pull_request=args.pr_number)
                coverage_comp = coverage_metrics["component"]
                measures = {}
                for m in coverage_comp.get("measures", []):
                    if "value" in m:
                        measures[m["metric"]] = m["value"]
                    elif "periods" in m and m["periods"]:
                        measures[m["metric"]] = m["periods"][0]["value"]

                print("\n📊 Coverage on New Code:")
                if "new_coverage" in measures:
                    coverage = float(measures["new_coverage"])
                    print(f"  Coverage: {coverage:.1f}%")
                    if coverage < 80:
                        print("  ⚠️  Below 80% threshold!")

                if "new_lines_to_cover" in measures:
                    lines_to_cover = int(float(measures.get("new_lines_to_cover", 0)))
                    uncovered_lines = int(float(measures.get("new_uncovered_lines", 0)))
                    covered_lines = lines_to_cover - uncovered_lines
                    print(f"  Lines to cover: {lines_to_cover}")
                    print(f"  Covered: {covered_lines}")
                    print(f"  Uncovered: {uncovered_lines}")
                    print(f"\n  Need {int(lines_to_cover * 0.8) - covered_lines} more lines covered for 80%")
            except Exception as e:
                print(f"\n❌ Coverage: Could not retrieve metrics ({e})")

            # Issues
            try:
                issues_params = {
                    "componentKeys": PROJECT_KEY,
                    "pullRequest": args.pr_number,
                    "resolved": "false",
                    "ps": 100,
                }
                issues_response = client.session.get(f"{SONAR_API_BASE}/issues/search", params=issues_params)
                issues_response.raise_for_status()
                issues_data = issues_response.json()

                total_issues = issues_data["total"]
                print(f"\n🐛 Issues: {total_issues}")

                if total_issues > 0:
                    # Group by severity
                    by_severity = {}
                    for issue in issues_data["issues"]:
                        severity = issue["severity"]
                        by_severity[severity] = by_severity.get(severity, 0) + 1

                    print("  By severity:")
                    for sev in ["BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"]:
                        if sev in by_severity:
                            print(f"    {sev}: {by_severity[sev]}")
            except Exception as e:
                print(f"\n❌ Issues: Could not retrieve issues ({e})")

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
