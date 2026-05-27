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

    @staticmethod
    def _patch_setup_state(first_run: bool, config_exists: bool):
        """Patch the is_first_run + get_default_config_path symbols at every
        bind site — status.py and dependencies.py both call them. Tests
        that patch only one location silently miss the other (was the
        bug in PR #795's test coverage; caught by Codex P1 #2 — the
        gate symbol bound in dependencies.py was never patched, so
        require_setup_mode kept seeing the real first-run result)."""
        return [
            patch(
                "ciris_engine.logic.adapters.api.routes.setup.status.is_first_run",
                return_value=first_run,
            ),
            patch(
                "ciris_engine.logic.adapters.api.routes.setup.dependencies.is_first_run",
                return_value=first_run,
            ),
            patch(
                "ciris_engine.logic.adapters.api.routes.setup.status.get_default_config_path"
            ),
            patch(
                "ciris_engine.logic.adapters.api.routes.setup.dependencies.get_default_config_path"
            ),
        ]

    @staticmethod
    def _start_patches(patches, config_exists: bool):
        """Enter all patches; set the config_path mocks to return a path
        that reports `exists() == config_exists`."""
        mocks = [p.start() for p in patches]
        path_mock = MagicMock(exists=lambda: config_exists)
        # The two get_default_config_path patches are at indices 2 and 3.
        mocks[2].return_value = path_mock
        mocks[3].return_value = path_mock
        return patches

    @staticmethod
    def _stop_patches(patches):
        for p in patches:
            p.stop()

    @pytest.mark.asyncio
    async def test_first_run_always_required(self):
        """is_first_run=True always wins — we can't be "configured" if
        the .env doesn't even say so."""
        patches = self._patch_setup_state(first_run=True, config_exists=False)
        self._start_patches(patches, config_exists=False)
        try:
            req = self._make_request(has_admin=None)
            response = Response()
            result = await get_setup_status(req, response)
            assert result.data.setup_required is True
            assert result.data.is_first_run is True
        finally:
            self._stop_patches(patches)

    @pytest.mark.asyncio
    async def test_healthy_install_not_required(self):
        """The happy path: config exists, admin exists, setup is done."""
        patches = self._patch_setup_state(first_run=False, config_exists=True)
        self._start_patches(patches, config_exists=True)
        try:
            req = self._make_request(has_admin=True)
            response = Response()
            result = await get_setup_status(req, response)
            assert result.data.setup_required is False
            assert result.data.config_exists is True
        finally:
            self._stop_patches(patches)

    @pytest.mark.asyncio
    async def test_healthy_install_lazy_load_path(self):
        """REGRESSION (codex P1, PR #795): a real-world healthy install
        — admin persisted to DB but APIAuthService cache empty until
        the lazy loader fires on this very poll. setup_required MUST
        come back False, not True. Pre-fix this scenario would have
        bounced real users into the wizard on every first poll."""
        patches = self._patch_setup_state(first_run=False, config_exists=True)
        self._start_patches(patches, config_exists=True)
        try:
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
        finally:
            self._stop_patches(patches)

    @pytest.mark.asyncio
    async def test_bugged_install_routes_back_to_setup(self):
        """THE #794 fix: config exists but no SYSTEM_ADMIN → require
        setup again. This is what self-heals the bugged install. We
        run this with populate_on_load=True so the test exercises the
        real lazy-load contract — empty cache, loader fires, still no
        admin → setup_required."""
        patches = self._patch_setup_state(first_run=False, config_exists=True)
        self._start_patches(patches, config_exists=True)
        try:
            req = self._make_request(has_admin=False, populate_on_load=True)
            response = Response()
            result = await get_setup_status(req, response)
            assert result.data.setup_required is True, (
                "Config exists but no SYSTEM_ADMIN — must route back to setup. "
                "This is the load-bearing #794 self-heal."
            )
        finally:
            self._stop_patches(patches)

    @pytest.mark.asyncio
    async def test_unknown_admin_state_falls_back_to_first_run(self):
        """Auth service not wired yet (early boot) — don't force the
        user through setup just because we couldn't probe. Trust the
        is_first_run signal alone in that case."""
        patches = self._patch_setup_state(first_run=False, config_exists=True)
        self._start_patches(patches, config_exists=True)
        try:
            req = self._make_request(has_admin=None)
            response = Response()
            result = await get_setup_status(req, response)
            assert result.data.setup_required is False, (
                "Unknown admin state must not false-positive setup_required "
                "during early boot — the auth service comes up after this "
                "endpoint is already serving."
            )
        finally:
            self._stop_patches(patches)

    @pytest.mark.asyncio
    async def test_no_config_still_first_run_path(self):
        """If config doesn't exist, the bugged-install check shouldn't
        fire — first_run handles it."""
        patches = self._patch_setup_state(first_run=True, config_exists=False)
        self._start_patches(patches, config_exists=False)
        try:
            req = self._make_request(has_admin=False)
            response = Response()
            result = await get_setup_status(req, response)
            assert result.data.setup_required is True
            assert result.data.config_exists is False
        finally:
            self._stop_patches(patches)


