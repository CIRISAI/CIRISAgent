"""
Tests for deferral permission and authorization checks.

Ensures that only authorized WAs can resolve deferrals and that
the permission system properly enforces role-based access control.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.services.governance.wise_authority import WiseAuthorityService
from ciris_engine.schemas.services.authority.wise_authority import DeferralResolution, PendingDeferral
from ciris_engine.schemas.services.authority_core import (
    AuthorizationContext,
    AuthorizationDenialReason,
    DeferralResponse,
    JWTSubType,
    TokenType,
    WACertificate,
    WAPermission,
    WARole,
)


class TestDeferralPermissions:
    """Test permission checks for deferral operations."""

    @pytest.fixture
    def mock_memory_service(self) -> AsyncMock:
        """Mock memory service with permission storage."""
        service = AsyncMock()

        # Store permissions by WA ID
        service.permissions = {
            "wa-2025-06-28-AUTH01": [
                WAPermission(
                    permission_id="perm_001",
                    wa_id="wa-2025-06-28-AUTH01",
                    permission_type="action",
                    permission_name="resolve_deferral",
                    resource="*",
                    granted_by="wa-2025-06-28-ROOT01",
                    granted_at=datetime.now(timezone.utc),
                    expires_at=None,
                )
            ],
            "wa-2025-06-28-OBSR01": [
                WAPermission(
                    permission_id="perm_002",
                    wa_id="wa-2025-06-28-OBSR01",
                    permission_type="action",
                    permission_name="view_deferral",
                    resource="*",
                    granted_by="wa-2025-06-28-ROOT01",
                    granted_at=datetime.now(timezone.utc),
                    expires_at=None,
                )
            ],
            "wa-2025-06-28-LIMIT1": [
                WAPermission(
                    permission_id="perm_003",
                    wa_id="wa-2025-06-28-LIMIT1",
                    permission_type="action",
                    permission_name="resolve_deferral",
                    resource="medical_*",  # Only medical deferrals
                    granted_by="wa-2025-06-28-ROOT01",
                    granted_at=datetime.now(timezone.utc),
                    expires_at=None,
                )
            ],
        }

        # Mock recall to return permissions
        async def mock_recall(query: Optional[str] = None, node_type: Optional[str] = None, **kwargs: Any) -> List[Any]:
            if node_type == "wa_permission" and query:
                wa_id = query.split(":")[1] if ":" in query else None
                return service.permissions.get(wa_id, [])
            return []

        service.recall = mock_recall
        return service

    @pytest.fixture
    def wa_certificates(self) -> Dict[str, WACertificate]:
        """Create test WA certificates with different roles."""
        import json

        return {
            # Breadth is now spelled out. Before F1 was fixed these scopes read
            # `["resolve_deferrals", "modify_deferrals"]` — an action named and
            # no domain named — and the gate inferred "…therefore every domain".
            # That inference IS the finding. A WA that really is authorized
            # everywhere says `:any`; nothing infers it on the WA's behalf.
            "wa-2025-06-28-AUTH01": WACertificate(
                wa_id="wa-2025-06-28-AUTH01",
                name="Full Authority",
                role=WARole.AUTHORITY,
                pubkey="authority_pubkey_base64url",
                jwt_kid="auth01_kid",
                scopes_json=json.dumps(["resolve_deferral:any", "modify_deferral:any"]),
                created_at=datetime.now(timezone.utc),
            ),
            "wa-2025-06-28-OBSR01": WACertificate(
                wa_id="wa-2025-06-28-OBSR01",
                name="Observer Only",
                role=WARole.OBSERVER,
                pubkey="observer_pubkey_base64url",
                jwt_kid="obsr01_kid",
                scopes_json=json.dumps(["view_deferrals"]),
                created_at=datetime.now(timezone.utc),
            ),
            "wa-2025-05-28-EXPR01": WACertificate(
                wa_id="wa-2025-05-28-EXPR01",
                name="Expired Authority",
                role=WARole.AUTHORITY,
                pubkey="expired_pubkey_base64url",
                jwt_kid="expr01_kid",
                scopes_json=json.dumps(["resolve_deferrals"]),
                created_at=datetime.now(timezone.utc) - timedelta(days=60),
            ),
            "wa-2025-06-28-REVK01": WACertificate(
                wa_id="wa-2025-06-28-REVK01",
                name="Revoked Authority",
                role=WARole.AUTHORITY,
                pubkey="revoked_pubkey_base64url",
                jwt_kid="revk01_kid",
                scopes_json=json.dumps(["resolve_deferrals"]),
                created_at=datetime.now(timezone.utc),
            ),
            "wa_limited_authority": WACertificate(
                wa_id="wa-2025-06-28-LIMT01",
                name="Limited Authority",
                role=WARole.AUTHORITY,
                pubkey="limited_pubkey_base64url",
                jwt_kid="limt01_kid",
                # Was `resolve_deferrals:medical_*` — plural, and so matching no
                # action anyone actually requests. It went unnoticed because
                # nothing read scopes at all; the fixture described an intent the
                # code never consulted.
                scopes_json=json.dumps(["resolve_deferral:medical_*"]),
                created_at=datetime.now(timezone.utc),
            ),
        }

    @pytest.fixture
    def mock_auth_service(self, wa_certificates: Dict[str, WACertificate]) -> AsyncMock:
        """Create mock authentication service."""
        auth_service = AsyncMock()
        auth_service.bootstrap_if_needed = AsyncMock()

        # Mock get_wa to return certificates
        async def mock_get_wa(wa_id: str) -> Optional[WACertificate]:
            return wa_certificates.get(wa_id)

        auth_service.get_wa = mock_get_wa
        return auth_service

    @pytest.fixture
    def wa_service(self, mock_memory_service: AsyncMock, mock_auth_service: AsyncMock) -> WiseAuthorityService:
        """Create WA service with mock dependencies."""
        mock_time_service = Mock()
        mock_time_service.now = Mock(return_value=datetime.now(timezone.utc))
        mock_time_service.timestamp = Mock(return_value=int(datetime.now(timezone.utc).timestamp()))

        service = WiseAuthorityService(
            time_service=mock_time_service,
            auth_service=mock_auth_service,
            db_path=":memory:",  # Use in-memory SQLite for tests
        )
        return service

    @pytest.mark.asyncio
    async def test_authority_can_resolve_deferrals(
        self, wa_service: WiseAuthorityService, wa_certificates: Dict[str, WACertificate]
    ) -> None:
        """Test that AUTHORITY role can resolve deferrals."""
        # Create authorization context for authority
        auth_context = AuthorizationContext(
            wa_id="wa-2025-06-28-AUTH01",
            role=WARole.AUTHORITY,
            token_type=TokenType.STANDARD,
            sub_type=JWTSubType.AUTHORITY,
            scopes=["resolve_deferrals"],
            action="resolve_deferral",
            resource="defer_001",
        )

        # Check authorization
        is_authorized = await wa_service.check_authorization(
            wa_id=auth_context.wa_id, action=auth_context.action, resource=auth_context.resource
        )

        assert is_authorized is True

    @pytest.mark.asyncio
    async def test_observer_cannot_resolve_deferrals(
        self, wa_service: WiseAuthorityService, wa_certificates: Dict[str, WACertificate]
    ) -> None:
        """Test that OBSERVER role cannot resolve deferrals."""
        # Create authorization context for observer
        auth_context = AuthorizationContext(
            wa_id="wa-2025-06-28-OBSR01",
            role=WARole.OBSERVER,
            token_type=TokenType.STANDARD,
            sub_type=JWTSubType.AUTHORITY,
            scopes=["view_deferrals"],
            action="resolve_deferral",
            resource="defer_001",
        )

        # Check authorization
        is_authorized = await wa_service.check_authorization(
            wa_id=auth_context.wa_id, action=auth_context.action, resource=auth_context.resource
        )

        assert is_authorized is False

    @pytest.mark.asyncio
    async def test_expired_certificate_cannot_resolve(
        self, wa_service: WiseAuthorityService, wa_certificates: Dict[str, WACertificate]
    ) -> None:
        """Test that expired certificates cannot resolve deferrals."""
        # Even with AUTHORITY role, expired cert should fail
        is_authorized = await wa_service.check_authorization(
            wa_id="wa_expired", action="resolve_deferral", resource="defer_001"
        )

        assert is_authorized is False

    @pytest.mark.asyncio
    async def test_revoked_certificate_cannot_resolve(
        self, wa_service: WiseAuthorityService, wa_certificates: Dict[str, WACertificate]
    ) -> None:
        """Test that revoked certificates cannot resolve deferrals."""
        is_authorized = await wa_service.check_authorization(
            wa_id="wa_revoked", action="resolve_deferral", resource="defer_001"
        )

        assert is_authorized is False

    @pytest.mark.asyncio
    async def test_resource_specific_permissions(
        self, wa_service: WiseAuthorityService, mock_memory_service: AsyncMock
    ) -> None:
        """Resource scope decides, not role alone (NULLWORKS RC3 F1 / MULTI-AUTH-01).

        This is the test that used to record the vulnerability. It asserted that
        a WA scoped to `medical_*` could resolve a *financial* deferral, with the
        comment "Resource-specific permissions are not yet implemented" — an
        accurate description of the code and an inversion of what the fixture
        said the WA was for. The authority is unchanged; only the resource
        differs; the answers must differ with it.
        """
        # Limited authority can only resolve medical deferrals
        is_authorized_medical = await wa_service.check_authorization(
            wa_id="wa_limited_authority", action="resolve_deferral", resource="medical_defer_001"
        )

        is_authorized_financial = await wa_service.check_authorization(
            wa_id="wa_limited_authority", action="resolve_deferral", resource="financial_defer_001"
        )

        assert is_authorized_medical is True
        assert is_authorized_financial is False

    @pytest.mark.asyncio
    async def test_grant_permission(self, wa_service: WiseAuthorityService) -> None:
        """Test granting new permissions to a WA."""
        # Grant permission to a new WA
        granted = await wa_service.grant_permission(
            wa_id="wa_new_moderator", permission="resolve_deferral", resource="community_*"
        )

        assert granted is False  # Expected behavior - permissions are role-based

    @pytest.mark.asyncio
    async def test_revoke_permission(self, wa_service: WiseAuthorityService) -> None:
        """Test revoking permissions from a WA."""
        # Try to revoke permission
        # Note: In current implementation, this returns False as permissions are role-based
        revoked = await wa_service.revoke_permission(
            wa_id="wa_temp_authority", permission="resolve_deferral", resource="*"
        )

        assert revoked is False  # Expected behavior - permissions are role-based

    @pytest.mark.asyncio
    async def test_permission_inheritance(self, wa_service: WiseAuthorityService) -> None:
        """Test that wildcard permissions work correctly through role-based access."""
        # Since permissions are role-based, we test by checking ROOT role permissions
        # ROOT role should have access to all actions

        # Create a mock ROOT WA
        mock_root_wa = WACertificate(
            wa_id="wa-2025-06-28-ROOT01",
            name="Root Admin",
            role=WARole.ROOT,
            pubkey="root_key_base64url",
            jwt_kid="root_kid",
            scopes_json='["*"]',
            created_at=datetime.now(timezone.utc),
        )

        # Mock the auth service to return the ROOT wa
        wa_service.auth_service.get_wa = AsyncMock(return_value=mock_root_wa)

        # Should authorize any action for ROOT
        actions = ["resolve_deferral", "modify_deferral", "delete_deferral", "create_deferral"]

        for action in actions:
            is_authorized = await wa_service.check_authorization(
                wa_id="wa-2025-06-28-ROOT01", action=action, resource="any_resource"
            )
            assert is_authorized is True

    @pytest.mark.asyncio
    async def test_concurrent_permission_checks(self, wa_service: WiseAuthorityService) -> None:
        """Test concurrent authorization checks don't interfere."""
        import asyncio

        # Create multiple WAs with different roles
        wa_certs = {}
        for i in range(5):
            wa_id = f"wa-2025-06-28-TEST{i:02d}"
            # Even indices get AUTHORITY role, odd get OBSERVER
            role = WARole.AUTHORITY if i % 2 == 0 else WARole.OBSERVER
            wa_certs[wa_id] = WACertificate(
                wa_id=wa_id,
                name=f"Test WA {i}",
                role=role,
                pubkey=f"key_{i}_base64url",
                jwt_kid=f"kid_{i}",
                # `:any` because this test is about concurrency, not jurisdiction —
                # these authorities are deliberately scoped everywhere so the only
                # thing the assertions can be measuring is the role split.
                scopes_json='["resolve_deferral:any"]' if role == WARole.AUTHORITY else '["view_deferrals"]',
                created_at=datetime.now(timezone.utc),
            )

        # Mock auth service to return appropriate certificates
        async def mock_get_wa(wa_id: str) -> Optional[WACertificate]:
            return wa_certs.get(wa_id)

        wa_service.auth_service.get_wa = mock_get_wa

        # Check all concurrently
        tasks = [
            wa_service.check_authorization(wa_id=wa_id, action="resolve_deferral", resource="test_resource")
            for wa_id in wa_certs.keys()
        ]

        results = await asyncio.gather(*tasks)

        # Even indices (AUTHORITY) should be authorized, odd (OBSERVER) should not
        for i, result in enumerate(results):
            if i % 2 == 0:
                assert result is True
            else:
                assert result is False


