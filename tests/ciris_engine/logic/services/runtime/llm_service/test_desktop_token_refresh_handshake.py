"""The desktop token-refresh handshake, end to end.

WHAT THIS REPRODUCES
--------------------
A desktop user on the CIRIS-hosted proxy works for about an hour and then
stops, permanently. Their log:

    [BILLING_PROVIDER] Started: auth_mode: JWT (Google ID token)
                               has_refresh_callback: False
    ciris_primary error: 401 - {'message': 'Invalid authentication token'}
    [INTERACT_TIMEOUT] ... timed out after 110s without an agent response

The hosted proxy is authenticated with the OAuth ID token itself
(`api_key=id_token`), and those expire in about an hour. There is a
handshake to replace it:

    1. Python gets a 401           -> writes CIRIS_HOME/.token_refresh_needed
    2. the client polls that file  -> silently re-signs-in
    3. the client rewrites .env with the fresh token
    4. the client writes .config_reload
    5. ResourceMonitor reloads .env and emits `token_refreshed`
    6. the LLM service re-reads the token and swaps its api_key

Step 3 is where desktop diverges. Android writes
CIRIS_BILLING_GOOGLE_ID_TOKEN and iOS writes CIRIS_BILLING_APPLE_ID_TOKEN —
both names Python reads. Desktop writes CIRIS_BILLING_OAUTH_TOKEN, which
nothing on the Python side has ever read. So the refresh completes, the
reload fires, and the service re-reads the SAME expired token: the loop runs
forever and recovers never.

These tests assert the CONTRACT (the names both sides use) rather than the
implementation, because the defect is precisely that two implementations
each worked in isolation.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path

import pytest


def jwt(exp_offset_seconds: float) -> str:
    """A token shaped like the real thing — these ARE JWTs, and the agent now
    chooses between copies by reading `exp`."""
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": time.time() + exp_offset_seconds}).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"

PY_READS = ("CIRIS_BILLING_GOOGLE_ID_TOKEN", "CIRIS_BILLING_APPLE_ID_TOKEN")

CLIENT_ROOT = Path(__file__).resolve().parents[6] / "client/shared/src"
DESKTOP_UPDATER = CLIENT_ROOT / "desktopMain/kotlin/ai/ciris/mobile/shared/platform/EnvFileUpdater.desktop.kt"
ANDROID_UPDATER = CLIENT_ROOT / "androidMain/kotlin/ai/ciris/mobile/shared/platform/EnvFileUpdater.android.kt"
IOS_UPDATER = CLIENT_ROOT / "iosMain/kotlin/ai/ciris/mobile/shared/platform/EnvFileUpdater.ios.kt"


class TestTheHandshakeContract:
    """Both halves must name the same variable, on every platform."""

    @staticmethod
    def _code_only(path: Path) -> str:
        """Kotlin source with comments stripped.

        Searching the whole file was the first version of this test and it was
        worthless: the explanatory comment above the assignment names both
        correct variables, so reverting the assignment itself back to the
        broken name would have left this green and let the outage return. A
        regression test that its own comment can satisfy is not a test.
        """
        out, in_block = [], False
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw
            if in_block:
                if "*/" in line:
                    line = line.split("*/", 1)[1]
                    in_block = False
                else:
                    continue
            if "/*" in line:
                head, rest = line.split("/*", 1)
                if "*/" in rest:
                    line = head + rest.split("*/", 1)[1]
                else:
                    line, in_block = head, True
            if "//" in line:
                line = line.split("//", 1)[0]
            out.append(line)
        return "\n".join(out)

    @pytest.mark.skipif(not DESKTOP_UPDATER.exists(), reason="client tree not present")
    def test_desktop_ASSIGNS_a_token_name_python_actually_reads(self):
        code = self._code_only(DESKTOP_UPDATER)
        assignment = re.search(r"val\s+tokenKey\s*=\s*(.+)", code)
        assert assignment, "could not find the tokenKey assignment — this guard has gone blind"
        rhs = assignment.group(1).strip()
        accepted = ("TokenHandshake.GOOGLE_TOKEN_VAR", "TokenHandshake.APPLE_TOKEN_VAR") + PY_READS
        assert any(name in rhs for name in accepted), (
            f"the desktop updater assigns tokenKey = {rhs} — a variable no Python code reads, so a "
            "successful silent re-sign-in leaves the expired token in place and every "
            "hosted-proxy call keeps 401ing. Python reads: " + ", ".join(PY_READS)
        )

    @pytest.mark.skipif(not DESKTOP_UPDATER.exists(), reason="client tree not present")
    def test_desktop_never_assigns_the_dead_legacy_name(self):
        code = self._code_only(DESKTOP_UPDATER)
        assignment = re.search(r"val\s+tokenKey\s*=\s*(.+)", code)
        assert assignment
        assert "CIRIS_BILLING_OAUTH_TOKEN" not in assignment.group(1), (
            "writing the legacy name is the original outage"
        )

    @pytest.mark.skipif(not ANDROID_UPDATER.exists(), reason="client tree not present")
    def test_android_still_writes_the_google_name(self):
        assert "CIRIS_BILLING_GOOGLE_ID_TOKEN" in ANDROID_UPDATER.read_text(encoding="utf-8")

    @pytest.mark.skipif(not IOS_UPDATER.exists(), reason="client tree not present")
    def test_ios_still_writes_the_apple_name(self):
        assert "CIRIS_BILLING_APPLE_ID_TOKEN" in IOS_UPDATER.read_text(encoding="utf-8")


class TestTheServiceSideOfTheHandshake:
    """Given a refreshed .env, the LLM service must actually swap its key."""

    @pytest.fixture
    def proxy_service(self):
        from ciris_engine.logic.services.runtime.llm_service.service import (
            OpenAICompatibleClient,
            OpenAIConfig,
        )

        config = OpenAIConfig(
            api_key="expired.jwt.value",
            model_name="gpt-4o-mini",
            base_url="https://llm01.ciris-services-1.ai/v1",
        )
        service = OpenAICompatibleClient.__new__(OpenAICompatibleClient)
        service.openai_config = config
        service.model_name = config.model_name
        service.client = None
        service._swapped_to = None

        def _update_api_key(key: str) -> None:
            service._swapped_to = key
            service.openai_config.api_key = key

        class _Breaker:
            def __init__(self) -> None:
                self.resets = 0

            def reset(self) -> None:
                self.resets += 1

        service.update_api_key = _update_api_key  # type: ignore[method-assign]
        service.circuit_breaker = _Breaker()
        return service

    @pytest.mark.asyncio
    async def test_a_fresh_google_token_is_picked_up(self, proxy_service, monkeypatch):
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "fresh.jwt.value")
        await proxy_service.handle_token_refreshed("token_refreshed", "openai_api_key")
        assert proxy_service._swapped_to == "fresh.jwt.value"

    @pytest.mark.asyncio
    async def test_the_freshest_copy_wins_when_several_names_are_present(
        self, proxy_service, monkeypatch
    ):
        """A real .env carries more than one: the Google name written at setup
        and whatever the client last refreshed. Choosing by name order returns
        the setup-time token, which is exactly the expired one."""
        stale, fresh = jwt(-600), jwt(3600)
        proxy_service.openai_config.api_key = stale
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", stale)
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", fresh)
        await proxy_service.handle_token_refreshed("token_refreshed", "openai_api_key")
        assert proxy_service._swapped_to == fresh

    @pytest.mark.asyncio
    async def test_the_desktop_variable_alone_must_not_strand_the_service(
        self, proxy_service, monkeypatch
    ):
        """THE BUG, from the service's side.

        The client re-signed-in successfully and wrote the token it knows how
        to write. If the service cannot see that name, it re-reads the expired
        one, reports "unchanged", resets the breaker, and 401s again — which is
        indistinguishable, in the log, from the user's credential simply being
        bad.
        """
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "expired.jwt.value")
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", "fresh.jwt.value")
        await proxy_service.handle_token_refreshed("token_refreshed", "openai_api_key")
        assert proxy_service._swapped_to == "fresh.jwt.value", (
            "a desktop client that refreshed its token left the service on the expired "
            "one — the 401 loop never recovers"
        )

    @pytest.mark.asyncio
    async def test_a_genuinely_unchanged_token_says_so_loudly(
        self, proxy_service, monkeypatch, caplog
    ):
        """The one case that must stay diagnosable: nothing new arrived.

        This is what a stranded desktop user's log looked like, and it read as
        routine. It must name the variables it consulted, so the next reader
        can tell "the client never wrote a new token" apart from "the token is
        new and still rejected".
        """
        import logging

        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "expired.jwt.value")
        monkeypatch.delenv("CIRIS_BILLING_OAUTH_TOKEN", raising=False)
        with caplog.at_level(logging.WARNING):
            await proxy_service.handle_token_refreshed("token_refreshed", "openai_api_key")
        blob = caplog.text
        assert proxy_service._swapped_to is None
        assert "CIRIS_BILLING_GOOGLE_ID_TOKEN" in blob, (
            "the no-op path must name which variables it read — otherwise a stranded "
            "client is invisible in the log"
        )


class TestTheHandshakeIsDefinedOnce:
    """The names live in one module per language, and the two agree.

    Every value in this handshake used to be re-spelled at each site: two
    copies of the refresh request in Python, three writers of the reload
    signal, three Kotlin clients with private constants. The drift was not
    hypothetical — it shipped, and it took a user's agent offline in a way no
    error message named.
    """

    KOTLIN_CONSTANTS = CLIENT_ROOT / "commonMain/kotlin/ai/ciris/mobile/shared/platform/EnvFileUpdater.kt"

    def test_python_defines_the_filenames_once(self):
        from ciris_engine.logic.utils import token_handshake as th

        assert th.TOKEN_REFRESH_REQUEST_FILE == ".token_refresh_needed"
        assert th.CONFIG_RELOAD_SIGNAL_FILE == ".config_reload"
        assert th.ENV_FILE == ".env"

    def test_no_python_site_respells_the_handshake_filenames(self):
        """Literal filenames belong to the module that defines them."""
        root = Path(__file__).resolve().parents[6] / "ciris_engine"
        offenders = []
        for py in root.rglob("*.py"):
            if py.name == "token_handshake.py":
                continue
            text = py.read_text(encoding="utf-8", errors="ignore")
            for literal in ('".token_refresh_needed"', '".config_reload"'):
                if literal in text:
                    offenders.append(f"{py.relative_to(root)} -> {literal}")
        assert not offenders, (
            "these sites spell a handshake filename themselves instead of importing it "
            "from utils.token_handshake: " + "; ".join(offenders)
        )

    @pytest.mark.skipif(not KOTLIN_CONSTANTS.exists(), reason="client tree not present")
    def test_the_two_languages_agree_on_every_name(self):
        from ciris_engine.logic.utils import token_handshake as th

        kotlin = self.KOTLIN_CONSTANTS.read_text(encoding="utf-8")
        for value in (
            th.TOKEN_REFRESH_REQUEST_FILE,
            th.CONFIG_RELOAD_SIGNAL_FILE,
            th.ENV_FILE,
            "CIRIS_BILLING_GOOGLE_ID_TOKEN",
            "CIRIS_BILLING_APPLE_ID_TOKEN",
        ):
            assert f'"{value}"' in kotlin, (
                f"the client half does not name {value!r}; the two ends of this handshake "
                "must be pinned to each other or they drift silently"
            )

    @pytest.mark.skipif(not DESKTOP_UPDATER.exists(), reason="client tree not present")
    def test_no_platform_respells_the_filenames(self):
        offenders = []
        for updater in (DESKTOP_UPDATER, ANDROID_UPDATER, IOS_UPDATER):
            if not updater.exists():
                continue
            text = updater.read_text(encoding="utf-8")
            for literal in ('".token_refresh_needed"', '".config_reload"'):
                if literal in text:
                    offenders.append(f"{updater.name} -> {literal}")
        assert not offenders, (
            "platform updaters must take these from TokenHandshake: " + "; ".join(offenders)
        )


class TestTheRequestSideLogsWhereItWrote:
    def test_the_ask_names_its_path_and_reason(self, tmp_path, monkeypatch, caplog):
        """A client that is not watching is invisible unless the agent says
        which directory it put the ask in — that path is the only way to see
        that the two halves are looking at different places."""
        import logging

        from ciris_engine.logic.utils.token_handshake import request_token_refresh

        monkeypatch.setenv("CIRIS_HOME", str(tmp_path))
        with caplog.at_level(logging.INFO):
            assert request_token_refresh(reason="proxy 401 on gpt-4o-mini") is True
        assert (tmp_path / ".token_refresh_needed").exists()
        assert str(tmp_path) in caplog.text
        assert "proxy 401 on gpt-4o-mini" in caplog.text


class TestTheSelectorNeverGoesBackwards:
    """Choosing between copies must not undo a good credential."""

    def test_a_stale_sibling_cannot_displace_the_freshest_value_in_hand(self, monkeypatch):
        """The mirror image of the legacy-desktop case.

        After a recovery the .env can hold a fresh token under one name and a
        stale one under another, with the fresh one already active. Preferring
        "any copy that differs" would then pick the stale one on every reload —
        including reloads the setup route triggers for unrelated reasons — and
        walk a working agent straight back into the 401 loop.
        """
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        fresh, stale = jwt(3600), jwt(-600)
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", fresh)
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", stale)
        token, var = read_proxy_token(current=fresh)
        assert token == fresh and var == "CIRIS_BILLING_OAUTH_TOKEN"

    def test_an_equally_opaque_sibling_still_wins_when_ours_is_being_rejected(self, monkeypatch):
        """The legacy-desktop case itself: neither token carries a readable
        expiry, and the one in hand is the one the provider is refusing."""
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "opaque-expired")
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", "opaque-refreshed")
        token, _ = read_proxy_token(current="opaque-expired")
        assert token == "opaque-refreshed"

    def test_with_nothing_in_hand_the_freshest_wins(self, monkeypatch):
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        fresh, stale = jwt(3600), jwt(60)
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", stale)
        monkeypatch.setenv("CIRIS_BILLING_APPLE_ID_TOKEN", fresh)
        token, var = read_proxy_token()
        assert token == fresh and var == "CIRIS_BILLING_APPLE_ID_TOKEN"


class TestBillingSharesTheSelector:
    """Billing recovering matters as much as the LLM recovering.

    A refresh that revives the LLM key but leaves billing on the setup-time
    token just moves the outage: credit checks keep returning AUTH_EXPIRED and
    gate every interaction, which looks to the user exactly like the agent
    still being broken.
    """

    def test_the_billing_provider_reads_through_the_shared_selector(self):
        src = (
            Path(__file__).resolve().parents[6]
            / "ciris_engine/logic/services/infrastructure/resource_monitor/ciris_billing_provider.py"
        ).read_text(encoding="utf-8")
        assert "read_proxy_token" in src, (
            "billing still reads the token names directly, so a client that refreshed under a "
            "different name revives the LLM and leaves billing expired"
        )

    def test_the_runtime_handlers_read_through_the_shared_selector(self):
        src = (
            Path(__file__).resolve().parents[6] / "ciris_engine/logic/runtime/billing_helpers.py"
        ).read_text(encoding="utf-8")
        assert src.count("read_proxy_token") >= 2, (
            "both the billing and the LLM refresh handlers must use the shared selector"
        )

    def test_the_llm_refresh_handler_does_not_key_off_OPENAI_API_KEY(self):
        """That handler only ever touches CIRIS-proxy services, and those
        authenticate with the ID token. Reading OPENAI_API_KEY meant the
        hosted-proxy case (empty) refreshed nothing, and the BYOK-leftover case
        pushed someone's provider key over a good token."""
        src = (
            Path(__file__).resolve().parents[6] / "ciris_engine/logic/runtime/billing_helpers.py"
        ).read_text(encoding="utf-8")
        handler = src[src.index("async def handle_llm_token_refreshed") : src.index("def update_llm_services_token")]
        assert 'os.getenv("OPENAI_API_KEY"' not in handler


