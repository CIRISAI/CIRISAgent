#!/usr/bin/env python
"""Simple handler test focusing on basic functionality."""

import json
import time

import requests

BASE_URL = "http://localhost:8000"


def get_token():
    """Get auth token."""
    resp = requests.post(f"{BASE_URL}/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"})
    return resp.json()["access_token"]


def test_speak_handler(token):
    """Test SPEAK handler - the simplest one."""
    print("\n" + "=" * 60)
    print("Testing SPEAK Handler")
    print("=" * 60)

    # Send a simple speak command
    message = "$force_action:speak action_params:Testing SPEAK handler"
    print(f"Sending: {message}")

    resp = requests.post(
        f"{BASE_URL}/v1/agent/interact", headers={"Authorization": f"Bearer {token}"}, json={"message": message}
    )

    if resp.status_code == 200:
        data = resp.json()
        response = data.get("response", "")
        print(f"✅ Got response: {response[:100]}...")

        # Check if it contains our test message
        if "Testing SPEAK handler" in response:
            print("✅ SPEAK handler executed correctly!")
            return True
        else:
            print("⚠️  Response doesn't contain expected message")
            return False
    else:
        print(f"❌ Failed: {resp.status_code}")
        return False


def test_observe_handler(token):
    """Test OBSERVE handler."""
    print("\n" + "=" * 60)
    print("Testing OBSERVE Handler")
    print("=" * 60)

    message = "$force_action:observe"
    print(f"Sending: {message}")

    resp = requests.post(
        f"{BASE_URL}/v1/agent/interact", headers={"Authorization": f"Bearer {token}"}, json={"message": message}
    )

    if resp.status_code == 200:
        data = resp.json()
        response = data.get("response", "")
        print(f"✅ Got response: {response[:100]}...")

        # OBSERVE typically returns info about fetched messages
        if "observe" in response.lower() or "fetch" in response.lower() or "message" in response.lower():
            print("✅ OBSERVE handler likely executed")
            return True
        else:
            print("⚠️  Response unclear")
            return False
    else:
        print(f"❌ Failed: {resp.status_code}")
        return False


def check_incidents():
    """Check for recent errors in incidents log."""
    print("\n" + "=" * 60)
    print("Checking Incidents Log")
    print("=" * 60)

    try:
        # Use tail command to get last 20 lines
        import subprocess

        result = subprocess.run(
            ["tail", "-n", "20", "/home/emoore/TESTING/CIRISAgent/logs/incidents_latest.log"],
            capture_output=True,
            text=True,
        )

        lines = result.stdout.split("\n")
        errors = [l for l in lines if "ERROR" in l or "CRITICAL" in l]

        if errors:
            print(f"⚠️  Found {len(errors)} recent errors:")
            for error in errors[-3:]:  # Last 3 errors
                # Extract just the error message
                if "ERROR" in error:
                    parts = error.split("ERROR", 1)
                    if len(parts) > 1:
                        msg = parts[1].strip()
                        # Get handler and message
                        msg_parts = msg.split(" - ", 2)
                        if len(msg_parts) >= 3:
                            handler = msg_parts[0].strip()
                            message = msg_parts[2].strip()[:100]
                            print(f"  - {handler}: {message}...")
                        else:
                            print(f"  - {msg[:100]}...")
        else:
            print("✅ No recent errors")

    except Exception as e:
        print(f"Could not read incidents log: {e}")


def main():
    print("=" * 80)
    print("CIRIS SIMPLE HANDLER TEST")
    print("=" * 80)

    # Get token
    token = get_token()
    print(f"✅ Got auth token")

    # Test basic handlers
    speak_ok = test_speak_handler(token)
    time.sleep(1)  # Small delay

    observe_ok = test_observe_handler(token)
    time.sleep(1)

    # Check for errors
    check_incidents()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if speak_ok and observe_ok:
        print("✅ Basic handlers working!")
    else:
        print("⚠️  Some issues detected")
        print(f"  SPEAK: {'✅' if speak_ok else '❌'}")
        print(f"  OBSERVE: {'✅' if observe_ok else '❌'}")

    print("\nNote: Task completion errors in incidents log are expected")
    print("      (known issue with follow-up thought handling)")
    print("=" * 80)


if __name__ == "__main__":
    main()
