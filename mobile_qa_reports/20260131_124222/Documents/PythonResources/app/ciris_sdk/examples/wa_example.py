"""Example usage of the Wise Authority SDK client."""

import asyncio

from ciris_sdk import CIRISClient


async def main() -> None:
    """Demonstrate WA client functionality."""

    # Initialize client
    async with CIRISClient(base_url="http://localhost:8080") as client:

        # 1. Get all pending deferrals
        print("=== Getting Pending Deferrals ===")
        pending = await client.wa.get_pending_deferrals()
        print(f"Found {len(pending)} pending deferrals")

        for deferral in pending:
            print(f"- ID: {deferral['id']}")
            print(f"  Reason: {deferral['reason']}")
            print(f"  Created: {deferral['created_at']}")

        # 2. Resolve a deferral with guidance
        if pending:
            deferral_id = pending[0]["id"]
            print(f"\n=== Resolving Deferral {deferral_id} ===")

            # Approve with guidance
            result = await client.wa.approve_deferral(
                deferral_id=deferral_id,
                guidance="Please proceed with the request, but ensure to validate all inputs and maintain user privacy.",
            )
            print(f"Resolution: {result['resolution']}")
            print(f"Resolved at: {result['resolved_at']}")

        # 3. Get current permissions
        print("\n=== Getting Current Permissions ===")
        permissions = await client.wa.get_permissions()
        for perm in permissions.get("permissions", []):
            print(f"- Resource: {perm['resource_type']}")
            print(f"  Permission: {perm['permission_type']}")
            print(f"  Granted by: {perm['granted_by']}")

        # 4. Get deferrals with filtering
        print("\n=== Getting Resolved Deferrals ===")
        resolved = await client.wa.get_deferrals(status="resolved", limit=5)
        print(f"Found {resolved['total']} total resolved deferrals")
        print(f"Showing {len(resolved['deferrals'])} deferrals")

        # 5. Example of different resolution types
        print("\n=== Resolution Examples ===")

        # Get another pending deferral
        pending = await client.wa.get_pending_deferrals()
        if len(pending) > 1:
            # Reject example
            await client.wa.reject_deferral(
                deferral_id=pending[1]["id"], reasoning="This action violates our content policy and could harm users."
            )

        if len(pending) > 2:
            # Modify example
            await client.wa.modify_deferral(
                deferral_id=pending[2]["id"],
                guidance="Instead of the requested action, please provide a helpful explanation of why this cannot be done.",
                reasoning="The original request needs modification to align with safety guidelines.",
            )


if __name__ == "__main__":
    asyncio.run(main())
