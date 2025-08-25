#!/usr/bin/env python3
"""
Check which services are unhealthy
"""

import asyncio
import json

import httpx


async def check_unhealthy_services():
    """Check which services are unhealthy"""

    base_url = "http://localhost:8005"

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # Login
        response = await client.post("/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"})
        auth_data = response.json()
        token = auth_data["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        print("=" * 80)
        print("CHECKING UNHEALTHY SERVICES")
        print("=" * 80)

        # Get unified telemetry
        response = await client.get("/v1/telemetry/unified?view=detailed")
        telemetry = response.json()

        print(f"\nServices: {telemetry.get('services_online', 0)}/{telemetry.get('services_total', 0)} online")

        # Check each service
        services = telemetry.get("services", {})

        unhealthy = []
        healthy = []

        for service_name, service_data in sorted(services.items()):
            is_healthy = service_data.get("healthy", False)
            if is_healthy:
                healthy.append(service_name)
            else:
                unhealthy.append(service_name)

        print(f"\n✅ HEALTHY SERVICES ({len(healthy)}):")
        for svc in healthy:
            print(f"   - {svc}")

        print(f"\n❌ UNHEALTHY SERVICES ({len(unhealthy)}):")
        for svc in unhealthy:
            service_data = services[svc]
            print(f"   - {svc}")
            print(f"     Status: {service_data.get('status', 'unknown')}")
            print(f"     Uptime: {service_data.get('uptime_seconds', 0):.0f}s")
            print(f"     Errors: {service_data.get('error_count', 0)}")
            if service_data.get("last_error"):
                print(f"     Last Error: {service_data.get('last_error')}")

        # Get more details from service registry
        print("\n" + "=" * 80)
        print("SERVICE REGISTRY DETAILS")
        print("=" * 80)

        response = await client.get("/v1/system/services")
        if response.status_code == 200:
            registry = response.json()
            services_list = registry.get("services", [])

            print(f"\nTotal registered services: {len(services_list)}")

            # Group by type
            by_type = {}
            for svc in services_list:
                svc_type = svc.get("type", "unknown")
                if svc_type not in by_type:
                    by_type[svc_type] = []
                by_type[svc_type].append(svc.get("name", "unnamed"))

            print("\nServices by type:")
            for svc_type, names in sorted(by_type.items()):
                print(f"  {svc_type}: {len(names)} services")
                for name in sorted(names):
                    print(f"    - {name}")


if __name__ == "__main__":
    asyncio.run(check_unhealthy_services())