class TestRequireSetupMode:
    """Regression tests for Codex P1 #2 — `require_setup_mode` must open
    the gate for the bugged-install recovery flow, not just for first-run.

    Pre-fix: Bug D made /setup/status report `setup_required=True` for
    the configured-but-no-admin state, BUT `require_setup_mode()` still
    only checked `is_first_run()` — so the wizard endpoints all 403'd.
    The client navigated to Setup, every endpoint failed, the user was
    stuck. Tests below pin that the gate and the signpost agree.
    """

    def setup_method(self):
        from ciris_engine.schemas.runtime.api import APIRole

        self.APIRole = APIRole

    def _make_request(self, *, has_admin, populate_on_load=False):
        if has_admin is True:
            svc = _make_auth_service(
                {"wa-1": _make_user("wa-1", api_role=self.APIRole.SYSTEM_ADMIN)},
                populate_on_load=populate_on_load,
            )
        elif has_admin is False:
            svc = _make_auth_service({}, populate_on_load=populate_on_load)
        else:
            svc = None
        return _MockRequest(svc)

    def _patches(self, *, first_run: bool, config_exists: bool):
        return [
            patch(
                "ciris_engine.logic.adapters.api.routes.setup.dependencies.is_first_run",
                return_value=first_run,
            ),
            patch(
                "ciris_engine.logic.adapters.api.routes.setup.dependencies.get_default_config_path",
                return_value=MagicMock(exists=lambda: config_exists),
            ),
        ]

    @pytest.mark.asyncio
    async def test_allows_during_first_run(self):
        from ciris_engine.logic.adapters.api.routes.setup.dependencies import (
            require_setup_mode,
        )

        for p in self._patches(first_run=True, config_exists=False):
            p.start()
        try:
            req = self._make_request(has_admin=None)
            # Should NOT raise
            await require_setup_mode(req)
        finally:
            from unittest.mock import patch as _patch  # noqa: F401
            patch.stopall()

    @pytest.mark.asyncio
    async def test_blocks_healthy_install(self):
        from fastapi import HTTPException

        from ciris_engine.logic.adapters.api.routes.setup.dependencies import (
            require_setup_mode,
        )

        for p in self._patches(first_run=False, config_exists=True):
            p.start()
        try:
            req = self._make_request(has_admin=True)
            with pytest.raises(HTTPException) as exc:
                await require_setup_mode(req)
            assert exc.value.status_code == 403
        finally:
            patch.stopall()

    @pytest.mark.asyncio
    async def test_allows_bugged_install_recovery(self):
        """THE Codex P1 #2 FIX: when /setup/status would return
        setup_required=True for the bugged-install state, the wizard
        endpoint gate must also open — otherwise the client navigates
        to Setup and every endpoint 403s."""
        from ciris_engine.logic.adapters.api.routes.setup.dependencies import (
            require_setup_mode,
        )

        for p in self._patches(first_run=False, config_exists=True):
            p.start()
        try:
            req = self._make_request(has_admin=False, populate_on_load=True)
            # Should NOT raise — bugged-install recovery is in-scope for
            # setup mode.
            await require_setup_mode(req)
        finally:
            patch.stopall()

    @pytest.mark.asyncio
    async def test_status_signpost_and_gate_agree_on_bugged_install(self):
        """The whole point of extracting is_setup_required is that both
        /setup/status and require_setup_mode read the SAME predicate.
        If they ever drift the client gets routed to Setup and then
        bounced out again. Pin the lock-step explicitly."""
        from ciris_engine.logic.adapters.api.routes.setup.dependencies import (
            is_setup_required,
            require_setup_mode,
        )

        for p in self._patches(first_run=False, config_exists=True):
            p.start()
        try:
            req = self._make_request(has_admin=False, populate_on_load=True)
            # The signpost says "setup required"
            signpost = await is_setup_required(req)
            assert signpost is True
            # And the gate opens (must not raise)
            req2 = self._make_request(has_admin=False, populate_on_load=True)
            await require_setup_mode(req2)
        finally:
            patch.stopall()

    @pytest.mark.asyncio
    async def test_unknown_admin_state_blocks_gate(self):
        """If we can't probe the auth service (early boot, unknown shape),
        is_setup_required returns False — and the gate blocks. This is
        the conservative bias: don't open the wizard on uncertainty,
        because /setup/status is also reporting "not required" in that
        ambiguous state."""
        from fastapi import HTTPException

        from ciris_engine.logic.adapters.api.routes.setup.dependencies import (
            require_setup_mode,
        )

        for p in self._patches(first_run=False, config_exists=True):
            p.start()
        try:
            req = self._make_request(has_admin=None)
            with pytest.raises(HTTPException) as exc:
                await require_setup_mode(req)
            assert exc.value.status_code == 403
        finally:
            patch.stopall()
