#!/usr/bin/env python3
import requests

# Get token
response = requests.post(
    "http://localhost:8000/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
)
token = response.json()["access_token"]
print(f"Got token: {token[:20]}...")

# Test SSE endpoint
print("\nTesting SSE endpoint...")
try:
    response = requests.get(
        "http://localhost:8000/v1/system/runtime/reasoning-stream",
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=5,
    )
    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")

    if response.status_code == 200:
        print("\n✅ SSE endpoint is working!")
        print("First few lines:")
        for i, line in enumerate(response.iter_lines()):
            if i >= 5:
                break
            print(line.decode() if isinstance(line, bytes) else line)
    else:
        print(f"\n❌ Error: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"❌ Exception: {e}")
