"""
Diagnostic script to understand why handlers aren't being invoked properly.
"""

import json
import time

import requests


def diagnose_handler_issue():
    """Run diagnostics to understand the handler invocation issue."""

    # Login
    print("1. Authenticating...")
    login_resp = requests.post(
        "http://localhost:8080/v1/auth/login", json={"username": "admin", "password": "qa_test_password_12345"}
    )
    if login_resp.status_code != 200:
        print(f"❌ Login failed: {login_resp.text}")
        return

    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Authentication successful")

    # Send a simple memorize command
    print("\n2. Sending $memorize command...")
    message = "$memorize test content"
    interact_resp = requests.post(
        "http://localhost:8080/v1/agent/interact",
        json={"message": message, "channel_id": "api_diagnostic"},
        headers=headers,
    )

    print(f"Response status: {interact_resp.status_code}")
    result = interact_resp.json()
    print(f"Response data: {json.dumps(result, indent=2)}")

    # Check what state the agent is in
    if "data" in result:
        print(f"\nAgent state: {result['data'].get('state', 'unknown')}")
        print(f"Message ID: {result['data'].get('message_id', 'none')}")

    # Wait for processing
    print("\n3. Waiting for processing...")
    time.sleep(10)

    # Check audit entries
    print("\n4. Checking audit entries...")
    audit_resp = requests.get("http://localhost:8080/v1/audit/entries?limit=20", headers=headers)

    if audit_resp.status_code == 200:
        entries = audit_resp.json().get("data", {}).get("entries", [])
        print(f"Found {len(entries)} audit entries")

        # Look for handler-related entries
        handler_entries = []
        task_entries = []
        thought_entries = []

        for entry in entries:
            resource = entry.get("resource", "")
            if "handler" in resource:
                handler_entries.append(entry)
            elif "task" in resource:
                task_entries.append(entry)
            elif "thought" in resource:
                thought_entries.append(entry)

        print(f"\nHandler entries: {len(handler_entries)}")
        print(f"Task entries: {len(task_entries)}")
        print(f"Thought entries: {len(thought_entries)}")

        # Show recent handler entries
        if handler_entries:
            print("\nRecent handler entries:")
            for entry in handler_entries[:5]:
                print(f"- {entry['action']} on {entry['resource']}")
                if "handler_type" in entry.get("details", {}):
                    print(f"  Handler type: {entry['details']['handler_type']}")

        # Show recent task entries
        if task_entries:
            print("\nRecent task entries:")
            for entry in task_entries[:5]:
                print(f"- {entry['action']} on {entry['resource']}")
                if "content" in entry.get("details", {}):
                    print(f"  Content: {entry['details']['content'][:100]}...")

    # Check system health
    print("\n5. Checking system health...")
    health_resp = requests.get("http://localhost:8080/v1/system/health", headers=headers)

    if health_resp.status_code == 200:
        health = health_resp.json()
        services = health.get("data", {}).get("services", {})

        # Check key services
        print("\nKey service status:")
        for service in ["llm", "memory", "runtime_control", "communication"]:
            status = services.get(service, {})
            print(f"- {service}: {status.get('status', 'unknown')}")

    # Try to get more detailed logs
    print("\n6. Checking for error patterns...")

    # Get system status
    status_resp = requests.get("http://localhost:8080/v1/system/status", headers=headers)

    if status_resp.status_code == 200:
        status = status_resp.json()
        system_data = status.get("data", {})

        # Check cognitive state
        if "cognitive_state" in system_data:
            print(f"\nCognitive state: {system_data['cognitive_state']}")

        # Check active tasks
        if "active_tasks" in system_data:
            active = system_data["active_tasks"]
            print(f"\nActive tasks: {active}")


if __name__ == "__main__":
    diagnose_handler_issue()
