"""
Tests for the personal-install owner-hint recovery UX (2.9.2).

Issue #784: a user who picked the wrong Google account during sign-in on
a personal-install mobile device hit a bare 403 with no recovery path.
The 2.9.2 server change enriches the 403 detail with an `owner_hint`
payload and exposes a `GET /v1/auth/owner-hint` endpoint so the Login
screen can show "Last signed in as Eric (e***@gmail.com)" before any
sign-in attempt.

These tests pin every observable surface of that contract — masking
rules, founding-owner lookup semantics, the 403 enrichment, the
pre-login endpoint's personal-install gating, and the privacy posture
(no surname, no avatar, no full email exposed).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# Re-export the private helpers we want to drive directly. Keeping the
# import surface narrow + named so a future refactor of the auth module
# can't silently break this test file via a star-import drift.
def _import_helpers():
    from ciris_engine.logic.adapters.api.routes import auth as auth_module

    return (
        auth_module._mask_email,
        auth_module._get_founding_owner_hint,
        auth_module._reject_observer_on_personal_install,
        auth_module,
    )


def _make_user(
    wa_id: str,
    *,
    api_role,
    oauth_email: str = "",
    oauth_name: str = "",
    name: str = "",
    auth_type: str = "oauth",
    oauth_provider: str = "google",
    created_at=None,
):
    """Build a minimal stand-in for auth_service.User that exposes only
    the attributes _get_founding_owner_hint reads. Using a plain object
    rather than the real dataclass keeps the test independent of unrelated
    User-schema churn."""
    user = MagicMock()
    user.wa_id = wa_id
    user.api_role = api_role
    user.oauth_email = oauth_email
    user.oauth_name = oauth_name
    user.name = name
    user.auth_type = auth_type
    user.oauth_provider = oauth_provider
    user.created_at = created_at
    return user


def _make_auth_service(users_by_key: dict):
    """Build a fake auth_service that exposes `_users` like the real
    APIAuthService does. Pass a dict keyed by anything (wa_id, oauth
    primary key, etc.) — duplicate User refs under multiple keys mirror
    the real service's aliasing pattern."""
    svc = MagicMock()
    svc._users = users_by_key
    return svc


# ---------------------------------------------------------------------------
# _mask_email
# ---------------------------------------------------------------------------


class TestMaskEmail:
    """The email-mask is the GDPR Art. 32 pseudonymisation rule shipped
    on every personal-install Login screen — it has to be deterministic
    and never leak the full local-part."""

    def setup_method(self):
        self.mask, _, _, _ = _import_helpers()

    def test_typical_email_keeps_three_chars(self):
        assert self.mask("ericmoore@gmail.com") == "eri***@gmail.com"

    def test_short_local_part_keeps_at_least_one_char(self):
        # 2-char prefix → keep 1 (len(prefix)-1, floored at 1)
        assert self.mask("ab@x.io") == "a***@x.io"

    def test_single_char_local_part_keeps_one(self):
        # Min 1 char retained — never mask everything to *** alone.
        assert self.mask("a@x.io") == "a***@x.io"

    def test_four_char_local_part_keeps_three(self):
        # 4-char prefix → keep 3 (capped at 3)
        assert self.mask("eric@x.io") == "eri***@x.io"

    def test_long_local_part_still_caps_at_three(self):
        # GDPR-friendly cap; never reveals more than first 3 chars.
        assert self.mask("ericamooreatxiscool@y.com") == "eri***@y.com"

    def test_returns_none_for_empty(self):
        assert self.mask("") is None
        assert self.mask(None) is None

    def test_returns_none_when_no_at_sign(self):
        # Don't try to "save" an invalid address — return None so the
        # caller renders the empty-hint path.
        assert self.mask("not-an-email") is None

    def test_handles_plus_addressing(self):
        assert self.mask("eric+ciris@gmail.com") == "eri***@gmail.com"

    def test_handles_subdomain(self):
        assert self.mask("eric@mail.ciris.ai") == "eri***@mail.ciris.ai"


# ---------------------------------------------------------------------------
# _get_founding_owner_hint
# ---------------------------------------------------------------------------


