#!/usr/bin/env python3
"""
Register Discord adapter using values from .env file.

This script:
1. Reads Discord configuration from .env
2. Authenticates with the CIRIS API
3. Registers a Discord adapter with the bot token and channel IDs
"""

import os
import sys
from pathlib import Path
from typing import Dict

import requests


def load_env_file(env_path: str = ".env") -> Dict[str, str]:
    """Load environment variables from .env file."""
    env_vars = {}

    if not Path(env_path).exists():
        print(f"Error: {env_path} file not found")
        sys.exit(1)

    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                # Remove 'export ' prefix if present
                if line.startswith("export "):
                    line = line[7:]

                key, value = line.split("=", 1)
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                env_vars[key.strip()] = value.strip()

    return env_vars


def register_discord_adapter(
    api_url: str = "http://localhost:8080", username: str = "admin", password: str = "ciris_admin_password"
) -> None:
    """Register Discord adapter via CIRIS API."""

    # Load environment variables
    env_vars = load_env_file()

    # Check required Discord variables
    required_vars = ["DISCORD_BOT_TOKEN"]
    missing_vars = [var for var in required_vars if var not in env_vars]

    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)

    # Extract Discord configuration
    bot_token = env_vars["DISCORD_BOT_TOKEN"]
    home_channel_id = env_vars.get("DISCORD_CHANNEL_ID")
    deferral_channel_id = env_vars.get("DISCORD_DEFERRAL_CHANNEL_ID")
    wa_user_id = env_vars.get("WA_USER_ID")

    # Build monitored channels list
    monitored_channels = []
    if home_channel_id:
        monitored_channels.append(home_channel_id)

    # Build admin users list
    admin_users = []
    if wa_user_id:
        admin_users.append(wa_user_id)

    print("Discord Configuration:")
    print(f"  Bot Token: {'*' * 10}{bot_token[-10:] if len(bot_token) > 10 else '***'}")
    print(f"  Home Channel: {home_channel_id}")
    print(f"  Deferral Channel: {deferral_channel_id}")
    print(f"  Monitored Channels: {monitored_channels}")
    print(f"  Admin Users: {admin_users}")
    print()

    # Step 1: Login to get access token
    print(f"1. Logging in to {api_url}...")
    login_response = requests.post(
        f"{api_url}/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Content-Type": "application/json"},
    )

    if login_response.status_code != 200:
        print(f"Error: Login failed with status {login_response.status_code}")
        print(f"Response: {login_response.text}")
        sys.exit(1)

    token = login_response.json()["access_token"]
    print(f"   ✓ Login successful. Token: {token[:20]}...")
    print()

    # Step 2: Check if Discord adapter already exists
    print("2. Checking existing adapters...")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    list_response = requests.get(f"{api_url}/v1/system/adapters", headers=headers)

    if list_response.status_code == 200:
        adapters = list_response.json()["data"]["adapters"]
        discord_adapters = [a for a in adapters if a["adapter_type"] == "discord"]

        if discord_adapters:
            print(f"   ⚠ Found {len(discord_adapters)} existing Discord adapter(s):")
            for adapter in discord_adapters:
                print(f"     - {adapter['adapter_id']} (running: {adapter['is_running']})")

            response = input("\n   Continue and register another Discord adapter? (y/N): ")
            if response.lower() != "y":
                print("   Aborted.")
                sys.exit(0)
    print()

    # Step 3: Register Discord adapter
    print("3. Registering Discord adapter...")

    config = {
        "config": {
            "bot_token": bot_token,
            "home_channel_id": home_channel_id,
            "deferral_channel_id": deferral_channel_id,
            "monitored_channel_ids": monitored_channels,
            "admin_user_ids": admin_users,
            "enabled": True,
            "respond_to_mentions": True,
            "respond_to_dms": True,
            "enable_threads": True,
            "max_message_length": 2000,
            "message_rate_limit": 1.0,
            "max_messages_per_minute": 30,
        }
    }

    register_response = requests.post(f"{api_url}/v1/system/adapters/discord", json=config, headers=headers)

    if register_response.status_code == 200:
        result = register_response.json()["data"]
        print("   ✓ Discord adapter registered successfully!")
        print(f"     Adapter ID: {result['adapter_id']}")
        print(f"     Type: {result['adapter_type']}")
        print(f"     Message: {result['message']}")
    else:
        print(f"   ✗ Registration failed with status {register_response.status_code}")
        print(f"     Response: {register_response.text}")
        sys.exit(1)
    print()

    # Step 4: Verify adapter is running
    print("4. Verifying adapter status...")
    adapter_id = result["adapter_id"]

    # Wait a moment for the adapter to start
    import time

    time.sleep(2)

    status_response = requests.get(f"{api_url}/v1/system/adapters", headers=headers)

    if status_response.status_code == 200:
        adapters = status_response.json()["data"]["adapters"]
        our_adapter = next((a for a in adapters if a["adapter_id"] == adapter_id), None)

        if our_adapter:
            print("   ✓ Adapter found in system")
            print(f"     Running: {our_adapter['is_running']}")
            print(f"     Services: {', '.join(our_adapter['services_registered'])}")
            print(f"     Tools: {len(our_adapter.get('tools', []))} available")
        else:
            print(f"   ⚠ Adapter {adapter_id} not found in adapter list")

    print("\n✅ Discord adapter registration complete!")
    print("   The bot should now be online in Discord.")
    print("   Check the logs for connection status: docker logs ciris")


if __name__ == "__main__":
    # Parse command line arguments
    api_url = os.environ.get("CIRIS_API_URL", "http://localhost:8080")
    username = os.environ.get("CIRIS_API_USER", "admin")
    password = os.environ.get("CIRIS_API_PASSWORD", "ciris_admin_password")

    if len(sys.argv) > 1:
        api_url = sys.argv[1]
    if len(sys.argv) > 2:
        username = sys.argv[2]
    if len(sys.argv) > 3:
        password = sys.argv[3]

    print("CIRIS Discord Adapter Registration")
    print("==================================")
    print(f"API URL: {api_url}")
    print(f"Username: {username}")
    print()

    try:
        register_discord_adapter(api_url, username, password)
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