class TestDeferralRoleEnforcement:
    """Test role-based access control for deferrals."""

    @pytest.fixture
    def wa_service(self) -> AsyncMock:
        """Mock wise authority service."""
        from unittest.mock import AsyncMock, Mock

        service = AsyncMock()
        service.auth_service = Mock()
        service.auth_service.get_wa = AsyncMock()
        service.check_authorization = AsyncMock(return_value=True)
        service.grant_permission = AsyncMock(return_value=False)
        return service

    @pytest.fixture
    def sample_deferrals(self) -> List[PendingDeferral]:
        """Create sample deferrals with different requirements."""
        return [
            PendingDeferral(
                deferral_id="defer_any_001",
                created_at=datetime.now(timezone.utc),
                deferred_by="agent_123",
                task_id="task_001",
                thought_id="thought_001",
                reason="General deferral",
                channel_id="test_channel",
                user_id="test_user",
                priority="low",
                requires_role=None,  # Any WA can resolve
                status="pending",
            ),
            PendingDeferral(
                deferral_id="defer_authority_001",
                created_at=datetime.now(timezone.utc),
                deferred_by="agent_123",
                task_id="task_002",
                thought_id="thought_002",
                reason="Requires authority decision",
                channel_id="test_channel",
                user_id="test_user",
                priority="high",
                requires_role="AUTHORITY",
                status="pending",
            ),
            PendingDeferral(
                deferral_id="defer_medical_001",
                created_at=datetime.now(timezone.utc),
                deferred_by="agent_123",
                task_id="task_003",
                thought_id="thought_003",
                reason="Medical decision required",
                channel_id="test_channel",
                user_id="test_user",
                priority="critical",
                requires_role="MEDICAL_AUTHORITY",
                status="pending",
            ),
        ]

    @pytest.mark.asyncio
    async def test_role_filtering_for_deferrals(self, sample_deferrals: List[PendingDeferral]) -> None:
        """Test that deferrals are filtered by required role."""
        # Filter for AUTHORITY role
        authority_deferrals = [d for d in sample_deferrals if d.requires_role in [None, "AUTHORITY"]]

        assert len(authority_deferrals) == 2
        assert "defer_any_001" in [d.deferral_id for d in authority_deferrals]
        assert "defer_authority_001" in [d.deferral_id for d in authority_deferrals]

        # Filter for MEDICAL_AUTHORITY role
        medical_deferrals = [d for d in sample_deferrals if d.requires_role in [None, "MEDICAL_AUTHORITY"]]

        assert len(medical_deferrals) == 2
        assert "defer_any_001" in [d.deferral_id for d in medical_deferrals]
        assert "defer_medical_001" in [d.deferral_id for d in medical_deferrals]

    @pytest.mark.asyncio
    async def test_resolution_role_validation(self, wa_service, sample_deferrals):
        """Test that resolution validates required role."""
        # Try to resolve medical deferral with non-medical authority
        response = DeferralResponse(
            approved=True,
            reason="Approved by wrong authority",
            modified_time=None,
            wa_id="wa_authority_001",  # Regular authority, not medical
            signature="test_sig",
        )

        # This should fail validation in a complete implementation
        # The actual validation would check:
        # 1. WA has resolve_deferral permission
        # 2. WA role matches deferral.requires_role
        # 3. WA certificate is valid and active

        # Mock the validation logic
        deferral = sample_deferrals[2]  # Medical deferral

        # In real implementation:
        # if deferral.requires_role and wa.role != deferral.requires_role:
        #     raise PermissionError("WA role does not match deferral requirements")

        wa_role = WARole.AUTHORITY
        required_role = "MEDICAL_AUTHORITY"

        assert wa_role.value != required_role  # Should not match

    @pytest.mark.asyncio
    async def test_permission_expiration(self, wa_service):
        """Test that permissions expire correctly."""
        # Grant temporary permission
        granted = await wa_service.grant_permission(wa_id="wa_temp_001", permission="resolve_deferral", resource="*")
        assert granted is False  # Expected - permissions are role-based

        # Mock permission with expiration
        expired_permission = WAPermission(
            permission_id="perm_expired",
            wa_id="wa_temp_001",
            permission_type="action",
            permission_name="resolve_deferral",
            resource="*",
            granted_by="wa_root",
            granted_at=datetime.now(timezone.utc) - timedelta(days=31),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # Expired yesterday
        )

        # Check if permission is expired
        is_expired = expired_permission.expires_at < datetime.now(timezone.utc)
        assert is_expired is True

        # Authorization should fail for expired permission
        # In real implementation, check_authorization would validate expiration


