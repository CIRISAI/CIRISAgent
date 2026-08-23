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

    @pytest.mark.skipif(not DESKTOP_UPDATER.exists(), reason="client tree not present")
    def test_desktop_writes_a_token_name_python_actually_reads(self):
        src = DESKTOP_UPDATER.read_text(encoding="utf-8")
        assert any(name in src for name in PY_READS), (
            "the desktop updater writes a token variable no Python code reads, so a "
            "successful silent re-sign-in leaves the expired token in place and every "
            "hosted-proxy call keeps 401ing. Python reads: " + ", ".join(PY_READS)
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
