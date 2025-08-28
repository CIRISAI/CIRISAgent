#!/usr/bin/env python3
import sys

import requests

# Login
login_resp = requests.post(
    "http://localhost:8080/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
)
if login_resp.status_code != 200:
    print(f"Login failed: {login_resp.text}")
    sys.exit(1)

token = login_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get adapters
resp = requests.get("http://localhost:8080/v1/system/adapters", headers=headers)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    import json

    data = resp.json()
    print(json.dumps(data, indent=2))
else:
    print(f"Error: {resp.text}")
