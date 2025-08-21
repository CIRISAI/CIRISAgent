#!/usr/bin/env python3
"""Investigation script for the 10 unhealthy services in telemetry."""

import json
from datetime import datetime
from typing import Any, Dict, List

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


def get_telemetry_unified(token: str) -> Dict[str, Any]:
    """Get unified telemetry data."""
    response = requests.get(f"{API_URL}/v1/telemetry/unified", headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    return response.json()


def analyze_unhealthy_services(telemetry: Dict[str, Any]) -> None:
    """Analyze unhealthy services from telemetry data."""
    services = telemetry.get("services", {})

    # Find unhealthy services
    unhealthy = []
    healthy = []

    for service_name, service_data in services.items():
        if not service_data.get("healthy", False):
            unhealthy.append((service_name, service_data))
        else:
            healthy.append((service_name, service_data))

    print(f"=== TELEMETRY ANALYSIS ===")
    print(f"Total services: {len(services)}")
    print(f"Healthy services: {len(healthy)}")
    print(f"Unhealthy services: {len(unhealthy)}")
    print()

    # List unhealthy services with details
    print("=== UNHEALTHY SERVICES ===")
    for service_name, service_data in unhealthy:
        print(f"\n{service_name}:")
        print(f"  Healthy: {service_data.get('healthy', False)}")
        print(f"  Uptime: {service_data.get('uptime_seconds', 0)}")
        print(f"  Last Error: {service_data.get('last_error', 'None')}")
        print(f"  Metrics: {json.dumps(service_data.get('metrics', {}), indent=4)}")

    # Check for patterns
    print("\n=== PATTERN ANALYSIS ===")

    # Group by service type
    service_types = {}
    for service_name, _ in unhealthy:
        # Extract service type from name (e.g., ServiceType.CONFIG_graph -> graph service)
        if "graph" in service_name.lower():
            service_type = "graph"
        elif "api" in service_name.lower():
            service_type = "api"
        elif "mock" in service_name.lower():
            service_type = "mock"
        elif "tool" in service_name.lower():
            service_type = "tool"
        elif "time" in service_name.lower():
            service_type = "infrastructure"
        elif "wise" in service_name.lower():
            service_type = "governance"
        else:
            service_type = "other"

        if service_type not in service_types:
            service_types[service_type] = []
        service_types[service_type].append(service_name)

    print("Unhealthy services by type:")
    for service_type, names in service_types.items():
        print(f"  {service_type}: {len(names)} services")
        for name in names:
            print(f"    - {name}")

    # List some healthy services for comparison
    print("\n=== SAMPLE HEALTHY SERVICES (first 5) ===")
    for service_name, service_data in healthy[:5]:
        print(f"\n{service_name}:")
        print(f"  Uptime: {service_data.get('uptime_seconds', 0)}")
        print(f"  Has metrics: {bool(service_data.get('metrics', {}))}")


def main():
    """Main investigation function."""
    try:
        # Get auth token
        print("Getting auth token...")
        token = get_auth_token()

        # Get telemetry data
        print("Fetching telemetry data...")
        telemetry = get_telemetry_unified(token)

        # Save raw data for analysis
        with open("/tmp/telemetry_investigation.json", "w") as f:
            json.dump(telemetry, f, indent=2)
        print("Raw telemetry saved to /tmp/telemetry_investigation.json")

        # Analyze unhealthy services
        analyze_unhealthy_services(telemetry)

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
