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


class TestTheSelectorIsStable:
    """The same environment must give the same answer every time."""

    def test_opaque_tokens_do_not_alternate_across_repeated_calls(self, monkeypatch):
        """The bug this class exists for.

        With two opaque tokens the earlier tie-break preferred "whichever copy
        is not the one in hand". Holding A it returned B; holding B, the stable
        sort put A first again and the guard no longer fired, so it returned A.
        Credentials flipped on every single billing request — one of them
        always the rejected one. A selector whose answer depends on who is
        asking is not a selector.
        """
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "opaque-a")
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", "opaque-b")

        answers = {read_proxy_token(current=held)[0] for held in ("", "opaque-a", "opaque-b")}
        assert len(answers) == 1, f"the selector answered differently depending on what was held: {answers}"

    def test_repeated_billing_requests_settle_on_one_credential(self, monkeypatch):
        """The same property through the provider, which is where it bit."""
        from ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider import (
            CIRISBillingProvider,
        )

        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "opaque-expired")
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", "opaque-refreshed")

        provider = CIRISBillingProvider.__new__(CIRISBillingProvider)
        provider._google_id_token = "opaque-expired"
        provider._token_refresh_callback = lambda: "opaque-expired"

        seen = {provider._get_current_token() for _ in range(5)}
        assert seen == {"opaque-refreshed"}, f"credentials alternated across requests: {seen}"

    def test_expiry_still_beats_the_tie_order(self, monkeypatch):
        """The tie order only applies when nothing carries a readable expiry."""
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", jwt(3600))
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", jwt(-600))
        token, var = read_proxy_token()
        assert var == "CIRIS_BILLING_GOOGLE_ID_TOKEN", "a live token lost to an expired one on name order"


class TestTheCallbackParticipates:
    """Neither privileged nor ignored."""

    def test_an_external_callback_token_is_used_even_when_env_has_one(self, monkeypatch):
        """A caller fetching credentials from secure storage must not be
        silenced by a stale bootstrap value left in the environment."""
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "opaque-bootstrap")
        token, var = read_proxy_token(callback_token="from-secure-storage")
        assert token == "from-secure-storage" and var == "callback"

    def test_a_callback_that_merely_echoes_the_environment_gains_no_precedence(self, monkeypatch):
        """Echoing is not sourcing: the legacy first-non-empty callback returns
        a value already in .env, and must not win a tie with it."""
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "opaque-stale")
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", "opaque-refreshed")
        token, _ = read_proxy_token(callback_token="opaque-stale")
        assert token == "opaque-refreshed"

    def test_a_fresher_env_token_still_beats_an_expired_callback(self, monkeypatch):
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", jwt(3600))
        token, var = read_proxy_token(callback_token=jwt(-600))
        assert var == "CIRIS_BILLING_GOOGLE_ID_TOKEN"


class TestHostedToolsSharesTheSelector:
    def test_hosted_tools_does_not_read_the_token_names_itself(self):
        src = (
            Path(__file__).resolve().parents[6] / "ciris_adapters/ciris_hosted_tools/services.py"
        ).read_text(encoding="utf-8")
        method = src[src.index("def _get_google_id_token") : src.index("def _get_google_id_token") + 3000]
        assert "read_proxy_token" in method, (
            "hosted tools reads the token names directly, so after a client refreshes under a "
            "different name its requests keep going out with the stale setup token while the "
            "rest of the agent has recovered"
        )