class TestGetFoundingOwnerHint:
    """Pin the founding-owner lookup semantics. The key contract: pick
    the earliest-created SYSTEM_ADMIN, dedupe by wa_id (since _users
    aliases the same User under multiple keys), mask the email, drop the
    surname."""

    def setup_method(self):
        from ciris_engine.schemas.runtime.api import APIRole

        self.APIRole = APIRole
        _, self.get_hint, _, _ = _import_helpers()

    def test_returns_none_when_auth_service_is_none(self):
        assert self.get_hint(None) is None

    def test_returns_none_when_users_dict_empty(self):
        svc = _make_auth_service({})
        assert self.get_hint(svc) is None

    def test_returns_none_when_no_system_admin_exists(self):
        # Only OBSERVER users — pre-setup state.
        user = _make_user(
            "wa-1",
            api_role=self.APIRole.OBSERVER,
            oauth_email="observer@x.io",
            name="O",
        )
        svc = _make_auth_service({"wa-1": user})
        assert self.get_hint(svc) is None

    def test_picks_single_system_admin(self):
        owner = _make_user(
            "wa-1",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="eric@gmail.com",
            oauth_name="Eric Moore",
            auth_type="oauth",
            oauth_provider="google",
        )
        svc = _make_auth_service({"wa-1": owner})
        hint = self.get_hint(svc)
        assert hint == {
            "masked_email": "eri***@gmail.com",
            "first_name": "Eric",
            "auth_type": "oauth",
            "oauth_provider": "google",
        }

    def test_dedupes_by_wa_id(self):
        """Real APIAuthService aliases the same User object under
        multiple keys (wa_id, OAuth primary key, OAuth link key). The
        hint lookup must dedupe — otherwise sorting could pick a
        different alias on different runs."""
        owner = _make_user(
            "wa-1",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="eric@gmail.com",
            oauth_name="Eric Moore",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        # Same user under 3 keys — should be treated as one.
        svc = _make_auth_service(
            {
                "wa-1": owner,
                "google:1234": owner,
                "google:eric@gmail.com": owner,
            }
        )
        hint = self.get_hint(svc)
        assert hint["masked_email"] == "eri***@gmail.com"
        assert hint["first_name"] == "Eric"

    def test_picks_earliest_created_when_multiple_admins(self):
        """If multiple SYSTEM_ADMINs exist (shouldn't on a personal
        install, but possible in shared/test setups), pick the earliest.
        That's the founding owner — the one the wizard ran for."""
        early = _make_user(
            "wa-early",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="founder@x.io",
            oauth_name="Founder",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        late = _make_user(
            "wa-late",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="later@x.io",
            oauth_name="Later",
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        # Insert late first to confirm we sort, not just take dict order.
        svc = _make_auth_service({"wa-late": late, "wa-early": early})
        hint = self.get_hint(svc)
        assert hint["first_name"] == "Founder"

    def test_handles_missing_created_at(self):
        """A pre-existing User without created_at must not crash the
        sort. The fallback (datetime.min) treats it as oldest, which
        is the right behavior for legacy data without timestamps."""
        owner = _make_user(
            "wa-1",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="eric@x.io",
            oauth_name="Eric",
            created_at=None,
        )
        svc = _make_auth_service({"wa-1": owner})
        assert self.get_hint(svc)["first_name"] == "Eric"

    def test_strips_surname_from_oauth_name(self):
        """Privacy posture: never expose surnames. Pseudonymisation
        means first name + masked email, nothing more."""
        owner = _make_user(
            "wa-1",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="e@x.io",
            oauth_name="Eric Wellington Moore",
        )
        svc = _make_auth_service({"wa-1": owner})
        hint = self.get_hint(svc)
        assert hint["first_name"] == "Eric"
        assert "Wellington" not in str(hint)
        assert "Moore" not in str(hint)

    def test_falls_back_to_name_when_oauth_name_empty(self):
        """Local-login users won't have oauth_name; fall back to the
        general `name` field so desktop / local-login installs still
        render a hint."""
        owner = _make_user(
            "wa-1",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="",
            oauth_name="",
            name="admin",
            auth_type="password",
            oauth_provider=None,
        )
        svc = _make_auth_service({"wa-1": owner})
        hint = self.get_hint(svc)
        assert hint == {
            "masked_email": None,  # local-login has no email
            "first_name": "admin",
            "auth_type": "password",
            "oauth_provider": None,
        }

    def test_returns_none_when_owner_has_no_identity_data(self):
        """A SYSTEM_ADMIN row with neither email nor name yields no
        hint — render an empty-state on the client rather than a
        worthless placeholder."""
        owner = _make_user(
            "wa-1",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="",
            oauth_name="",
            name="",
        )
        svc = _make_auth_service({"wa-1": owner})
        assert self.get_hint(svc) is None

    def test_does_not_expose_oauth_picture_or_external_id(self):
        """Make sure the hint payload only carries the four documented
        fields. Avatar / OAuth external_id are PII we don't surface to
        an unauthenticated client."""
        owner = _make_user(
            "wa-1",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="eric@gmail.com",
            oauth_name="Eric",
        )
        owner.oauth_picture = "https://lh3.googleusercontent.com/a/SECRET"
        owner.oauth_external_id = "1234567890"
        svc = _make_auth_service({"wa-1": owner})
        hint = self.get_hint(svc)
        assert set(hint.keys()) == {
            "masked_email",
            "first_name",
            "auth_type",
            "oauth_provider",
        }

    def test_recovers_from_exception_during_lookup(self):
        """Receipt capture must never propagate — if introspection on a
        user object fails for any reason, the hint endpoint should
        degrade to None rather than 500ing the Login screen."""
        broken_svc = MagicMock()
        # Accessing _users raises — simulates a service in an
        # un-started state.
        type(broken_svc)._users = property(
            lambda _self: (_ for _ in ()).throw(RuntimeError("not loaded"))
        )
        assert self.get_hint(broken_svc) is None


# ---------------------------------------------------------------------------
# _reject_observer_on_personal_install
# ---------------------------------------------------------------------------


class TestRejectObserverOnPersonalInstall:
    """Pin the 403 enrichment contract. Mobile + OBSERVER → 403 with
    owner_hint attached. Everything else → no raise."""

    def setup_method(self):
        from ciris_engine.schemas.api.auth import UserRole
        from ciris_engine.schemas.runtime.api import APIRole

        self.APIRole = APIRole
        self.UserRole = UserRole
        _, _, self.reject, _ = _import_helpers()

    def _patch_mobile(self, *, android=False, ios=False):
        return patch.multiple(
            "ciris_engine.logic.utils.path_resolution",
            is_android=MagicMock(return_value=android),
            is_ios=MagicMock(return_value=ios),
        )

    def test_no_raise_when_role_is_admin_on_mobile(self):
        """ADMIN / SYSTEM_ADMIN logins are never rejected by this gate
        — the block is OBSERVER-specific."""
        with self._patch_mobile(android=True):
            self.reject(self.UserRole.ADMIN, "admin@x.io", auth_service=None)
            self.reject(self.UserRole.SYSTEM_ADMIN, "admin@x.io", auth_service=None)

    def test_no_raise_when_observer_on_non_mobile(self):
        """OBSERVER is allowed on desktop / server installs — multi-user
        read-only access is a valid deployment shape there."""
        with self._patch_mobile(android=False, ios=False):
            self.reject(self.UserRole.OBSERVER, "viewer@x.io", auth_service=None)

    def test_raises_403_when_observer_on_android(self):
        with self._patch_mobile(android=True):
            with pytest.raises(HTTPException) as exc_info:
                self.reject(self.UserRole.OBSERVER, "viewer@x.io", auth_service=None)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "auth_personal_install_observer_blocked"

    def test_raises_403_when_observer_on_ios(self):
        with self._patch_mobile(ios=True):
            with pytest.raises(HTTPException) as exc_info:
                self.reject(self.UserRole.OBSERVER, "viewer@x.io", auth_service=None)
        assert exc_info.value.status_code == 403

    def test_403_omits_owner_hint_when_auth_service_not_provided(self):
        """Backwards-compat: callers that don't pass auth_service still
        produce a valid 403 — just without the recovery hint."""
        with self._patch_mobile(android=True):
            with pytest.raises(HTTPException) as exc_info:
                self.reject(self.UserRole.OBSERVER, "viewer@x.io")
        assert "owner_hint" not in exc_info.value.detail

    def test_403_includes_owner_hint_when_auth_service_provided(self):
        """The whole point of the 2.9.2 change: the 403 detail carries
        an owner_hint payload so the client can render the recovery
        screen without a second round-trip to the server."""
        owner = _make_user(
            "wa-1",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="eric@gmail.com",
            oauth_name="Eric Moore",
        )
        svc = _make_auth_service({"wa-1": owner})

        with self._patch_mobile(android=True):
            with pytest.raises(HTTPException) as exc_info:
                self.reject(self.UserRole.OBSERVER, "viewer@x.io", auth_service=svc)

        detail = exc_info.value.detail
        assert detail["code"] == "auth_personal_install_observer_blocked"
        assert detail["owner_hint"]["masked_email"] == "eri***@gmail.com"
        assert detail["owner_hint"]["first_name"] == "Eric"

    def test_403_omits_owner_hint_when_no_founding_owner_yet(self):
        """If setup hasn't completed (no SYSTEM_ADMIN), the hint lookup
        returns None — we must not put `None` under owner_hint, the
        key should be absent entirely so clients can branch on
        `"owner_hint" in detail`."""
        svc = _make_auth_service({})  # no users yet
        with self._patch_mobile(android=True):
            with pytest.raises(HTTPException) as exc_info:
                self.reject(self.UserRole.OBSERVER, "viewer@x.io", auth_service=svc)
        assert "owner_hint" not in exc_info.value.detail


# ---------------------------------------------------------------------------
# GET /v1/auth/owner-hint endpoint
# ---------------------------------------------------------------------------


class TestOwnerHintEndpoint:
    """The pre-login `GET /v1/auth/owner-hint` endpoint. Mobile-only
    surface — desktop / server installs respond 404 so an attacker
    polling the public API can't confirm owner identity."""

    def setup_method(self):
        from ciris_engine.logic.adapters.api.routes import auth as auth_module
        from ciris_engine.schemas.runtime.api import APIRole

        self.APIRole = APIRole
        self.endpoint = auth_module.get_owner_hint

    def _patch_mobile(self, *, android=False, ios=False):
        return patch.multiple(
            "ciris_engine.logic.utils.path_resolution",
            is_android=MagicMock(return_value=android),
            is_ios=MagicMock(return_value=ios),
        )

    @pytest.mark.asyncio
    async def test_404_on_non_mobile(self):
        """Multi-tenant servers must never leak owner identity through
        this endpoint — even by confirming it exists."""
        svc = _make_auth_service({})
        with self._patch_mobile(android=False, ios=False):
            with pytest.raises(HTTPException) as exc_info:
                await self.endpoint(auth_service=svc)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_hint_on_android(self):
        owner = _make_user(
            "wa-1",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="eric@gmail.com",
            oauth_name="Eric",
        )
        svc = _make_auth_service({"wa-1": owner})
        with self._patch_mobile(android=True):
            response = await self.endpoint(auth_service=svc)
        assert response == {
            "owner_hint": {
                "masked_email": "eri***@gmail.com",
                "first_name": "Eric",
                "auth_type": "oauth",
                "oauth_provider": "google",
            }
        }

    @pytest.mark.asyncio
    async def test_returns_hint_on_ios(self):
        owner = _make_user(
            "wa-1",
            api_role=self.APIRole.SYSTEM_ADMIN,
            oauth_email="e@x.io",
            oauth_name="Eric",
        )
        svc = _make_auth_service({"wa-1": owner})
        with self._patch_mobile(ios=True):
            response = await self.endpoint(auth_service=svc)
        assert response["owner_hint"]["first_name"] == "Eric"

    @pytest.mark.asyncio
    async def test_returns_null_hint_when_setup_incomplete(self):
        """Distinguish "no owner yet" (200 with null) from "endpoint
        does not exist" (404). The client needs to render a friendly
        empty state for a first-launch device, not a generic error."""
        svc = _make_auth_service({})  # no users
        with self._patch_mobile(android=True):
            response = await self.endpoint(auth_service=svc)
        assert response == {"owner_hint": None}
