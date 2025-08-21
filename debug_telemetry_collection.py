#!/usr/bin/env python3
"""Debug script to trace telemetry collection for unhealthy services."""

import json
from typing import Any, Dict

import requests

# API configuration
API_URL = "http://localhost:8000"
USERNAME = "admin"
PASSWORD = "ciris_admin_password"


def get_auth_token() -> str:
    """Get authentication token."""
    response = requests.post(f"{API_URL}/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})
    response.raise_for_status()
    return response.json()["access_token"]


def get_service_registry_info(token: str) -> Dict[str, Any]:
    """Get service registry provider info."""
    response = requests.get(
        f"{API_URL}/v1/services/registry/provider-info", headers={"Authorization": f"Bearer {token}"}
    )
    response.raise_for_status()
    return response.json()


def get_service_status(token: str, service_name: str) -> Dict[str, Any]:
    """Get status for a specific service."""
    try:
        response = requests.get(
            f"{API_URL}/v1/services/{service_name}/status", headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def main():
    """Main investigation function."""
    # Get auth token
    print("Getting auth token...")
    token = get_auth_token()

    # Get service registry info
    print("\n=== SERVICE REGISTRY INFO ===")
    registry_info = get_service_registry_info(token)

    # Save for analysis
    with open("/tmp/registry_info.json", "w") as f:
        json.dump(registry_info, f, indent=2)
    print("Registry info saved to /tmp/registry_info.json")

    # List of unhealthy services to check
    unhealthy_services = [
        "ServiceType.CONFIG_graph",
        "ServiceType.TIME_time",
        "ServiceType.MEMORY_local_graph",
        "ServiceType.WISE_AUTHORITY_wise_authority",
        "ServiceType.TSDB_CONSOLIDATION_tsdbconsolidation_132956962453936_638544",
        "ServiceType.LLM_mock",
        "ServiceType.TOOL_api_tool",
        "ServiceType.TOOL_secrets",
        "ServiceType.COMMUNICATION_api_026080",
        "ServiceType.RUNTIME_CONTROL_api_runtime",
    ]

    # Extract service types from the names
    print("\n=== ANALYZING UNHEALTHY SERVICE NAMES ===")
    for service_name in unhealthy_services:
        # Parse the ServiceType.XXX_yyy format
        if service_name.startswith("ServiceType."):
            parts = service_name[12:].split("_", 1)  # Remove "ServiceType." prefix
            service_type = parts[0]
            provider_suffix = parts[1] if len(parts) > 1 else ""
            print(f"\n{service_name}:")
            print(f"  Type: {service_type}")
            print(f"  Provider/Suffix: {provider_suffix}")

            # Look for this in registry
            services = registry_info.get("services", {})
            if service_type in services:
                providers = services[service_type]
                print(f"  Found in registry: {len(providers)} provider(s)")
                for provider in providers:
                    print(f"    - {provider.get('name', 'Unknown')}")
                    print(f"      Priority: {provider.get('priority', 'N/A')}")
                    print(f"      Metadata: {provider.get('metadata', {})}")
            else:
                print(f"  NOT found in registry under type '{service_type}'")

    # Check how services are named in telemetry
    print("\n=== CHECKING SERVICE NAMING PATTERN ===")

    # These services SHOULD be working - let's check a known healthy one
    healthy_test_services = ["memory", "config", "telemetry", "audit"]

    for service_name in healthy_test_services:
        print(f"\nChecking {service_name}:")
        status = get_service_status(token, service_name)
        if "error" not in status:
            print(f"  Status retrieved successfully")
            print(f"  Service name in response: {status.get('service_name', 'N/A')}")
            print(f"  Healthy: {status.get('is_healthy', False)}")
            print(f"  Uptime: {status.get('uptime_seconds', 0)}")
        else:
            print(f"  Error: {status['error']}")


if __name__ == "__main__":
    main()