class TestTheHandshakePathsThemselves:
    """The three paths, and the failure modes of writing to them.

    These are the values both processes must agree on, so each one is worth a
    test of its own: a wrong directory here is invisible at runtime — the ask
    is written, nothing answers, and the log looks like a client that simply
    never refreshed.
    """

    def test_every_path_hangs_off_CIRIS_HOME(self, tmp_path, monkeypatch):
        from ciris_engine.logic.utils import token_handshake as th

        monkeypatch.setenv("CIRIS_HOME", str(tmp_path))
        assert th.handshake_home() == tmp_path
        assert th.token_refresh_request_path() == tmp_path / ".token_refresh_needed"
        assert th.config_reload_signal_path() == tmp_path / ".config_reload"
        assert th.env_path() == tmp_path / ".env"

    def test_without_CIRIS_HOME_it_falls_back_to_the_shared_resolver(self, monkeypatch):
        """Never a third opinion about where home is."""
        from ciris_engine.logic.utils import token_handshake as th

        monkeypatch.delenv("CIRIS_HOME", raising=False)
        monkeypatch.setattr(
            "ciris_engine.logic.utils.path_resolution.get_ciris_home",
            lambda: "/somewhere/ciris",  # a str, as some callers return
        )
        assert th.handshake_home() == Path("/somewhere/ciris")
        assert th.env_path() == Path("/somewhere/ciris/.env")

    def test_the_ask_creates_the_directory_if_it_is_missing(self, tmp_path, monkeypatch):
        from ciris_engine.logic.utils.token_handshake import request_token_refresh

        home = tmp_path / "not-yet-there"
        monkeypatch.setenv("CIRIS_HOME", str(home))
        assert request_token_refresh(reason="first 401") is True
        assert (home / ".token_refresh_needed").read_text()

    def test_an_unwritable_home_is_reported_not_raised(self, tmp_path, monkeypatch, caplog):
        """A 401 handler must not turn into a crash because the disk said no."""
        import logging

        from ciris_engine.logic.utils.token_handshake import request_token_refresh

        blocker = tmp_path / "blocked"
        blocker.write_text("i am a file, not a directory")
        monkeypatch.setenv("CIRIS_HOME", str(blocker))
        with caplog.at_level(logging.ERROR):
            assert request_token_refresh(reason="proxy 401") is False
        assert "failed to write" in caplog.text.lower()

    def test_an_empty_environment_says_what_it_looked_for(self, monkeypatch, caplog):
        """When there is no token anywhere, the log must name the variables it
        checked — that line is how a stranded client is diagnosed at all."""
        import logging

        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        for var in ("CIRIS_BILLING_GOOGLE_ID_TOKEN", "CIRIS_BILLING_APPLE_ID_TOKEN", "CIRIS_BILLING_OAUTH_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        with caplog.at_level(logging.WARNING):
            token, var = read_proxy_token()
        assert (token, var) == ("", "")
        assert "CIRIS_BILLING_GOOGLE_ID_TOKEN" in caplog.text

    def test_an_unreadable_jwt_sorts_last_instead_of_raising(self):
        from ciris_engine.logic.utils.token_handshake import jwt_expiry_epoch

        assert jwt_expiry_epoch("") is None
        assert jwt_expiry_epoch("not-a-jwt") is None
        assert jwt_expiry_epoch("a.b.c") is None          # payload is not base64 JSON
        assert jwt_expiry_epoch("h.eyJzdWIiOiJ4In0.s") is None  # valid JSON, no exp
        assert jwt_expiry_epoch(jwt(60)) is not None


class TestNobodyReadsTheTokenNamesDirectly:
    """One module knows the variable names. Everything else asks it.

    This started as one mismatch — desktop writing a name Python never read —
    and every round of review since has found another site quietly holding its
    own copy of the list: billing's provider, its two runtime handlers, its
    lazy initializer, the tools route, the hosted-tools adapter and its .env
    scan, the startup credential, and the capability gates that decide whether
    hosted features exist at all. Each was locally reasonable and collectively
    they meant a refreshed token reached some subsystems and not others, so the
    agent recovered in pieces.

    A grep is the only thing that can hold this line, so here it is.
    """

    ALLOWED = {
        "ciris_engine/logic/utils/token_handshake.py",  # defines them
        "ciris_engine/logic/setup/wizard.py",           # writes the .env template
    }

    def test_no_module_outside_the_handshake_reads_a_token_variable(self):
        import re

        root = Path(__file__).resolve().parents[6]
        pattern = re.compile(
            r'os\.(?:getenv|environ\.get)\(\s*["\']'
            r'(CIRIS_BILLING_GOOGLE_ID_TOKEN|CIRIS_BILLING_APPLE_ID_TOKEN|CIRIS_BILLING_OAUTH_TOKEN)'
        )
        offenders = []
        for base in ("ciris_engine", "ciris_adapters"):
            for py in (root / base).rglob("*.py"):
                rel = py.relative_to(root).as_posix()
                if rel in self.ALLOWED:
                    continue
                for lineno, line in enumerate(py.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if pattern.search(line):
                        offenders.append(f"{rel}:{lineno}")
        assert not offenders, (
            "these read a proxy-token variable directly instead of calling "
            "token_handshake.read_proxy_token() / has_proxy_token(); a token refreshed under a "
            "name they do not know leaves them on the expired one while the rest of the agent "
            "recovers: " + ", ".join(offenders)
        )

    def test_the_consumers_all_import_the_selector(self):
        """The other direction: the known consumers must actually call it."""
        root = Path(__file__).resolve().parents[6]
        consumers = [
            "ciris_engine/logic/services/runtime/llm_service/service.py",
            "ciris_engine/logic/services/infrastructure/resource_monitor/ciris_billing_provider.py",
            "ciris_engine/logic/runtime/billing_helpers.py",
            "ciris_engine/logic/runtime/service_initializer.py",
            "ciris_engine/logic/adapters/api/routes/billing.py",
            "ciris_engine/logic/adapters/api/routes/tools.py",
            "ciris_adapters/ciris_hosted_tools/services.py",
        ]
        missing = [
            c for c in consumers
            if "token_handshake" not in (root / c).read_text(encoding="utf-8")
        ]
        assert not missing, f"these consume the proxy token without the shared selector: {missing}"


class TestExpiryStatusIsATierNotANumber:
    """A token we can prove is dead must never outrank one that might be alive."""

    def test_an_expired_jwt_loses_to_an_opaque_callback_token(self, monkeypatch):
        """The defect: an expired JWT still carries a large positive epoch,
        while a token whose format has no `exp` scores zero. Ranking on the
        raw number therefore preferred the credential we are actively being
        refused for over the replacement a callback had just fetched."""
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", jwt(-600))
        token, var = read_proxy_token(callback_token="google:1089981372")
        assert (token, var) == ("google:1089981372", "callback")

    def test_an_expired_jwt_loses_to_an_opaque_environment_token(self, monkeypatch):
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", jwt(-600))
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", "opaque-but-possibly-alive")
        token, _ = read_proxy_token()
        assert token == "opaque-but-possibly-alive"

    def test_a_live_jwt_still_beats_an_opaque_token(self, monkeypatch):
        """The tier order only helps the unknown against the known-dead."""
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        live = jwt(3600)
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", live)
        token, var = read_proxy_token(callback_token="opaque")
        assert (token, var) == (live, "CIRIS_BILLING_GOOGLE_ID_TOKEN")

    def test_an_expired_token_is_still_offered_when_it_is_all_there_is(self, monkeypatch):
        """Last resort, not discarded: a clean 401 is more useful than sending
        no credential at all."""
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        dead = jwt(-600)
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", dead)
        assert read_proxy_token()[0] == dead

    def test_the_least_stale_expired_token_wins_among_expired_ones(self, monkeypatch):
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        older, newer = jwt(-9000), jwt(-60)
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", older)
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", newer)
        assert read_proxy_token()[0] == newer


class TestTheEnvFileScanUsesTheSameRanking:
    """One ordering, wherever the candidates were read from.

    The hosted-tools .env fallback ranked its own finds by expiry alone, which
    left the opaque tie to dictionary insertion order — Google first — while
    the shared selector resolves that tie toward the legacy-desktop name. Same
    inputs, different answers, so tools sent the stale credential while billing
    and the LLM used the refreshed one.
    """

    def test_the_file_resolves_an_opaque_tie_like_the_selector(self, tmp_path, monkeypatch):
        from ciris_adapters.ciris_hosted_tools.services import CIRISHostedToolService
        from ciris_engine.logic.utils.token_handshake import read_proxy_token

        for var in ("CIRIS_BILLING_GOOGLE_ID_TOKEN", "CIRIS_BILLING_APPLE_ID_TOKEN", "CIRIS_BILLING_OAUTH_TOKEN", "GOOGLE_ID_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("CIRIS_HOME", str(tmp_path))
        monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
        (tmp_path / ".env").write_text(
            "CIRIS_BILLING_GOOGLE_ID_TOKEN=opaque-stale\nCIRIS_BILLING_OAUTH_TOKEN=opaque-refreshed\n"
        )

        service = CIRISHostedToolService.__new__(CIRISHostedToolService)
        from_file = service._get_google_id_token()

        # what the selector would have said from the same pair
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "opaque-stale")
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", "opaque-refreshed")
        from_env, _ = read_proxy_token()

        assert from_file == from_env == "opaque-refreshed"

    def test_the_file_prefers_a_live_token_over_an_expired_one(self, tmp_path, monkeypatch):
        from ciris_adapters.ciris_hosted_tools.services import CIRISHostedToolService

        for var in ("CIRIS_BILLING_GOOGLE_ID_TOKEN", "CIRIS_BILLING_APPLE_ID_TOKEN", "CIRIS_BILLING_OAUTH_TOKEN", "GOOGLE_ID_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("CIRIS_HOME", str(tmp_path))
        monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
        live, dead = jwt(3600), jwt(-600)
        (tmp_path / ".env").write_text(
            f"CIRIS_BILLING_OAUTH_TOKEN={dead}\nCIRIS_BILLING_GOOGLE_ID_TOKEN={live}\n"
        )

        service = CIRISHostedToolService.__new__(CIRISHostedToolService)
        assert service._get_google_id_token() == live