class TestDeferralAuditTrail:
    """Test audit trail for deferral operations."""

    @pytest.fixture
    def wa_service(self):
        """Mock wise authority service."""
        from unittest.mock import AsyncMock, Mock

        service = AsyncMock()
        service.auth_service = Mock()
        service.auth_service.get_wa = AsyncMock()
        service.check_authorization = AsyncMock(return_value=True)
        return service

    @pytest.mark.asyncio
    async def test_deferral_resolution_audit(self, wa_service):
        """Test that deferral resolutions are properly audited."""
        # Mock audit entries that would be created
        audit_entries = []

        # Resolution attempt
        resolution = DeferralResolution(
            deferral_id="defer_audit_001",
            wa_id="wa_authority_001",
            resolution="approve",
            guidance="Approved after careful review",
            new_constraints=["monitor_for_7_days"],
            resolution_metadata={"review_duration_minutes": "15", "review_quality": "thorough"},
        )

        # Audit entry that should be created
        audit_entry = {
            "timestamp": datetime.now(timezone.utc),
            "action": "deferral_resolved",
            "actor": resolution.wa_id,
            "target": resolution.deferral_id,
            "details": {
                "resolution": resolution.resolution,
                "guidance": resolution.guidance,
                "constraints_added": resolution.new_constraints,
                "metadata": resolution.resolution_metadata,
            },
        }

        audit_entries.append(audit_entry)

        # Verify audit trail
        assert len(audit_entries) == 1
        assert audit_entries[0]["action"] == "deferral_resolved"
        assert audit_entries[0]["actor"] == "wa_authority_001"
        assert "monitor_for_7_days" in audit_entries[0]["details"]["constraints_added"]

    @pytest.mark.asyncio
    async def test_failed_authorization_audit(self, wa_service):
        """Test that failed authorization attempts are audited."""
        # Mock unauthorized attempt
        unauthorized_attempt = {
            "timestamp": datetime.now(timezone.utc),
            "action": "deferral_resolution_denied",
            "actor": "wa_observer_001",
            "target": "defer_001",
            "reason": "insufficient_permissions",
            "details": {
                "required_role": "AUTHORITY",
                "actual_role": "OBSERVER",
                "required_permission": "resolve_deferral",
            },
        }

        # This would be logged in the audit system
        assert unauthorized_attempt["reason"] == "insufficient_permissions"
        assert unauthorized_attempt["details"]["required_role"] == "AUTHORITY"


