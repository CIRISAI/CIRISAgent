"""
System health checks - production, CI/CD, deployments.
Simple subprocess calls, no complex dependencies.
"""

import json
import subprocess
from typing import Dict


def check_production() -> Dict[str, str]:
    """Check production status."""
    status = {}

    # Check main site
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "https://agents.ciris.ai"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            code = result.stdout.strip()
            status["production"] = "UP" if code == "200" else f"HTTP {code}"
        else:
            status["production"] = "DOWN"
    except Exception:
        status["production"] = "UNREACHABLE"

    # Check datum agent
    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "https://agents.ciris.ai/api/datum/v1/system/health",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            code = result.stdout.strip()
            status["datum"] = "HEALTHY" if code == "200" else f"HTTP {code}"
        else:
            status["datum"] = "DOWN"
    except Exception:
        status["datum"] = "UNREACHABLE"

    return status


def check_ci_status() -> Dict[str, str]:
    """Check CI/CD pipeline status."""
    try:
        result = subprocess.run(
            ["gh", "run", "list", "--repo", "CIRISAI/CIRISAgent", "--limit", "1", "--json", "status,conclusion"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            runs = json.loads(result.stdout)
            if runs:
                run = runs[0]
                status = run.get("status", "UNKNOWN")
                conclusion = run.get("conclusion", "")
                if conclusion:
                    return {"ci_cd": conclusion.upper()}
                else:
                    return {"ci_cd": status.upper()}
        return {"ci_cd": "NO RUNS"}
    except Exception:
        return {"ci_cd": "ERROR"}


def check_deployment() -> str:
    """Check if recent deployment is active."""
    try:
        # Check if build is running - specifically the Build and Deploy workflow
        result = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--repo",
                "CIRISAI/CIRISAgent",
                "--workflow",
                "Build and Deploy",
                "--limit",
                "1",
                "--json",
                "status,conclusion,headSha",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            runs = json.loads(result.stdout)
            if runs:
                run = runs[0]
                status = run.get("status", "")
                conclusion = run.get("conclusion", "")
                commit = run.get("headSha", "")[:7]

                if status == "in_progress":
                    return f"⏳ Deployment in progress [{commit}]"
                elif status == "completed":
                    if conclusion == "success":
                        return f"✅ Recent deployment succeeded [{commit}]"
                    elif conclusion == "failure":
                        return f"❌ Recent deployment FAILED [{commit}]"
                    elif conclusion == "cancelled":
                        return f"⚠️ Recent deployment cancelled [{commit}]"
                    else:
                        return f"Recent deployment {conclusion} [{commit}]"

        return ""
    except Exception:
        return ""


def check_all() -> Dict[str, str]:
    """Run all health checks."""
    health = {}
    health.update(check_production())
    health.update(check_ci_status())

    deployment = check_deployment()
    if deployment:
        health["deployment"] = deployment

    return health