class TestTheBillingCallbackCannotUndoARefresh:
    """The refresh must survive the next billing request.

    `_get_current_token()` runs before every billing call. It used to consult
    the injected `get_fresh_token` callback FIRST and return the moment that
    callback produced anything different from the token in hand. That callback
    was a first-non-empty read of the Google/Apple names — so after a legacy
    desktop refresh left a stale Google value beside a fresh one, it handed
    back the STALE token, installed it over the fresh one the refresh handler
    had just set, and returned before the shared selector was ever reached.
    Billing then kept answering AUTH_EXPIRED and gating interactions while the
    LLM key looked perfectly healthy.
    """

    def _provider(self, installed: str, callback):
        from ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider import (
            CIRISBillingProvider,
        )

        provider = CIRISBillingProvider.__new__(CIRISBillingProvider)
        provider._google_id_token = installed
        provider._token_refresh_callback = callback
        return provider

    def test_a_stale_callback_cannot_reinstall_the_expired_token(self, monkeypatch):
        stale, fresh = jwt(-600), jwt(3600)
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", stale)
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", fresh)

        # the old first-non-empty callback, verbatim
        provider = self._provider(installed=fresh, callback=lambda: stale)
        assert provider._get_current_token() == fresh, (
            "the callback reinstalled the expired token, so the very next billing request "
            "goes out with it and AUTH_EXPIRED resumes"
        )

    def test_the_same_holds_for_opaque_tokens(self, monkeypatch):
        """The legacy case has no readable expiry on either side."""
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "opaque-expired")
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", "opaque-refreshed")
        provider = self._provider(installed="opaque-expired", callback=lambda: "opaque-expired")
        assert provider._get_current_token() == "opaque-refreshed"

    def test_the_callback_still_serves_when_the_environment_is_empty(self, monkeypatch):
        """Demoted, not removed: a caller supplying a token from somewhere
        other than .env must still be honoured."""
        for var in ("CIRIS_BILLING_GOOGLE_ID_TOKEN", "CIRIS_BILLING_APPLE_ID_TOKEN", "CIRIS_BILLING_OAUTH_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        provider = self._provider(installed="", callback=lambda: "from-the-caller")
        assert provider._get_current_token() == "from-the-caller"

    def test_the_injected_callback_itself_uses_the_selector(self):
        src = (
            Path(__file__).resolve().parents[6] / "ciris_engine/logic/runtime/billing_helpers.py"
        ).read_text(encoding="utf-8")
        factory = src[src.index("def create_billing_provider") : src.index("async def reinitialize_billing_provider")]
        assert "read_proxy_token" in factory, "get_fresh_token must not re-implement the choice"