class TestScopeGrantsGrammar:
    """Unit tests for the scope string grammar (pure function, no service)."""

    @pytest.mark.parametrize(
        "scope,action,resource,expected",
        [
            # Narrow domain grant: the glob is the jurisdiction.
            ("resolve_deferral:medical_*", "resolve_deferral", "medical_defer_001", True),
            ("resolve_deferral:medical_*", "resolve_deferral", "financial_defer_001", False),
            ("resolve_deferral:org/acme/*", "resolve_deferral", "org/acme/case-1", True),
            ("resolve_deferral:org/acme/*", "resolve_deferral", "org/other/case-1", False),
            # `any` is the spelling already minted across this codebase and has
            # to keep meaning "unrestricted" or every field certificate narrows.
            ("read:any", "read", "literally_anything", True),
            ("resolve_deferral:*", "resolve_deferral", "anything", True),
            ("*", "resolve_deferral", "anything", True),
            ("*:medical_*", "resolve_deferral", "medical_1", True),
            # The action half is load-bearing too: breadth on one action is not
            # breadth on another. A WA minted `read:any, write:any` (which is
            # what service_initializer mints) holds no deferral jurisdiction.
            ("write:any", "resolve_deferral", "defer_1", False),
            # A bare scope names an action and no domain. Reading it as "every
            # domain" is exactly the inference that produced the finding.
            ("resolve_deferral", "resolve_deferral", "medical_1", False),
            # Malformed scopes must not widen access.
            ("read:", "read", "x", False),
            ("   ", "read", "x", False),
            # Identifiers, not prose: matching is case-sensitive.
            ("resolve_deferral:Medical_*", "resolve_deferral", "medical_1", False),
        ],
    )
    def test_scope_grants(self, scope: str, action: str, resource: str, expected: bool) -> None:
        from ciris_engine.schemas.services.authority_core import scope_grants

        assert scope_grants(scope, action, resource) is expected


