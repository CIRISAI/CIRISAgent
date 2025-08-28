#!/usr/bin/env python3
"""
Check if the latest fixes are deployed to agents.ciris.ai
"""

import json
import subprocess

import requests


def get_latest_commit():
    """Get the latest commit hash from upstream main"""
    result = subprocess.run(
        ["git", "ls-remote", "https://github.com/CIRISAI/CIRISAgent.git", "main"], capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.split()[0][:7]  # Short hash
    return None


def check_gui_version():
    """Check the GUI version at agents.ciris.ai"""
    try:
        # Try to fetch the GUI and look for version markers
        response = requests.get("https://agents.ciris.ai", timeout=10)
        if response.status_code == 200:
            # Check if our OAuth fix is present (looking for the /v1/ in OAuth URLs)
            if "/api/${agent.agent_id}/v1/auth/oauth/" in response.text:
                return True, "OAuth fix detected in GUI!"
            elif "/api/${agent.agent_id}/auth/oauth/" in response.text:
                return False, "Old OAuth routing still in place"
            else:
                return None, "Could not detect OAuth routing version"
    except Exception as e:
        return None, f"Error checking GUI: {e}"
    return None, "Could not determine version"


def check_ci_status():
    """Check if CI/CD has completed for the latest commit"""
    result = subprocess.run(
        ["gh", "run", "list", "--repo", "CIRISAI/CIRISAgent", "--limit", "1", "--json", "status,conclusion,headSha"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        runs = json.loads(result.stdout)
        if runs:
            latest_run = runs[0]
            return latest_run.get("status"), latest_run.get("conclusion"), latest_run.get("headSha", "")[:7]
    return None, None, None


def main():
    print("🔍 Checking deployment status for agents.ciris.ai...")
    print("=" * 60)

    # Check latest commit
    latest_commit = get_latest_commit()
    print(f"📦 Latest upstream commit: {latest_commit}")

    # Check CI/CD status
    ci_status, ci_conclusion, ci_commit = check_ci_status()
    print(f"🔧 CI/CD Status: {ci_status} ({ci_conclusion}) for commit {ci_commit}")

    # Check if GUI has the fix
    has_fix, message = check_gui_version()
    print(f"🌐 Production GUI: {message}")

    print("=" * 60)

    # Determine overall status
    if has_fix:
        print("✅ 🎉 agents.ciris.ai has the new SDK! Go test good buddy! 🎉")
        print("\nWhat to test:")
        print("  1. Regular login with username/password")
        print("  2. OAuth login with Google")
        print("  3. OAuth login with Discord")
        print("\nAll should route through /api/datum/v1/auth/* now!")
    elif ci_status == "in_progress":
        print("⏳ CI/CD is still running... Almost there!")
        print(f"   Current status: {ci_status}")
        print("   ETA: 10-15 minutes from start")
    elif ci_conclusion == "success" and not has_fix:
        print("🚀 CI/CD completed! Images are being deployed...")
        print("   CIRISManager is restarting containers")
        print("   ETA: 2-5 minutes")
    else:
        print("⏰ Not yet, please keep waiting...")
        print("   CI/CD needs to complete first")

    print("\n💡 Run this tool again in a minute to check status!")


if __name__ == "__main__":
    main()
