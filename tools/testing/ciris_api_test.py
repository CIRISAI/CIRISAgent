#!/usr/bin/env python3
"""
CIRIS API Testing Script
Provides easy functions for testing the CIRIS API with proper authentication
"""

import json
import sys
import time
from typing import Any, Dict, List, Optional

import requests


class CIRISClient:
    """Simple client for interacting with CIRIS API"""

    def __init__(
        self, base_url: str = "http://localhost:8080", username: str = "admin", password: str = "ciris_admin_password"
    ):
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None
        self.username = username
        self.password = password
        self.session = requests.Session()

    def authenticate(self) -> bool:
        """Authenticate and store token"""
        try:
            response = self.session.post(
                f"{self.base_url}/v1/auth/login", json={"username": self.username, "password": self.password}
            )
            response.raise_for_status()
            data = response.json()
            self.token = data.get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            print("✓ Authenticated successfully")
            return True
        except Exception as e:
            print(f"✗ Authentication failed: {e}")
            return False

    def interact(self, message: str, channel_id: Optional[str] = None) -> Dict[str, Any]:
        """Send a message to the agent"""
        if not self.token:
            self.authenticate()

        if channel_id is None:
            channel_id = "api_0.0.0.0_8080"

        try:
            response = self.session.post(
                f"{self.base_url}/v1/agent/interact", json={"message": message, "channel_id": channel_id}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"✗ Interaction failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            return {}

    def mock_command(self, command: str, *args) -> Dict[str, Any]:
        """Send a mock LLM command"""
        full_command = f"${command}"
        if args:
            full_command += " " + " ".join(str(arg) for arg in args)
        return self.interact(full_command)

    def get_audit_entries(self, limit: int = 10, handler: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get audit entries, optionally filtered by handler"""
        if not self.token:
            self.authenticate()

        try:
            params = {"limit": limit}
            response = self.session.get(f"{self.base_url}/v1/audit/entries", params=params)
            response.raise_for_status()
            entries = response.json().get("data", {}).get("entries", [])

            if handler:
                # Filter entries by handler type
                filtered = []
                for entry in entries:
                    action = entry.get("action", "").upper()
                    # Match either format: AUDITEVENTTYPE.HANDLER_ACTION_X or AUDITEVENTTYPE.HANDLER_X
                    if (
                        action == f"AUDITEVENTTYPE.HANDLER_ACTION_{handler.upper()}"
                        or action == f"AUDITEVENTTYPE.HANDLER_{handler.upper()}"
                    ):
                        filtered.append(entry)
                return filtered
            return entries
        except Exception as e:
            print(f"✗ Failed to get audit entries: {e}")
            return []

    def health_check(self) -> Dict[str, Any]:
        """Check system health"""
        try:
            response = self.session.get(f"{self.base_url}/v1/system/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"✗ Health check failed: {e}")
            return {}

    def wait_for_handler(self, handler: str, timeout: int = 10) -> bool:
        """Wait for a specific handler to appear in audit log"""
        start_time = time.time()
        print(f"⏳ Waiting for {handler} handler (timeout: {timeout}s)...")

        while time.time() - start_time < timeout:
            entries = self.get_audit_entries(limit=50, handler=handler)
            if entries:
                print(f"✓ Found {handler} handler entry")
                return True
            time.sleep(0.5)

        print(f"✗ Timeout waiting for {handler} handler")
        return False


def test_mock_handlers():
    """Test all mock LLM handlers"""
    client = CIRISClient()

    if not client.authenticate():
        return

    print("\n=== Testing Mock LLM Handlers ===\n")

    # Test cases for each handler
    test_cases = [
        ("speak", ["Hello from test!"]),
        ("recall", ["test memories"]),
        ("memorize", ["Test memory content"]),
        ("ponder", ["What is the meaning of life?"]),
        ("tool", ["SELF_HELP"]),
        ("observe", ["test_channel"]),
        ("defer", ["Need more information"]),
        ("reject", ["Invalid request"]),
        ("forget", ["memory_123"]),
        ("task_complete", []),
    ]

    results = {}

    for command, args in test_cases:
        print(f"\n--- Testing ${command} ---")

        # Send command
        response = client.mock_command(command, *args)

        if response:
            print(f"Response: {response.get('data', {}).get('response', 'No response')}")

            # Wait a bit for processing
            time.sleep(1)

            # Check audit log
            handler_found = client.wait_for_handler(command, timeout=5)
            results[command] = handler_found
        else:
            results[command] = False

    # Summary
    print("\n=== Test Results ===")
    for command, success in results.items():
        status = "✓" if success else "✗"
        print(f"{status} {command}: {'PASS' if success else 'FAIL'}")

    # Get recent audit entries for debugging
    print("\n=== Recent Audit Entries ===")
    entries = client.get_audit_entries(limit=20)
    for entry in entries[:10]:
        print(f"- {entry.get('action', 'Unknown')} at {entry.get('timestamp', 'Unknown')}")


def test_specific_handler(handler: str, *args):
    """Test a specific handler"""
    client = CIRISClient()

    if not client.authenticate():
        return

    print(f"\n=== Testing {handler} handler ===")

    # Send command
    response = client.mock_command(handler, *args)
    print(f"Response: {json.dumps(response, indent=2)}")

    # Wait for handler
    if client.wait_for_handler(handler):
        # Get the specific entry
        entries = client.get_audit_entries(limit=10, handler=handler)
        if entries:
            print("\nAudit entry:")
            print(json.dumps(entries[0], indent=2))
    else:
        # Debug: show all recent entries
        print("\nAll recent audit entries:")
        entries = client.get_audit_entries(limit=20)
        for entry in entries:
            print(f"- {entry.get('action', 'Unknown')}")


def interactive_mode():
    """Interactive mode for testing"""
    client = CIRISClient()

    if not client.authenticate():
        return

    print("\n=== CIRIS Interactive Mode ===")
    print("Commands:")
    print("  $<command> [args]  - Send mock LLM command")
    print("  /audit [n]         - Show last n audit entries")
    print("  /health            - Check system health")
    print("  /quit              - Exit")
    print("")

    while True:
        try:
            user_input = input("ciris> ").strip()

            if not user_input:
                continue

            if user_input == "/quit":
                break
            elif user_input.startswith("/audit"):
                parts = user_input.split()
                limit = int(parts[1]) if len(parts) > 1 else 10
                entries = client.get_audit_entries(limit=limit)
                for entry in entries:
                    print(f"- {entry.get('timestamp', 'Unknown')}: {entry.get('action', 'Unknown')}")
            elif user_input == "/health":
                health = client.health_check()
                print(json.dumps(health, indent=2))
            else:
                # Send as message
                response = client.interact(user_input)
                if response:
                    print(f"Agent: {response.get('data', {}).get('response', 'No response')}")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            test_mock_handlers()
        elif sys.argv[1] == "interactive":
            interactive_mode()
        else:
            # Test specific handler
            handler = sys.argv[1]
            args = sys.argv[2:] if len(sys.argv) > 2 else []
            test_specific_handler(handler, *args)
    else:
        print("Usage:")
        print("  python ciris_api_test.py test              - Test all handlers")
        print("  python ciris_api_test.py interactive       - Interactive mode")
        print("  python ciris_api_test.py <handler> [args]  - Test specific handler")
        print("\nExample:")
        print("  python ciris_api_test.py speak 'Hello world!'")