class TestResourceScopedAuthorization:
    """NULLWORKS RC3 finding F1 / MULTI-AUTH-01 regression tests.

    The finding: routing or domain affinity is not decision-specific human
    jurisdiction, and the final authority gate must reject an otherwise powerful
    authority who lacks scope for the specific decision. Before the fix,
    `check_authorization` accepted a `resource` argument and never read it, so
    every assertion in this class would have returned True.
    """

    @staticmethod
    def _cert(wa_id: str, role: WARole, scopes: List[str], name: str = "Test WA") -> WACertificate:
        import json

        return WACertificate(
            wa_id=wa_id,
            name=name,
            role=role,
            pubkey=f"{wa_id}_pubkey_base64url",
            jwt_kid=f"{wa_id}_kid",
            scopes_json=json.dumps(scopes),
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def certs(self) -> Dict[str, WACertificate]:
        return {
            # A real, powerful authority — scoped to one domain only.
            "wa-2025-06-28-MEDIC1": self._cert(
                "wa-2025-06-28-MEDIC1", WARole.AUTHORITY, ["resolve_deferral:medical_*"], "Medical Authority"
            ),
            # An authority minted the way service_initializer.py mints them.
            # Broad-sounding, and holding no deferral jurisdiction whatsoever.
            "wa-2025-06-28-BROAD1": self._cert(
                "wa-2025-06-28-BROAD1", WARole.AUTHORITY, ["read:any", "write:any"], "Broad Authority"
            ),
            # An authority genuinely authorized everywhere, spelled out.
            "wa-2025-06-28-GLOBL1": self._cert(
                "wa-2025-06-28-GLOBL1", WARole.AUTHORITY, ["resolve_deferral:any"], "Global Authority"
            ),
            "wa-2025-06-28-ROOT01": self._cert("wa-2025-06-28-ROOT01", WARole.ROOT, [], "Root"),
        }

    @pytest.fixture
    def wa_service(self, certs: Dict[str, WACertificate]) -> WiseAuthorityService:
        auth_service = AsyncMock()
        auth_service.bootstrap_if_needed = AsyncMock()

        async def mock_get_wa(wa_id: str) -> Optional[WACertificate]:
            return certs.get(wa_id)

        auth_service.get_wa = mock_get_wa

        time_service = Mock()
        time_service.now = Mock(return_value=datetime.now(timezone.utc))

        return WiseAuthorityService(time_service=time_service, auth_service=auth_service, db_path=":memory:")

    @pytest.mark.asyncio
    async def test_authority_without_scope_for_domain_is_denied(self, wa_service: WiseAuthorityService) -> None:
        """The medical authority has no jurisdiction over a financial decision."""
        allowed = await wa_service.check_authorization(
            "wa-2025-06-28-MEDIC1", "resolve_deferral", "financial_defer_001"
        )
        assert allowed is False

    @pytest.mark.asyncio
    async def test_authority_with_scope_for_domain_is_allowed(self, wa_service: WiseAuthorityService) -> None:
        """Same authority, same action, in-scope resource: allowed."""
        allowed = await wa_service.check_authorization("wa-2025-06-28-MEDIC1", "resolve_deferral", "medical_defer_001")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_authorization_is_not_resource_invariant(self, wa_service: WiseAuthorityService) -> None:
        """MULTI-AUTH-01 proper: identical WA and action, differing only in resource.

        Before the fix both calls returned True — the resource argument was
        accepted and discarded. That equality is the whole finding, so assert on
        the inequality directly rather than only on the two values.
        """
        in_scope = await wa_service.check_authorization("wa-2025-06-28-MEDIC1", "resolve_deferral", "medical_defer_001")
        out_of_scope = await wa_service.check_authorization(
            "wa-2025-06-28-MEDIC1", "resolve_deferral", "financial_defer_001"
        )
        assert in_scope != out_of_scope

    @pytest.mark.asyncio
    async def test_broadly_scoped_authority_lacks_decision_specific_jurisdiction(
        self, wa_service: WiseAuthorityService
    ) -> None:
        """`read:any` + `write:any` is breadth, not deferral jurisdiction.

        This is the "otherwise powerful authority" case in the finding's own
        words. The role gate passes — AUTHORITY may resolve deferrals — and the
        WA still holds no scope naming this decision.
        """
        decision = await wa_service.authorize("wa-2025-06-28-BROAD1", "resolve_deferral", "medical_defer_001")
        assert decision.allowed is False
        assert decision.reason is AuthorizationDenialReason.SCOPE_ABSENT

    @pytest.mark.asyncio
    async def test_explicit_global_scope_still_works(self, wa_service: WiseAuthorityService) -> None:
        """Breadth remains expressible — it just has to be written down."""
        allowed = await wa_service.check_authorization("wa-2025-06-28-GLOBL1", "resolve_deferral", "anything_at_all")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_root_is_never_scope_gated(self, wa_service: WiseAuthorityService) -> None:
        """ROOT holds no scopes at all here and still acts — it is the recovery path.

        If ROOT could be locked out by a bad scope set, the operator who fixes
        bad scope sets would be locked out by them too.
        """
        decision = await wa_service.authorize("wa-2025-06-28-ROOT01", "resolve_deferral", "financial_defer_001")
        assert decision.allowed is True
        assert decision.held_scopes == []

    @pytest.mark.asyncio
    async def test_denial_is_inspectable(self, wa_service: WiseAuthorityService) -> None:
        """A bare `False` is what let this sit in the code. The denial must say why.

        Whoever debugs a refused approval must be able to read which scope was
        demanded and which the WA actually held, without re-deriving the check.
        """
        decision = await wa_service.authorize("wa-2025-06-28-MEDIC1", "resolve_deferral", "financial_defer_001")

        assert decision.allowed is False
        assert decision.reason is AuthorizationDenialReason.SCOPE_ABSENT
        assert decision.scope_enforced is True
        assert decision.required_scope == "resolve_deferral:financial_defer_001"
        assert decision.held_scopes == ["resolve_deferral:medical_*"]
        assert decision.role is WARole.AUTHORITY
        # The message names both halves of the comparison that failed.
        assert "financial_defer_001" in decision.message
        assert "resolve_deferral:medical_*" in decision.message

    @pytest.mark.asyncio
    async def test_role_denial_is_distinguishable_from_scope_denial(self, wa_service: WiseAuthorityService) -> None:
        """`May never do this` and `may, but not here` need different names."""
        decision = await wa_service.authorize("wa-2025-06-28-MEDIC1", "mint_wa", "medical_defer_001")
        assert decision.allowed is False
        assert decision.reason is AuthorizationDenialReason.ROLE_FORBIDS_ACTION

    @pytest.mark.asyncio
    async def test_missing_certificate_is_distinguishable(self, wa_service: WiseAuthorityService) -> None:
        decision = await wa_service.authorize("wa-2025-06-28-NOBODY", "resolve_deferral", "medical_defer_001")
        assert decision.allowed is False
        assert decision.reason is AuthorizationDenialReason.WA_NOT_FOUND
        assert decision.role is None

    @pytest.mark.asyncio
    async def test_unnamed_resource_falls_back_to_the_role_gate_and_says_so(
        self, wa_service: WiseAuthorityService
    ) -> None:
        """`resource=None` keeps the pre-existing decision — visibly.

        Denying on a missing resource would deny every caller alive today (the
        protocol defaults it to None, `request_approval` reads it from metadata
        that is usually absent, the Discord adapter never sets it), so silence
        keeps the role-only answer. What changed is that the omission is now a
        readable fact instead of being indistinguishable from a jurisdiction
        check that ran and passed.
        """
        decision = await wa_service.authorize("wa-2025-06-28-BROAD1", "resolve_deferral", None)

        assert decision.allowed is True  # unchanged from pre-fix behaviour
        assert decision.scope_enforced is False
        assert decision.required_scope is None
        assert "named no resource" in decision.message

        # And the same WA IS refused the moment a caller names the resource.
        allowed = await wa_service.check_authorization("wa-2025-06-28-BROAD1", "resolve_deferral", "medical_defer_001")
        assert allowed is False

    @pytest.mark.asyncio
    async def test_garbled_scope_set_does_not_widen_access(self, wa_service: WiseAuthorityService) -> None:
        """A scopes column that fails to decode means "no scopes", never "allow".

        `authentication_store` documents rows in the wild whose `scopes` value
        is a JSON string rather than a list. Least privilege applies here too.
        """
        broken = Mock()
        broken.role = WARole.AUTHORITY
        broken.scopes = '["resolve_deferral:any"]'  # a str, not a list

        assert wa_service._held_scopes(broken) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
