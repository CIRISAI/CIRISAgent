#!/usr/bin/env python3
"""
Debug consent flow to understand user creation
"""

import asyncio
from datetime import datetime

import httpx


async def debug_consent():
    """Debug what user gets created."""

    print("=" * 60)
    print("CONSENT USER DEBUG")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # 1. Login
        login_resp = await client.post(
            "http://localhost:9000/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"}
        )
        token = login_resp.json()["access_token"]
        user_id = login_resp.json().get("user", {}).get("wa_id", "unknown")
        headers = {"Authorization": f"Bearer {token}"}

        print(f"\n1. LOGIN INFO")
        print(f"   User ID from login: {user_id}")
        print(f"   Token prefix: {token[:30]}...")

        # 2. Check consent status (should create TEMPORARY)
        print(f"\n2. CONSENT STATUS ENDPOINT")
        status_resp = await client.get("http://localhost:9000/v1/consent/status", headers=headers)
        print(f"   Status Code: {status_resp.status_code}")
        if status_resp.status_code == 200:
            status_data = status_resp.json()
            print(f"   Response: {status_data}")

        # 3. Query consent to see what was created
        print(f"\n3. CONSENT QUERY ENDPOINT")
        query_resp = await client.get("http://localhost:9000/v1/consent/query?status=ACTIVE", headers=headers)
        print(f"   Status Code: {query_resp.status_code}")
        if query_resp.status_code == 200:
            query_data = query_resp.json()
            print(f"   Total consents: {query_data.get('total', 0)}")
            for consent in query_data.get("consents", []):
                print(f"   - User ID: {consent.get('user_id')}")
                print(f"   - Status: {consent.get('status')}")
                print(f"   - Scope: {consent.get('scope')}")

        # 4. Check agent status to see user context
        print(f"\n4. AGENT STATUS (to check user context)")
        agent_resp = await client.get("http://localhost:9000/v1/agent/status", headers=headers)
        if agent_resp.status_code == 200:
            agent_data = agent_resp.json()
            print(f"   Agent ID: {agent_data.get('agent_id')}")
            print(f"   Messages processed: {agent_data.get('messages_processed')}")

        print("\n" + "=" * 60)
        print("ANALYSIS:")
        print(f"- User authenticates as: wa-system-admin (based on code)")
        print(f"- This is an ADMIN role user")
        print(f"- Consent should be created for wa-system-admin")
        print(f"- Channel would be: api_wa-system-admin")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(debug_consent())
