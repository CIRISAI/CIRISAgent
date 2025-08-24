#!/usr/bin/env python
"""
Comprehensive QA test for all 10 CIRIS handlers using mock LLM.

This test exercises all handlers through the interact endpoint using
special mock LLM commands.
"""

import json
import sys
import time
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "http://localhost:8000"


class HandlerTestSuite:
    """Test suite for all CIRIS handlers."""

    def __init__(self):
        self.token = None
        self.user_id = None
        self.test_results = {}
        self.audit_entries = []

    def get_token(self) -> str:
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        if response.status_code != 200:
            print(f"❌ Failed to get token: {response.status_code}")
            sys.exit(1)

        self.token = response.json()["access_token"]
        print(f"✅ Got auth token")
        return self.token

    def interact(self, message: str) -> Dict[str, Any]:
        """Send message to interact endpoint."""
        response = requests.post(
            f"{BASE_URL}/v1/agent/interact",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"message": message},
        )

        if response.status_code != 200:
            print(f"❌ Interact failed with {response.status_code}: {response.text}")
            return {"error": response.text, "status_code": response.status_code}

        return response.json()

    def get_audit_log(self, limit: int = 10) -> List[Dict]:
        """Get recent audit log entries."""
        response = requests.get(
            f"{BASE_URL}/v1/audit/events?limit={limit}", headers={"Authorization": f"Bearer {self.token}"}
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("events", [])
        return []

    def check_incidents(self) -> List[str]:
        """Check incidents log for recent errors."""
        # Read last 100 lines of incidents log
        try:
            with open("/home/emoore/TESTING/CIRISAgent/logs/incidents_latest.log", "r") as f:
                lines = f.readlines()[-100:]
                errors = [line for line in lines if "ERROR" in line or "CRITICAL" in line]
                return errors[-5:] if errors else []  # Return last 5 errors
        except:
            return []

    def test_handler(self, handler_name: str, command: str, description: str) -> bool:
        """Test a specific handler."""
        print(f"\n{'='*60}")
        print(f"Testing {handler_name}: {description}")
        print(f"Command: {command}")
        print("-" * 60)

        # Get audit log before
        audit_before = self.get_audit_log(5)

        # Send command
        result = self.interact(command)

        # Wait for processing
        time.sleep(1)

        # Get audit log after
        audit_after = self.get_audit_log(5)

        # Check for new audit entries
        new_entries = []
        if audit_after and audit_before:
            # Find new entries by comparing timestamps
            before_ids = {e.get("event_id") for e in audit_before if e.get("event_id")}
            new_entries = [e for e in audit_after if e.get("event_id") not in before_ids]

        # Analyze result
        success = False
        if "error" in result:
            print(f"❌ Handler failed: {result['error']}")
        elif "response" in result:
            response = result.get("response", "")
            print(f"Response: {response[:200]}...")

            # Check if handler was executed (look for handler name in audit)
            handler_executed = any(handler_name.lower() in str(e).lower() for e in new_entries)

            if handler_executed:
                print(f"✅ Handler {handler_name} executed (found in audit log)")
                success = True
            elif handler_name == "SPEAK" and response:
                print(f"✅ SPEAK handler executed (got response)")
                success = True
            elif handler_name == "OBSERVE" and "observe" in response.lower():
                print(f"✅ OBSERVE handler executed")
                success = True
            else:
                print(f"⚠️  Handler execution unclear, checking response...")
                # Check response for handler markers
                if any(
                    marker in response.lower()
                    for marker in [handler_name.lower(), "completed", "executed", "processed"]
                ):
                    print(f"✅ Handler appears to have executed")
                    success = True
                else:
                    print(f"❓ Cannot confirm handler execution")

        # Store result
        self.test_results[handler_name] = {
            "success": success,
            "command": command,
            "response": result.get("response", "")[:200],
            "new_audit_entries": len(new_entries),
        }

        return success

    def run_all_tests(self):
        """Run tests for all handlers."""
        print("=" * 80)
        print("CIRIS HANDLER TEST SUITE")
        print("=" * 80)

        # Get token
        self.get_token()

        # Get user info
        consent_resp = requests.get(f"{BASE_URL}/v1/consent/status", headers={"Authorization": f"Bearer {self.token}"})
        if consent_resp.status_code == 200:
            self.user_id = consent_resp.json().get("user_id", "unknown")
            print(f"User ID: {self.user_id}")

        # Test each handler
        handlers = [
            # Basic handlers
            ("SPEAK", "$force_action:speak action_params:Hello from QA test!", "Send a message"),
            ("OBSERVE", "$force_action:observe", "Observe channel messages"),
            # Memory handlers
            ("MEMORIZE", "$force_action:memorize action_params:test_qa_node CONCEPT test_data", "Store memory"),
            ("RECALL", "$force_action:recall action_params:test_qa_node", "Recall memory"),
            ("FORGET", "$force_action:forget action_params:test_qa_node", "Forget memory"),
            # Wisdom handlers
            ("DEFERRAL", "$force_action:deferral action_params:Need guidance on test", "Request wisdom"),
            ("APPROVAL", "$force_action:approval action_params:test_approval", "Request approval"),
            # Tool/Task handlers
            ("EXECUTE", "$force_action:execute action_params:test_tool test_params", "Execute tool"),
            ("ROUTING", "$force_action:routing action_params:test_route", "Route to service"),
            ("WAITING", "$force_action:waiting action_params:5", "Wait for event"),
        ]

        for handler_name, command, description in handlers:
            self.test_handler(handler_name, command, description)
            time.sleep(0.5)  # Small delay between tests

        # Check for incidents
        print("\n" + "=" * 80)
        print("CHECKING INCIDENTS LOG")
        print("=" * 80)

        recent_errors = self.check_incidents()
        if recent_errors:
            print(f"⚠️  Found {len(recent_errors)} recent errors:")
            for error in recent_errors[-3:]:  # Show last 3
                print(f"  - {error[:150]}...")
        else:
            print("✅ No recent errors in incidents log")

        # Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)

        total = len(self.test_results)
        passed = sum(1 for r in self.test_results.values() if r["success"])

        print(f"\nResults: {passed}/{total} handlers tested successfully")
        print("\nDetails:")
        for handler, result in self.test_results.items():
            status = "✅" if result["success"] else "❌"
            audit_count = result["new_audit_entries"]
            print(f"  {status} {handler}: {audit_count} audit entries")

        # Additional validation
        print("\n" + "=" * 80)
        print("VALIDATION CHECKS")
        print("=" * 80)

        # Check telemetry
        telemetry_resp = requests.get(
            f"{BASE_URL}/v1/telemetry/unified", headers={"Authorization": f"Bearer {self.token}"}
        )
        if telemetry_resp.status_code == 200:
            data = telemetry_resp.json()
            online = data.get("services_online", 0)
            total = data.get("services_total", 0)
            print(f"✅ Services: {online}/{total} healthy")

        # Check audit trail
        all_audit = self.get_audit_log(50)
        handler_events = [e for e in all_audit if any(h.lower() in str(e).lower() for h in self.test_results.keys())]
        print(f"✅ Audit: Found {len(handler_events)} handler events in last 50 entries")

        # Final status
        print("\n" + "=" * 80)
        if passed == total:
            print("🎉 ALL HANDLERS TESTED SUCCESSFULLY!")
        elif passed >= total * 0.8:
            print(f"✅ MOST HANDLERS WORKING ({passed}/{total})")
        else:
            print(f"⚠️  SOME HANDLERS NEED ATTENTION ({passed}/{total})")
        print("=" * 80)


def main():
    """Run the handler test suite."""
    suite = HandlerTestSuite()
    suite.run_all_tests()


if __name__ == "__main__":
    main()
