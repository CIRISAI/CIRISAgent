#!/usr/bin/env python3
"""
Test consent flow - interaction, then upgrade
"""

import asyncio
from datetime import datetime

from ciris_sdk.client import CIRISClient


async def test_consent_flow():
    """Test complete consent flow."""

    print("=" * 60)
    print("CONSENT FLOW TEST")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    async with CIRISClient(base_url="http://localhost:9000") as client:
        try:
            # 1. Login
            await client.login(username="admin", password="ciris_admin_password")
            print("\n1. AUTHENTICATION")
            print("   ✓ Logged in successfully")

            # 2. Check initial consent status
            print("\n2. INITIAL CONSENT STATUS")
            try:
                active = await client.consent.get_active()
                print(f"   Active consents before interaction: {len(active)}")
                for consent in active:
                    print(f"   - {consent}")
            except Exception as e:
                print(f"   No initial consents: {e}")

            # 3. Interact with agent (should create default consent)
            print("\n3. AGENT INTERACTION")
            response = await client.interact("Hello, I need help with Python")
            print(f"   ✓ Interaction successful")
            print(f"   Response: {response.response[:100]}...")

            # 4. Check consent after interaction
            print("\n4. CONSENT AFTER INTERACTION")
            try:
                active = await client.consent.get_active()
                print(f"   Active consents after interaction: {len(active)}")
                for consent in active:
                    print(f"   - Status: {consent.status if hasattr(consent, 'status') else 'unknown'}")
                    print(f"   - Scope: {consent.scope if hasattr(consent, 'scope') else 'unknown'}")
                    print(f"   - User: {consent.user_id if hasattr(consent, 'user_id') else 'unknown'}")
            except Exception as e:
                print(f"   Error checking consent: {e}")

            # 5. Try to grant explicit consent
            print("\n5. GRANT EXPLICIT CONSENT")
            try:
                from ciris_sdk.resources.consent import ConsentScope, ConsentStatus

                # Try granting consent
                grant_result = await client.consent.grant(
                    user_id="admin", scope=ConsentScope.FULL, purpose="Full access for testing", duration_hours=24
                )
                print(f"   ✓ Consent granted: {grant_result}")
            except Exception as e:
                print(f"   Error granting consent: {e}")

            # 6. Check consent status again
            print("\n6. FINAL CONSENT STATUS")
            try:
                # Query with different parameters
                from ciris_sdk.resources.consent import ConsentStatus

                # Query all consents
                all_query = await client.consent.query()
                print(f"   All consents: {len(all_query.consents)}")

                # Query active only
                active_query = await client.consent.query(status=ConsentStatus.ACTIVE)
                print(f"   Active consents: {len(active_query.consents)}")

                for consent in active_query.consents:
                    print(f"   - ID: {consent.id}")
                    print(f"   - Status: {consent.status}")
                    print(f"   - Scope: {consent.scope}")
                    print(f"   - Purpose: {consent.purpose}")

            except Exception as e:
                print(f"   Error querying consent: {e}")

            # 7. Test consent revocation
            print("\n7. CONSENT REVOCATION TEST")
            try:
                revoke_result = await client.consent.revoke(user_id="admin")
                print(f"   ✓ Consent revoked: {revoke_result}")

                # Check after revocation
                active = await client.consent.get_active()
                print(f"   Active consents after revocation: {len(active)}")
            except Exception as e:
                print(f"   Error revoking consent: {e}")

            print("\n" + "=" * 60)
            print("CONSENT FLOW TEST COMPLETED")
            print("=" * 60)

        except Exception as e:
            print(f"\n❌ Unexpected Error: {e}")
            import traceback

            traceback.print_exc()
        finally:
            try:
                await client.logout()
                print("\n✓ Logout successful")
            except:
                pass


if __name__ == "__main__":
    asyncio.run(test_consent_flow())
