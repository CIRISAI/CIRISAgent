#!/usr/bin/env python
"""
Simple handler test for quick validation of CIRIS handlers.

A lightweight test that validates basic handler functionality.
"""

import json
import sys
import time

import requests

BASE_URL = "http://localhost:8000"


def get_token():
    """Get authentication token."""
    response = requests.post(
        f"{BASE_URL}/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
    )
    if response.status_code != 200:
        print(f"❌ Failed to get token: {response.status_code}")
        sys.exit(1)
    return response.json()["access_token"]


def test_handler(token, handler_name, command):
    """Test a single handler."""
    print(f"\nTesting {handler_name}...")
    print(f"Command: {command}")

    response = requests.post(
        f"{BASE_URL}/v1/agent/interact", headers={"Authorization": f"Bearer {token}"}, json={"message": command}
    )

    if response.status_code != 200:
        print(f"❌ {handler_name} failed: {response.status_code}")
        return False

    data = response.json()
    if "response" in data:
        print(f"✅ {handler_name} executed")
        print(f"   Response: {data['response'][:100]}...")
        return True
    else:
        print(f"❌ {handler_name} no response")
        return False


def main():
    """Run simple handler tests."""
    print("=" * 60)
    print("CIRIS SIMPLE HANDLER TEST")
    print("=" * 60)

    # Get token
    print("\nGetting auth token...")
    token = get_token()
    print("✅ Authenticated")

    # Test basic handlers
    handlers = [
        ("SPEAK", "$SPEAK Test message from simple QA"),
        ("OBSERVE", "$OBSERVE"),
        ("MEMORIZE", "$MEMORIZE simple_test CONCEPT test_data"),
        ("RECALL", "$RECALL simple_test"),
        ("FORGET", "$FORGET simple_test"),
    ]

    results = []
    for handler_name, command in handlers:
        success = test_handler(token, handler_name, command)
        results.append((handler_name, success))
        time.sleep(0.5)  # Small delay between tests

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    print(f"\nResults: {passed}/{total} handlers tested successfully")
    for handler_name, success in results:
        status = "✅" if success else "❌"
        print(f"  {status} {handler_name}")

    if passed == total:
        print("\n🎉 ALL HANDLERS WORKING!")
    else:
        print(f"\n⚠️  {total - passed} handlers failed")

    print("=" * 60)


if __name__ == "__main__":
    main()
