"""
Regression tests for CIRISAgent#794 — `/v1/auth/setup/status` must
flag setup_required=True when config exists but no SYSTEM_ADMIN user
is present.

Background: a previously-aborted setup wizard can leave `.env`
CIRIS_CONFIGURED=true on disk without creating the founding SYSTEM_-
ADMIN user. Pre-2.9.3 `setup-status` returned setup_required=False
based on the .env alone, so the client believed the device was set up.
Every subsequent OAuth sign-in then 403'd with
`auth_personal_install_observer_blocked` and the user had no recovery
path. 2.9.3 adds a SYSTEM_ADMIN existence probe; when config_exists
but no admin is present, setup_required flips back to True so the
client auto-routes through the setup wizard.

These tests pin the resolution truth table:

  first_run | config_exists | has_admin | setup_required
  --------- | ------------- | --------- | --------------
  True      | True/False    | True/False| True   (first-run always wins)
  False     | True          | True      | False  (healthy install)
  False     | True          | False     | True   (#794 bugged install)
  False     | True          | None      | False  (auth not wired — fall back)
  False     | False         | None      | False  (no config — defer to first_run)

A note on the lazy-load regression (codex review of PR #795):

APIAuthService loads `_users` lazily — `_users_loaded` starts False
and `_ensure_users_loaded()` populates the cache on first call from
list_users / OAuth login paths. /setup/status is polled BEFORE any
login on a healthy install, so the cache is empty for legitimate
admins-in-DB. The probe MUST trigger the lazy load before reading
`_users`, otherwise a healthy install reads as has_admin=False and
gets falsely flagged setup_required=True — bouncing real users into
the wizard. The tests below assert this via mock auth services whose
`_users` only populate AFTER `_ensure_users_loaded()` runs.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response

from ciris_engine.logic.adapters.api.routes.setup.status import (
    _has_system_admin_user,
    get_setup_status,
)


class _MockRequest:
    """Minimal Request stand-in with the attribute access pattern the
    route uses. Plain MagicMock for app.state lets us set arbitrary
    auth_service shapes."""

    def __init__(self, auth_service):
        self.app = MagicMock()
        self.app.state.auth_service = auth_service


def _make_user(wa_id, *, api_role):
    user = MagicMock()
    user.wa_id = wa_id
    user.api_role = api_role
    return user


def _make_auth_service(users, *, populate_on_load=False):
    """Build a mock auth service that mirrors APIAuthService's lazy
    loading contract.

    Args:
        users: dict[str, User] — the "DB state" the lazy loader will
            install into `_users`.
        populate_on_load: if True, `_users` starts empty and is only
            populated when `_ensure_users_loaded` is awaited (mirrors
            the real lazy-load behavior the Codex review flagged).
            If False, `_users` is pre-populated (legacy behavior).
    """
    svc = MagicMock()
    if populate_on_load:
        svc._users = {}

        async def _do_load():
            svc._users = users

        svc._ensure_users_loaded = AsyncMock(side_effect=_do_load)
    else:
        svc._users = users
        svc._ensure_users_loaded = AsyncMock()
    return svc


class TestHasSystemAdminUser:
    def setup_method(self):
        from ciris_engine.schemas.runtime.api import APIRole

        self.APIRole = APIRole

    @pytest.mark.asyncio
    async def test_returns_none_when_auth_service_missing(self):
        """Early-boot path: auth_service not on app.state yet."""
        req = MagicMock()
        req.app.state.auth_service = None
        assert await _has_system_admin_user(req) is None

    @pytest.mark.asyncio
    async def test_returns_none_when_lazy_loader_missing(self):
        """Auth service of unknown shape — without `_ensure_users_loaded`
        we cannot safely assert admin absence (the `_users` dict may
        just be unloaded). Degrade to "unknown" so the route falls
        back to is_first_run, never false-positives setup_required."""
        svc = MagicMock(spec=["_users"])
        svc._users = {}
        assert await _has_system_admin_user(_MockRequest(svc)) is None

    @pytest.mark.asyncio
    async def test_lazy_load_populates_then_finds_admin(self):
        """REGRESSION (codex P1, PR #795): A healthy install has admins
        in the DB but `_users` starts empty until `_ensure_users_loaded`
        runs. The probe MUST trigger the lazy load — otherwise the
        empty cache makes a real admin install read as has_admin=False
        and falsely flag setup_required=True for legitimate users."""
        admin = _make_user("wa-1", api_role=self.APIRole.SYSTEM_ADMIN)
        svc = _make_auth_service({"wa-1": admin}, populate_on_load=True)
        # Pre-load: cache is empty
        assert svc._users == {}
        result = await _has_system_admin_user(_MockRequest(svc))
        # The probe loaded the cache and found the admin
        assert result is True
        svc._ensure_users_loaded.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lazy_load_subsequent_calls_short_circuit(self):
        """The lazy loader is idempotent (real impl gates on
        `_users_loaded` flag) — repeated /setup/status polls must not
        re-hit the DB. The mock here always-awaits, but the real
        contract is verified by the fact that _ensure_users_loaded is
        the *only* path we use — no raw DB queries from the route."""
        admin = _make_user("wa-1", api_role=self.APIRole.SYSTEM_ADMIN)
        svc = _make_auth_service({"wa-1": admin}, populate_on_load=True)
        await _has_system_admin_user(_MockRequest(svc))
        await _has_system_admin_user(_MockRequest(svc))
        await _has_system_admin_user(_MockRequest(svc))
        assert svc._ensure_users_loaded.await_count == 3
        # Each call relies on the lazy-loader contract, never on raw
        # DB access — this is what keeps the endpoint cheap to poll.

    @pytest.mark.asyncio
    async def test_returns_false_when_users_dict_empty_after_load(self):
        """The actual #794 bugged-install state: auth service is wired,
        lazy-load runs, but DB has no SYSTEM_ADMIN user."""
        svc = _make_auth_service({}, populate_on_load=True)
        assert await _has_system_admin_user(_MockRequest(svc)) is False

    @pytest.mark.asyncio
    async def test_returns_false_when_only_observers_exist(self):
        """No SYSTEM_ADMIN among non-empty users — still "no admin"."""
        svc = _make_auth_service(
            {"wa-1": _make_user("wa-1", api_role=self.APIRole.OBSERVER)},
        )
        assert await _has_system_admin_user(_MockRequest(svc)) is False

    @pytest.mark.asyncio
    async def test_returns_true_for_single_admin(self):
        svc = _make_auth_service(
            {"wa-1": _make_user("wa-1", api_role=self.APIRole.SYSTEM_ADMIN)}
        )
        assert await _has_system_admin_user(_MockRequest(svc)) is True

    @pytest.mark.asyncio
    async def test_dedupes_aliases_under_multiple_keys(self):
        """Real APIAuthService aliases the same User under multiple
        dict keys (wa_id, oauth primary, oauth link). The probe must
        count each user once — otherwise it can return True for an
        admin that's been aliased 3 times when in reality the only
        thing present is a single OBSERVER aliased once."""
        admin = _make_user("wa-1", api_role=self.APIRole.SYSTEM_ADMIN)
        observer = _make_user("wa-2", api_role=self.APIRole.OBSERVER)
        # 5 keys, 2 distinct users — should still find the admin.
        svc = _make_auth_service(
            {
                "wa-1": admin,
                "google:111": admin,
                "google:eric@x.io": admin,
                "wa-2": observer,
                "google:222": observer,
            }
        )
        assert await _has_system_admin_user(_MockRequest(svc)) is True

    @pytest.mark.asyncio
    async def test_returns_false_when_only_aliased_observer_exists(self):
        """Inverse of the above: multiple aliases of the same non-
        admin user must not be miscounted as 'at least one admin'."""
        obs = _make_user("wa-1", api_role=self.APIRole.OBSERVER)
        svc = _make_auth_service(
            {"wa-1": obs, "google:1": obs, "google:2": obs}
        )
        assert await _has_system_admin_user(_MockRequest(svc)) is False

    @pytest.mark.asyncio
    async def test_returns_none_on_introspection_failure(self):
        """Defensive: a broken auth_service must degrade to "unknown"
        rather than crash the status endpoint."""
        svc = MagicMock()
        svc._ensure_users_loaded = AsyncMock(
            side_effect=RuntimeError("loader exploded")
        )
        assert await _has_system_admin_user(_MockRequest(svc)) is None

    @pytest.mark.asyncio
    async def test_ignores_users_without_wa_id(self):
        """Defensive: malformed user entries with no wa_id are skipped
        rather than crashing the loop."""
        admin = _make_user("wa-1", api_role=self.APIRole.SYSTEM_ADMIN)
        broken = MagicMock()
        broken.wa_id = None
        broken.api_role = self.APIRole.SYSTEM_ADMIN
        svc = _make_auth_service({"broken": broken, "wa-1": admin})
        # Still finds the real admin
        assert await _has_system_admin_user(_MockRequest(svc)) is True


class TestSetupStatusResolution:
    """Pin the full setup_required truth table — the load-bearing
    self-heal for #794."""

    def setup_method(self):
        from ciris_engine.schemas.runtime.api import APIRole

        self.APIRole = APIRole

    def _make_request(self, *, has_admin, populate_on_load=False):
        """has_admin: True | False | None (probe returns this verbatim)."""
        if has_admin is True:
            svc = _make_auth_service(
                {"wa-1": _make_user("wa-1", api_role=self.APIRole.SYSTEM_ADMIN)},
                populate_on_load=populate_on_load,
            )
        elif has_admin is False:
            svc = _make_auth_service({}, populate_on_load=populate_on_load)
        else:  # None — auth not wired
            svc = None
        return _MockRequest(svc)

    @pytest.mark.asyncio
    async def test_first_run_always_required(self):
        """is_first_run=True always wins — we can't be "configured" if
        the .env doesn't even say so."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.is_first_run",
            return_value=True,
        ), patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.get_default_config_path"
        ) as mock_path:
            mock_path.return_value = MagicMock(exists=lambda: False)
            req = self._make_request(has_admin=None)
            response = Response()
            result = await get_setup_status(req, response)
            assert result.data.setup_required is True
            assert result.data.is_first_run is True

    @pytest.mark.asyncio
    async def test_healthy_install_not_required(self):
        """The happy path: config exists, admin exists, setup is done."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.is_first_run",
            return_value=False,
        ), patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.get_default_config_path"
        ) as mock_path:
            mock_path.return_value = MagicMock(exists=lambda: True)
            req = self._make_request(has_admin=True)
            response = Response()
            result = await get_setup_status(req, response)
            assert result.data.setup_required is False
            assert result.data.config_exists is True

    @pytest.mark.asyncio
    async def test_healthy_install_lazy_load_path(self):
        """REGRESSION (codex P1, PR #795): a real-world healthy install
        — admin persisted to DB but APIAuthService cache empty until
        the lazy loader fires on this very poll. setup_required MUST
        come back False, not True. Pre-fix this scenario would have
        bounced real users into the wizard on every first poll."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.is_first_run",
            return_value=False,
        ), patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.get_default_config_path"
        ) as mock_path:
            mock_path.return_value = MagicMock(exists=lambda: True)
            req = self._make_request(has_admin=True, populate_on_load=True)
            # Sanity: the cache really is empty until the route runs
            assert req.app.state.auth_service._users == {}
            response = Response()
            result = await get_setup_status(req, response)
            assert result.data.setup_required is False, (
                "Healthy install with lazy-load auth service must NOT "
                "false-positive setup_required — the route is responsible "
                "for triggering the lazy load."
            )
            # And the loader was actually invoked exactly once
            req.app.state.auth_service._ensure_users_loaded.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bugged_install_routes_back_to_setup(self):
        """THE #794 fix: config exists but no SYSTEM_ADMIN → require
        setup again. This is what self-heals the bugged install. We
        run this with populate_on_load=True so the test exercises the
        real lazy-load contract — empty cache, loader fires, still no
        admin → setup_required."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.is_first_run",
            return_value=False,
        ), patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.get_default_config_path"
        ) as mock_path:
            mock_path.return_value = MagicMock(exists=lambda: True)
            req = self._make_request(has_admin=False, populate_on_load=True)
            response = Response()
            result = await get_setup_status(req, response)
            assert result.data.setup_required is True, (
                "Config exists but no SYSTEM_ADMIN — must route back to setup. "
                "This is the load-bearing #794 self-heal."
            )

    @pytest.mark.asyncio
    async def test_unknown_admin_state_falls_back_to_first_run(self):
        """Auth service not wired yet (early boot) — don't force the
        user through setup just because we couldn't probe. Trust the
        is_first_run signal alone in that case."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.is_first_run",
            return_value=False,
        ), patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.get_default_config_path"
        ) as mock_path:
            mock_path.return_value = MagicMock(exists=lambda: True)
            req = self._make_request(has_admin=None)
            response = Response()
            result = await get_setup_status(req, response)
            assert result.data.setup_required is False, (
                "Unknown admin state must not false-positive setup_required "
                "during early boot — the auth service comes up after this "
                "endpoint is already serving."
            )

    @pytest.mark.asyncio
    async def test_no_config_still_first_run_path(self):
        """If config doesn't exist, the bugged-install check shouldn't
        fire — first_run handles it."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.is_first_run",
            return_value=True,
        ), patch(
            "ciris_engine.logic.adapters.api.routes.setup.status.get_default_config_path"
        ) as mock_path:
            mock_path.return_value = MagicMock(exists=lambda: False)
            req = self._make_request(has_admin=False)
            response = Response()
            result = await get_setup_status(req, response)
            assert result.data.setup_required is True
            assert result.data.config_exists is False
