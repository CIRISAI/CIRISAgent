#!/usr/bin/env python3
"""
Desktop App / Web UI QA Runner CLI

End-to-end UI testing for CIRIS Desktop app and web interface.

Usage:
    python -m tools.qa_runner.modules.web_ui [command] [options]

Commands:
    desktop         Test the CIRIS Desktop app (uses TestAutomationServer)
    desktop-login   Test login flow on desktop app
    desktop-chat    Test chat interaction on desktop app
    desktop-setup   Drive the NODE-CLIENT first-run wizard (announce decision,
                    gated trace opt-in, fed-ID label, age range; NO LLM step)
    desktop-catchup Drive the catch-up Add-Federation-ID flow
                    (btn_add_federation_id -> input_fed_label ->
                    toggle_announce_ownership -> btn_add_fedid_confirm)
    desktop-up      Full orchestration: wipe -> setup via API -> launch -> login
    e2e             Run full end-to-end test flow (browser-based, legacy)
    setup           Test only setup wizard steps (browser-based, agent flow)
    interact        Test only interaction steps (browser-based)
    models          Test only model listing feature (browser-based, agent flow)
    licensed_agent  First-time licensed agent flow (Portal device auth)
    list            List available tests

Examples:
    # Test desktop app (requires CIRIS_TEST_MODE=true)
    python -m tools.qa_runner.modules.web_ui desktop

    # Test desktop app login flow
    python -m tools.qa_runner.modules.web_ui desktop-login

    # Test desktop app chat
    python -m tools.qa_runner.modules.web_ui desktop-chat

    # Legacy browser-based E2E test
    python -m tools.qa_runner.modules.web_ui e2e --wipe

    # Use mock LLM (no API key needed)
    python -m tools.qa_runner.modules.web_ui e2e --mock-llm
"""

# Windows cp1252 consoles raise UnicodeEncodeError on any non-ASCII glyph, which
# takes the whole process down. main.py / cli.py / desktop_launcher already call
# this; the QA runner never did, so it crashed on Windows CI before reaching a
# single test — which is why this harness had never run there.
try:
    from ciris_engine.logic.utils import win_console as _win_console

    _win_console.setup()
except Exception:  # pragma: no cover - never let the shim stop the runner
    pass

import argparse
import asyncio
import glob
import json
import os
import shutil
import subprocess
import tempfile
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import re
import requests

from tools.qa_runner.platform_procs import temp_path

from .browser_helper import BrowserConfig, ensure_playwright_installed
from .desktop_app_helper import DesktopAppConfig, DesktopAppHelper, check_desktop_app_running
from .federation_walk_test import FederationWalkTest
from .server_manager import ServerConfig
from .test_cases import WebUITestConfig
from .test_runner import WebUITestRunner, run_web_ui_tests


@dataclass
class DesktopTestResult:
    """Result of a desktop app test."""

    name: str
    success: bool
    duration_ms: float
    error: Optional[str] = None
    screen: Optional[str] = None


class DesktopAppTestRunner:
    """
    Test runner for CIRIS Desktop app.

    Uses the embedded TestAutomationServer for native Compose automation.
    """

    def __init__(self, config: Optional[DesktopAppConfig] = None, verbose: bool = False):
        self.config = config or DesktopAppConfig()
        self.verbose = verbose
        self.helper: Optional[DesktopAppHelper] = None
        self.results: List[DesktopTestResult] = []

    async def start(self) -> "DesktopAppTestRunner":
        """Start the test runner and connect to desktop app."""
        self.helper = DesktopAppHelper(self.config)
        await self.helper.start()
        return self

    async def stop(self) -> None:
        """Stop the test runner."""
        if self.helper:
            await self.helper.stop()
            self.helper = None

    def _log(self, msg: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"  {msg}")

    async def _dump_tree(self, label: str) -> None:
        """Print every testTag currently composed, for a failed element wait.

        Deliberately unconditional -- not gated on --verbose. This runs when
        something has ALREADY failed, and it is the difference between a CI log
        that says "Element not found: input_username" (which costs another full
        round trip to learn anything) and one that says which screen variant
        actually rendered. Never raises: a diagnostic that can fail replaces the
        real error with its own.
        """
        try:
            elements = await self.helper.get_elements()
            print(f"  [tree:{label}] screen={self.helper.current_screen!r} elements={len(elements)}")
            for e in elements:
                print(f"      {e.test_tag}")
            if not elements:
                print("      (nothing composed — the app rendered no tagged elements at all)")
        except Exception as exc:
            print(f"  [tree:{label}] could not read the element tree: {type(exc).__name__}: {exc}")

    async def run_test(self, name: str, test_fn) -> DesktopTestResult:
        """Run a single test and record result."""
        start = datetime.now()
        try:
            await test_fn()
            duration = (datetime.now() - start).total_seconds() * 1000
            screen = await self.helper.get_screen() if self.helper else None
            result = DesktopTestResult(
                name=name,
                success=True,
                duration_ms=duration,
                screen=screen,
            )
            print(f" [OK] {name} ({duration:.0f}ms)")
        except Exception as e:
            duration = (datetime.now() - start).total_seconds() * 1000
            screen = await self.helper.get_screen() if self.helper else None
            result = DesktopTestResult(
                name=name,
                success=False,
                duration_ms=duration,
                error=str(e),
                screen=screen,
            )
            print(f" [FAIL] {name}: {e}")

        self.results.append(result)
        return result

    async def test_login_flow(self, username: str = "admin", password: str = "qa_test_password_12345") -> bool:
        """Test the login flow on the desktop app."""
        print("\n Testing Login Flow")

        if not self.helper:
            raise RuntimeError("Test runner not started")

        # Wait for login screen
        async def wait_for_login():
            self._log("Waiting for login screen...")
            if not await self.helper.wait_for_screen("Login", timeout=30000):
                raise RuntimeError("Login screen did not appear")
            self._log(f"Current screen: {self.helper.current_screen}")

        await self.run_test("wait_for_login_screen", wait_for_login)

        # Reveal the local-credentials panel if the Login screen is a chooser.
        #
        # WINDOWS SHOWS A CHOOSER AND LINUX DOES NOT. The element tree on a
        # failing Windows run was:
        #
        #   screen='Login' elements=8
        #     btn_google_signin  btn_local_login  btn_login_reset_device
        #     btn_privacy_policy btn_server_status language_selector
        #     login_language_selector txt_owner_hint
        #
        # No input_username anywhere -- it is composed only after
        # btn_local_login is clicked. On Linux the same build lands straight on
        # the credential form, which is why this flow passed 6/6 here and failed
        # 5 of 6 there.
        #
        # desktop_app_helper.login() already probes for exactly this, but its
        # comment calls it an "iOS/Android landing page" and says "Desktop's
        # Login shows input_username directly". That is true of Linux desktop
        # and false of Windows desktop, and this step-by-step flow never had the
        # probe at all.
        async def reveal_local_login():
            if await self.helper.is_element_visible("input_username"):
                self._log("Login screen shows the credential form directly")
                return
            if not await self.helper.is_element_visible("btn_local_login"):
                await self._dump_tree("reveal_local_login")
                raise RuntimeError("Login screen has neither input_username nor btn_local_login")
            self._log("Login screen is a provider chooser — selecting local login")
            await self.helper.click("btn_local_login")
            await self.helper.wait_for_element("input_username", timeout=5000)

        await self.run_test("reveal_local_login", reveal_local_login)

        # Wait for username input
        async def wait_for_username_input():
            self._log("Waiting for username input...")
            # try/except, not `if not await ...`: wait_for_element RAISES on
            # timeout rather than returning False, so a truthiness check never
            # runs and the diagnostic below would be silently skipped -- which
            # is exactly what happened on the first attempt at this.
            try:
                found = await self.helper.wait_for_element("input_username", timeout=10000)
            except Exception:
                # Dump what IS on screen, then re-raise unchanged. "Element not
                # found" on its own cost a full Windows CI round trip to learn
                # nothing: the screen reported "Login" and the field was absent,
                # with no artifact saying what was actually composed. The tree
                # separates "a different screen variant rendered" from "nothing
                # rendered at all".
                await self._dump_tree("wait_for_username_input")
                raise
            if not found:
                await self._dump_tree("wait_for_username_input")
                raise RuntimeError("Username input not found")

        await self.run_test("wait_for_username_input", wait_for_username_input)

        # Enter username
        async def enter_username():
            self._log(f"Entering username: {username}")
            if not await self.helper.input_text("input_username", username):
                raise RuntimeError("Failed to enter username")

        await self.run_test("enter_username", enter_username)

        # Enter password
        async def enter_password():
            self._log(f"Entering password: {'*' * len(password)}")
            if not await self.helper.input_text("input_password", password):
                raise RuntimeError("Failed to enter password")

        await self.run_test("enter_password", enter_password)

        # Click login button
        async def click_login():
            self._log("Clicking login button...")
            if not await self.helper.click("btn_login_submit"):
                raise RuntimeError("Failed to click login button")

        await self.run_test("click_login_button", click_login)

        # Wait for next screen (Interact or Setup)
        async def wait_for_post_login():
            self._log("Waiting for post-login screen...")
            start = datetime.now()
            while (datetime.now() - start).total_seconds() < 30:
                screen = await self.helper.get_screen()
                if screen in ["Interact", "Setup", "Startup"]:
                    self._log(f"Navigated to: {screen}")
                    return
                await asyncio.sleep(0.5)
            raise RuntimeError(f"Still on Login screen after 30s")

        await self.run_test("wait_for_post_login", wait_for_post_login)

        # Return overall success
        return all(r.success for r in self.results)

    async def test_chat_flow(self, message: str = "Hello, can you hear me?") -> bool:
        """Test the chat interaction flow on the desktop app."""
        print("\n Testing Chat Flow")

        if not self.helper:
            raise RuntimeError("Test runner not started")

        # Wait for Interact screen
        async def wait_for_interact():
            self._log("Waiting for Interact screen...")
            if not await self.helper.wait_for_screen("Interact", timeout=30000):
                raise RuntimeError("Interact screen did not appear")

        await self.run_test("wait_for_interact_screen", wait_for_interact)

        # Wait for message input
        async def wait_for_input():
            self._log("Waiting for message input...")
            if not await self.helper.wait_for_element("input_message", timeout=10000):
                raise RuntimeError("Message input not found")

        await self.run_test("wait_for_message_input", wait_for_input)

        # Enter message
        async def enter_message():
            self._log(f"Entering message: {message}")
            if not await self.helper.input_text("input_message", message):
                raise RuntimeError("Failed to enter message")

        await self.run_test("enter_message", enter_message)

        # Baseline BEFORE sending: the TEXTS already on screen, not a count.
        #
        # A COUNT CANNOT ANSWER THE QUESTION. Sending adds the user's OWN message
        # bubble to the composed tree, so "the tree grew" becomes true the instant
        # the echo renders — before the agent has done anything. That is exactly
        # what shipped: a CI run passed `wait_for_response` in 1005ms against a
        # screen showing one message, the user's, still displaying its pending
        # indicator. The screenshot is the only reason anyone noticed.
        #
        # Texts, not elements, because the reply is CONTENT: something must appear
        # that we did not put there.
        def _texts(els) -> set:
            return {e.text.strip() for e in els if getattr(e, "text", None) and e.text.strip()}

        baseline_texts = _texts(await self.helper.get_elements())

        # PRE-SEND HISTORY BASELINE. Without one, "an agent row exists" is
        # satisfied by a row left over from an earlier interaction, so the
        # assertion could pass on a conversation this run never had. Captured
        # before the click, for the same reason the text baseline is.
        import httpx

        _args = _LAST_ARGS
        api_port = getattr(_args, "api_port", None) or 8080
        username = getattr(_args, "username", None) or "admin"
        password = getattr(_args, "password", None) or "qa_test_password_12345"
        api_base = f"http://127.0.0.1:{api_port}"
        if not getattr(_args, "username", None):
            self._log(f"WARNING: no --username given; falling back to '{username}'")
        self._log(f"Asserting reply via {api_base}/v1/agent/history as '{username}'")

        async def _history(client, headers):
            r = await client.get(f"{api_base}/v1/agent/history?limit=50", headers=headers)
            r.raise_for_status()
            return r.json()["data"]["messages"]

        _http = httpx.AsyncClient(timeout=30.0)
        _r = await _http.post(
            f"{api_base}/v1/auth/login", json={"username": username, "password": password}
        )
        _r.raise_for_status()
        _headers = {"Authorization": f"Bearer {_r.json()['access_token']}"}
        try:
            baseline_ids = {m.get("id") for m in await _history(_http, _headers)}
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            self._log(f"pre-send history unavailable ({type(exc).__name__}); baseline empty")
            baseline_ids = set()
        self._log(f"History baseline: {len(baseline_ids)} existing message(s)")


        # Click send button
        async def click_send():
            self._log("Clicking send button...")
            if not await self.helper.click("btn_send"):
                raise RuntimeError("Failed to click send button")

        await self.run_test("click_send_button", click_send)

        async def wait_for_response():
            """The agent must actually answer — asserted through /v1/agent/history.

            WHY NOT THE SCREEN, AFTER THREE ATTEMPTS TO MAKE THE SCREEN WORK.

            `/tree` is keyed on testTag: `desktop_app_helper.get_elements()` reads
            `elem["testTag"]` for every entry, so the endpoint only reports TAGGED
            composables. The chat transcript is not tagged, so no message bubble —
            ours or the agent's — is visible to automation at all.

            That is not a theory. Run 33509242206 failed with

                Text on screen at failure: <nothing new at all — the echo did not
                render either>

            while the screenshot from that same instant shows both bubbles:

                You    Hello, can you hear me?                     12:45 PM
                CIRIS  Hello! Yes, I can hear you. How can I …     12:46 PM

            Every text-diffing version of this check was therefore measuring an
            empty set, and the two earlier "fixes" (a longer deadline, a narrower
            blocklist) were adjustments to a signal that was never there. The
            transcript being untagged is a real gap in the client's test surface
            and is filed upstream; it is not something this gate can wait out.

            So assert where the content actually is. `/v1/agent/history` returns
            ConversationMessage with `is_agent`, which is the fact under test —
            "the agent produced an answer to what the UI sent" — and it cannot be
            satisfied by chrome, by our own echo, or by a placeholder, because
            those are not agent-authored rows.

            The screenshot remains the human-facing evidence that it RENDERED;
            this is the machine-checkable evidence that it EXISTS.
            """
            sent = message.strip()

            try:
                last_seen: list = []

                async def _poll_for_reply() -> bool:
                    """One deadline's worth of polling. True if the agent answered."""
                    nonlocal last_seen
                    deadline = datetime.now() + timedelta(seconds=RESPONSE_DEADLINE_SECONDS)
                    while datetime.now() < deadline:
                        await asyncio.sleep(2.0)
                        try:
                            msgs = await _history(_http, _headers)
                        except (httpx.HTTPError, KeyError, ValueError) as exc:
                            self._log(f"history poll failed (retrying): {type(exc).__name__}: {exc}")
                            continue
                        last_seen = msgs
                        replies = [m for m in msgs if _is_new_agent_reply(m, baseline_ids, sent)]
                        if replies:
                            reply = replies[-1]["content"].strip()
                            elapsed = RESPONSE_DEADLINE_SECONDS - (deadline - datetime.now()).total_seconds()
                            self._log(f'Agent replied after {elapsed:.1f}s: "{reply[:100]}"')
                            return True
                    return False

                # ONE RETRY, FOR PROVIDER RATE LIMITING ONLY.
                #
                # Three platforms drive one OpenRouter key concurrently, and a Windows run
                # failed with exactly this and nothing else:
                #     [error] Rate limited by openai_compatible_primary. Retrying in 6.7s...
                #     [error] LLM call failed (InstructorRetryException)
                # The agent behaved correctly — it reported the provider failure instead of
                # inventing an answer — so failing the release gate there grades our
                # shipping decision on someone else's quota.
                #
                # It cannot mask a real fault: a silent agent produces no new rows and a
                # genuine DMA error carries no rate-limit text, so neither matches and both
                # still fail on the first deadline.
                if not await _poll_for_reply():
                    fresh_now = [m for m in last_seen if m.get("id") not in baseline_ids]
                    if any(
                        m.get("message_type") in ("error", "system")
                        and "rate limit" in (m.get("content") or "").lower()
                        for m in fresh_now
                    ):
                        self._log(
                            f"provider rate-limited within {RESPONSE_DEADLINE_SECONDS}s — "
                            "resending once; this is quota, not the agent"
                        )
                        # `.update()`, NOT `|=`. An augmented assignment BINDS the name in
                        # this scope, so `baseline_ids` — defined in the enclosing function
                        # — became a local read before assignment:
                        #     cannot access free variable 'baseline_ids' where it is not
                        #     associated with a value in enclosing scope
                        # which failed the Windows platform at runtime. `.update()` mutates
                        # the same set without rebinding anything.
                        baseline_ids.update(m.get("id") for m in last_seen if m.get("id"))
                        resent = await self.helper.input_text("input_message", message) and await self.helper.click(
                            "btn_send"
                        )
                        if resent and await _poll_for_reply():
                            return
                        if not resent:
                            self._log("resend failed — reporting the original result")
                else:
                    return

                fresh = [m for m in last_seen if m.get("id") not in baseline_ids]
                self._log(f"Conversation at failure: {len(last_seen)} message(s), {len(fresh)} new:")
                for m in fresh[-8:]:
                    self._log(f"    | [{m.get('message_type', '?')}] {(m.get('content') or '')[:110]}")
                if not fresh:
                    self._log("    | <nothing new — the message never reached the agent>")
                errored = [m for m in fresh if m.get("message_type") in ("error", "system")]
                extra = (
                    f"\n        {len(errored)} error/system row(s) arrived INSTEAD of an answer —"
                    "\n        the agent was reached and failed, rather than staying silent."
                    if errored
                    else ""
                )
                raise RuntimeError(
                    f"No new agent reply within {RESPONSE_DEADLINE_SECONDS}s.{extra}\n"
                    "        The UI sent the message and /v1/agent/history shows no NEW\n"
                    "        message_type=='agent' row, so the agent did not answer.\n"
                    "        NOTE: this does NOT prove the reply rendered on screen — the\n"
                    "        transcript is absent from /tree (CIRISClient#27); the\n"
                    "        screenshot is the only client-side evidence.\n"
                    "        Check the LLM is configured and the agent log for DMA errors."
                )
            finally:
                await _http.aclose()

        await self.run_test("wait_for_response", wait_for_response)

        return all(r.success for r in self.results)

    # The message checkLlmConfig returns when state.llmApiKey is BLANK — the
    # signature of the stale-click-closure regression: the field visibly holds a
    # key, the automation clicked Test Connection, and the handler read a frozen
    # snapshot from before the key existed. If this text appears while we KNOW
    # we entered a key, the registered handler is stale, full stop.
    _BLANK_KEY_MESSAGE = "Enter an API key"

    async def _gate_verdict(self) -> str:
        """Whatever the app says about the AGENT/NODE gate, for the no-AI-screen error.

        THIS WAS A CALL WITH NO DEFINITION. Added in 2.9.42 on an error path that
        only runs when the AI screen is missing, so it never executed — until a
        client bump made an earlier step fail, and then the diagnostic built to
        explain the failure raised

            NameError: name '_gate_verdict' is not defined

        replacing the explanation with a stack trace at exactly the moment it was
        needed. An error path that never runs is not a diagnostic; it is a second
        failure waiting for the first.

        Best-effort by construction: a build exposing no gate surface must still
        get the surrounding message, so this says so rather than raising.
        """
        try:
            elements = await self.helper.get_elements()
        except Exception as exc:  # noqa: BLE001
            return f"          (could not read the UI tree: {type(exc).__name__})\n"

        prefixes = ("txt_gate", "txt_client_mode", "txt_node", "txt_agent_mode", "txt_mode")
        lines = [
            f"          {e.test_tag} = {e.text.strip()[:110]}"
            for e in elements
            if getattr(e, "text", None)
            and e.text.strip()
            and any(e.test_tag.startswith(pfx) for pfx in prefixes)
        ]
        if not lines:
            return (
                "          (the app exposed no gate/clientMode surface — either this "
                "build predates it,\n           or the screen never rendered)\n"
            )
        return "\n".join(sorted(lines)) + "\n"

    async def _llm_verdict_texts(self) -> dict:
        """testTag -> text for the AI step's verdict surfaces (txt_llm_*)."""
        assert self.helper is not None
        out = {}
        for e in await self.helper.get_elements():
            if e.test_tag.startswith("txt_llm_") and e.text:
                out[e.test_tag] = e.text
        return out

    async def _drive_llm_step_byok(
        self,
        provider: str,
        api_key: str,
        model: Optional[str],
        expect_key_rejected: bool = False,
        require_live_models: bool = False,
    ) -> None:
        """Drive the AI step's BYOK path: provider → key → Test Connection → model.

        Since 2.9.30 (#1062) the model field is adaptive. Once a valid key +
        Test Connection yields a live model list, the free-text
        ``input_llm_model_text`` is replaced by a dropdown (``input_llm_model``
        anchor + one ``menu_model_<sanitized-id>`` per model). The live list
        only appears AFTER btn_test_connection runs the shared checkLlmConfig
        probe, so we must click it (it is now testableClickable, the fix under
        test) before waiting for the dropdown. Falls back to the text field
        when no live list appears.
        """
        assert self.helper is not None

        def _model_tag(model_id: str) -> str:
            # Mirror SetupScreen.kt: menu_model_${id.replace("/","_").replace(":","_")}
            return model_id.replace("/", "_").replace(":", "_")

        async def _tags() -> set:
            return {e.test_tag for e in await self.helper.get_elements()}

        self._log(f"AI (BYOK): provider={provider} model={model or '(auto)'}")

        # 1. Provider.
        if not await self.helper.click("input_llm_provider"):
            raise RuntimeError("Failed to open LLM provider dropdown")
        if not await self.helper.wait_for_element(f"menu_provider_{provider}", timeout=4000):
            raise RuntimeError(f"menu_provider_{provider} not found in provider dropdown")
        await self.helper.click(f"menu_provider_{provider}")
        await asyncio.sleep(0.3)

        # 2. API key.
        if not await self.helper.input_text("input_api_key", api_key):
            raise RuntimeError("Failed to enter API key (input_api_key)")
        await asyncio.sleep(0.3)

        # 3. Test Connection — populates the live-model dropdown (the fix: this
        #    button is now testableClickable, so /click can fire it). Retry it a
        #    few times: on a freshly-wiped node the backend/node can still be
        #    warming when the first probe fires, so listModels throws and no
        #    dropdown appears. Each attempt re-runs the whole checkLlmConfig.
        model_tag = _model_tag(model) if model else ""
        for attempt in range(1, 6):
            if not await self.helper.click("btn_test_connection"):
                raise RuntimeError(
                    "Failed to click btn_test_connection — is the app built with the " "testableClickable fix? (#1062)"
                )
            self._log(f"AI (BYOK): Test Connection attempt {attempt}/5")
            await asyncio.sleep(3)  # let one checkLlmConfig produce its verdict rows

            verdicts = await self._llm_verdict_texts()
            blob = " | ".join(verdicts.values())
            if self._BLANK_KEY_MESSAGE in blob:
                # We ENTERED a key; the handler saw none. Do not retry — every
                # retry replays the same frozen closure and the old runner
                # "fell back to the text field" and PASSED, which is exactly how
                # this shipped. Fail loudly with the mechanism named.
                raise RuntimeError(
                    "STALE CLICK CLOSURE regression: Test Connection ran with an EMPTY api key while "
                    f"input_api_key holds one (verdict: {blob!r}). The automation registry is serving a "
                    "handler captured before the key was typed — see "
                    "TestAutomation.desktop.kt testableClickable/rememberUpdatedState."
                )
            if expect_key_rejected:
                # Synthetic-key CI mode: the PASS is the provider refusing the
                # credential — proof the key REACHED the wire. No dropdown will
                # ever appear, so return on the auth-class verdict.
                lowered = blob.lower()
                if any(w in lowered for w in ("rejected", "auth", "invalid", "key", "credit", "unauthorized")):
                    self._log(f"AI (BYOK): synthetic key correctly refused by the provider ({blob!r})")
                    return
                self._log(f"AI (BYOK): no auth verdict yet (attempt {attempt}): {blob!r}")

            # One checkLlmConfig cycle (validate + listModels) is a few seconds;
            # give it up to 18s to surface the dropdown before retrying.
            inner_deadline = time.time() + 18
            while time.time() < inner_deadline:
                tags = await _tags()
                if "input_llm_model" in tags:
                    await self.helper.click("input_llm_model")
                    await asyncio.sleep(0.6)
                    menu = sorted(t for t in await _tags() if t.startswith("menu_model_"))
                    if model_tag and f"menu_model_{model_tag}" in menu:
                        await self.helper.click(f"menu_model_{model_tag}")
                        self._log(f"AI (BYOK): selected requested model {model!r} from live dropdown")
                    elif model_tag:
                        # ASKED FOR A MODEL AND IT IS NOT THERE. Silently taking
                        # another one means the run reports on a model nobody chose.
                        raise RuntimeError(
                            f"requested model {model!r} is not in the live dropdown "
                            f"({len(menu)} offered). Refusing to substitute: a gate that "
                            f"quietly tests a different model than the one pinned is "
                            f"reporting on something nobody selected."
                        )
                    elif menu:
                        # LAST RESORT, AND IT IS A REAL RISK. The list is sorted, so
                        # this takes whatever is alphabetically first — on OpenRouter
                        # that is `aion-labs/aion-2.0`, which MANDATES reasoning and
                        # answers HTTP 400 to every call CIRIS makes. A whole gate run
                        # failed that way, reporting "no reply rendered" for a model it
                        # had picked for itself.
                        #
                        # Kept for suites with no pinned model, but it now says loudly
                        # that the choice was arbitrary.
                        await self.helper.click(menu[0])
                        self._log(
                            f"AI (BYOK): no --llm-model pinned; taking {menu[0]}, the FIRST of "
                            f"{len(menu)} models in alphabetical order. This is arbitrary — if the "
                            f"run fails with provider 4xx, pin a known-good model instead."
                        )
                    else:
                        self._log("AI (BYOK): model dropdown present but empty; provider default stands")
                    return
                await asyncio.sleep(1)
            # No dropdown this cycle. Let the node warm before the next attempt.
            self._log(f"AI (BYOK): no live list on attempt {attempt}; node may be warming, retrying")
            await asyncio.sleep(4)

        if expect_key_rejected:
            raise RuntimeError(
                "expected the provider to REJECT the synthetic key, but no auth-class verdict ever "
                "rendered — either the request never reached the provider or the verdict surfaces "
                "(txt_llm_*) are missing from this build."
            )
        if require_live_models:
            # A REAL key was supplied, so the live dropdown is the contract.
            # The permissive text-fallback below is what let the stale-closure
            # regression pass CI-shaped runs silently: no dropdown, type the
            # model by hand, setup "succeeds". With a working key that fallback
            # is indistinguishable from the bug, so in strict mode it is one.
            verdicts = await self._llm_verdict_texts()
            raise RuntimeError(
                "live model dropdown never appeared with a REAL key after 5 Test Connection "
                f"attempts (verdicts: {verdicts!r}) — the BYOK path is broken; refusing the "
                "text-field fallback because it would report this as a pass."
            )

        # 4. Still no live list after retries → text fallback so setup can finish.
        tags = await _tags()
        if "input_llm_model_text" in tags and model:
            await self.helper.input_text("input_llm_model_text", model)
            self._log(f"AI (BYOK): typed model {model!r} into text field (no live list appeared)")
        else:
            self._log("AI (BYOK): no live model list appeared after retries; leaving provider/text default")

    async def test_setup_wizard_flow(
        self,
        username: str = "admin",
        password: str = "qa_test_password_12345",
        fed_label: Optional[str] = None,
        announce: bool = True,
        trace_opt_in: bool = True,
        age_band: str = "adult",
        llm_provider: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_key_expect_rejected: bool = False,
        llm_require_live_models: bool = False,
    ) -> bool:
        """Drive the first-run setup wizard via the test server.

        2.9.14 first-run order (SetupState.nextSetupStep):

            YOU → JOIN_FEDERATION → [AI] → COMPLETE

        Three screens, one question each. The AI screen appears only on AGENT
        builds (CIRISBuild.HAS_AGENT); the node client goes straight to COMPLETE
        after the consent screen.

        Screen 1 (YOU) carries what used to be four screens — the fed-ID name
        (`input_fedid_label`), the local account (`input_username` /
        `input_password` / `input_password_confirm`) and the age band
        (`age_band_*`). Screen 2 (JOIN_FEDERATION) carries the consent toggles,
        which are now REACHABLE on every path (through 2.9.13 the trace checkbox
        lived on a step nothing routed to):
          - `toggle_announce_ownership` — announce, ON by default
          - `toggle_trace_opt_in`       — send traces (consent:replication:v1)
          - `toggle_trace_analyze`      — be scored (CC#46 analyze)
          - `toggle_share_location`     — rough location, OFF by default

        Requires the desktop app to be sitting on the Setup wizard (backend
        in first-run mode). Use `desktop-setup --launch` to bring that up.
        """
        print("\n Testing Setup Wizard Flow (first-run, 3 screens)")

        if not self.helper:
            raise RuntimeError("Test runner not started")

        if fed_label is None:
            fed_label = f"qa-node-{int(time.time())}"

        # ── Step 0: land on the Setup wizard ──────────────────────────
        async def wait_for_setup():
            """First run now starts at LOGIN, not at the wizard (#1055).

            The Login screen used to be auto-skipped on first run because
            `googleSignInCallback == null` was read as "no OAuth configured" --
            untrue once the browser-handoff flow landed. With that fixed, a fresh
            install lands on a provider chooser:

                screen = Login
                  btn_google_signin  btn_local_login  btn_login_reset_device
                  btn_privacy_policy btn_server_status language_selector

            and the wizard only appears after a sign-in method is chosen.

            This is also the answer to the Windows/Linux divergence I chased
            earlier today: Windows was already showing this chooser while Linux
            went straight to the form. They agree now -- and the behaviour they
            agree on is the Windows one, so the harness needs it on every
            platform rather than as a Windows special case.
            """
            self._log("Waiting for Setup wizard...")

            # POLL TO A DEADLINE rather than waiting for one screen then peeking
            # at another. The first version of this waited 8s for Setup and then
            # checked for Login — so a boot that was still on 'Startup' matched
            # neither and failed instantly, where the original 30s wait had
            # simply outlasted it. That is a timing regression I introduced
            # while adding the chooser handling, and it only showed on a cold
            # Windows runner.
            #
            # 'Startup' is a transient splash: keep waiting. 'Login' is terminal
            # and actionable: click through. 'Setup' is the goal.
            deadline = time.time() + 45
            screen = ""
            clicked_local = False
            while time.time() < deadline:
                screen = await self.helper.get_screen() or ""
                if screen == "Setup":
                    return
                if screen == "Login" and not clicked_local:
                    if await self.helper.is_element_visible("btn_local_login"):
                        self._log("first run starts at the Login chooser — selecting local signup")
                        await self.helper.click("btn_local_login")
                        clicked_local = True
                    elif await self.helper.is_element_visible("input_username"):
                        # Already configured: this is a login screen, not first
                        # run. Caller's problem, but say which it was.
                        break
                await asyncio.sleep(0.5)

            await self._dump_tree("wait_for_setup_wizard")
            raise RuntimeError(f"Setup wizard did not appear within 45s (last screen '{screen}')")

        await self.run_test("wait_for_setup_wizard", wait_for_setup)

        # ── Screen 1: YOU (fed-ID name + account + age band) ──────────
        async def you_step():
            """Drive YOU in its current order: Age -> Account -> Federation identity.

            AGE LEADS AND IS REQUIRED (#1055). SetupFormState.canAdvance now gates
            YOU on `ageRange.selectedBandToken != null`, because the band seeds the
            fed-ID and the minor-stewardship gate -- nothing below it can be judged
            until it is answered.

            This step used to fill the fed-ID label first and click the age band
            LAST, behind `if is_element_visible(...)`, so a band that had not
            rendered yet was silently skipped. That is now unadvanceable, and the
            old shape would have reported a PASS anyway: clicking btn_next
            "succeeds" as a click even when the wizard refuses to move, and the
            failure only surfaced one step later as a confusing "the consent screen
            has no toggles". Order fixed, and the skip made loud.
            """
            self._log(f"YOU: band={age_band}, username={username}, fed-ID label={fed_label}")

            # 1. AGE — first, required, and never silently skipped.
            band_tag = f"age_band_{age_band}"
            if not await self.helper.wait_for_element(band_tag, timeout=10000):
                await self._dump_tree("you_step:age")
                raise RuntimeError(f"{band_tag} not found — YOU cannot advance without an age band")
            await self.helper.click(band_tag)
            await asyncio.sleep(0.2)

            # 2. ACCOUNT — local username/password render only for non-OAuth
            # signup (showLocalUserFields()), so probe rather than assume.
            if await self.helper.is_element_visible("input_username"):
                await self.helper.input_text("input_username", username)
                await self.helper.input_text("input_password", password)
                await self.helper.input_text("input_password_confirm", password)
            else:
                self._log("no local account fields (OAuth signup) — skipping credentials")

            # 3. FEDERATION IDENTITY — the label now AUTO-DERIVES from the
            # username / OAuth id and is only overridden when the user edits it.
            # Setting it explicitly keeps runs identifiable and still exercises
            # the manual-edit path (labelManuallyEdited).
            if await self.helper.is_element_visible("input_fedid_label"):
                await self.helper.input_text("input_fedid_label", fed_label)

            await asyncio.sleep(0.3)
            if not await self.helper.click("btn_next"):
                raise RuntimeError("Failed to click btn_next on screen 1 (YOU)")

            # VERIFY IT ACTUALLY ADVANCED. A click that lands but does not move
            # the wizard is the exact shape that made this pass while leaving the
            # run broken -- the same lesson as the .env assertion that passed
            # while asserting nothing. If YOU is unsatisfied, say so here, where
            # the cause is, instead of two steps downstream.
            #
            # POLL, don't one-shot: on the Windows CI runner the transition
            # takes ~1s, and a fixed 0.5s sleep flagged a wizard that advanced
            # 300ms after the check (join_federation then passed immediately).
            deadline = asyncio.get_event_loop().time() + 10.0
            while await self.helper.is_element_visible(band_tag):
                if asyncio.get_event_loop().time() > deadline:
                    await self._dump_tree("you_step:did-not-advance")
                    raise RuntimeError(
                        "still on the YOU step 10s after btn_next — a required field is "
                        "unsatisfied (age band, account, or fed-ID label)"
                    )
                await asyncio.sleep(0.5)

        await self.run_test("you_step", you_step)

        # ── Screen 2: JOIN_FEDERATION (consent) ───────────────────────
        # The regression this guards: through 2.9.13 NO path reached a trace
        # consent control, so no production node could ever ship a trace.
        async def consent_step():
            self._log("JOIN_FEDERATION: waiting for toggle_announce_ownership")
            if not await self.helper.wait_for_element("toggle_announce_ownership", timeout=15000):
                raise RuntimeError("toggle_announce_ownership not found on the consent screen")
            # WAIT FOR IT — the two toggles do not arrive together. Announce is
            # local state and paints immediately; the trace grant is rendered
            # from `GET /v1/setup/consent-disclosure`, so on a loaded runner it
            # lands seconds later. A one-shot is_element_visible here read that
            # gap as the 2.9.13 sealed-consent regression and failed a build
            # whose consent screen was fine (same race as you_step, one screen
            # further on). A genuine regression still fails, 15s later.
            if not await self.helper.wait_for_element("toggle_trace_opt_in", timeout=15000):
                await self._dump_tree("join_federation:no-trace-toggle")
                raise RuntimeError(
                    "toggle_trace_opt_in is not reachable on the consent screen 15s after "
                    "the announce toggle — this is the 2.9.13 sealed-consent regression "
                    "(the disclosure carried no `replication` grant)"
                )
            if not announce:
                await self.helper.click("toggle_announce_ownership")
            if not trace_opt_in:
                await self.helper.click("toggle_trace_opt_in")
            await asyncio.sleep(0.3)
            if not await self.helper.click("btn_next"):
                raise RuntimeError("Failed to click btn_next on screen 2 (JOIN_FEDERATION)")
            await asyncio.sleep(0.5)

        await self.run_test("join_federation", consent_step)

        # ── Screen 3: AI (agent build only; final step there) ─────────
        async def ai_step():
            self._log("Probing for the AI screen (agent builds only)")
            # 20s, not 6s: the same CI runner has taken 18.8s just to paint the
            # wizard's first screen. At 6s a loaded agent build looks exactly
            # like a node-client build that has no AI screen at all, and the run
            # walks past the whole LLM step reporting nothing wrong.
            # REQUIRED, not probed. This repo builds the AGENT: it is the brain,
            # it needs an LLM, and a wizard that never offers to configure one has
            # not set the product up. Tolerating absence here is what let the
            # whole LLM step vanish silently while the run still reported 4/5.
            #
            # If it is missing, the cause is almost never the screen. It is
            # clientMode: the client resolves NODE when it cannot read the node's
            # `folded`/`reachable`, and a node has no brain to configure. So say
            # that, rather than making the operator rediscover it.
            if not await self.helper.wait_for_optional_element("input_llm_provider", timeout=20000):
                raise RuntimeError(
                    "No AI screen. This build is the AGENT and MUST offer LLM "
                    "configuration.\n"
                    "        The app's own verdict:\n"
                    + await self._gate_verdict()
                    + "        AGENT requires folded && reachable && !veto. folded and "
                    "reachable come from the NODE\n"
                    "        (CIRIS_NODE_URL, :4243 `agent` block); role and services "
                    "come from the BRAIN (CIRIS_API_URL).\n"
                    "        A node has no brain to configure, so clientMode=NODE means "
                    "no AI screen."
                )
            if llm_api_key:
                # BYOK path (#1062): real provider + key + Test Connection +
                # live-model dropdown. This exercises the accommodation that
                # made btn_test_connection reachable by automation.
                await self._drive_llm_step_byok(
                    llm_provider or "openrouter",
                    llm_api_key,
                    llm_model,
                    expect_key_rejected=llm_key_expect_rejected,
                    require_live_models=llm_require_live_models,
                )
            elif await self.helper.is_element_visible("btn_use_free_ai"):
                # CIRIS-hosted proxy option (OAuth path) — no key entry needed.
                self._log("AI: choosing CIRIS-hosted option (btn_use_free_ai)")
                if not await self.helper.click("btn_use_free_ai"):
                    raise RuntimeError("Failed to click btn_use_free_ai on the AI screen")
            else:
                # Keyless "local" (Ollama) provider — satisfies gating without a
                # real key; the --mock-llm backend ignores the values anyway.
                self._log("AI: selecting keyless 'local' provider")
                if not await self.helper.click("input_llm_provider"):
                    raise RuntimeError("Failed to open LLM provider dropdown")
                if not await self.helper.wait_for_element("menu_provider_local", timeout=4000):
                    raise RuntimeError("menu_provider_local not found in provider dropdown")
                if not await self.helper.click("menu_provider_local"):
                    raise RuntimeError("Failed to select menu_provider_local")
            await asyncio.sleep(0.3)
            # On the agent build this is the FINAL step: btn_next self-claims and
            # advances to COMPLETE.
            if not await self.helper.click("btn_next"):
                raise RuntimeError("Failed to click btn_next (finish) on the AI screen")
            await asyncio.sleep(1.0)

        await self.run_test("ai_configuration", ai_step)

        # ── Step 5: COMPLETE (best-effort — CompleteStep is in SetupScreen) ──
        async def wait_for_complete():
            self._log("Waiting for setup to complete (leave wizard / COMPLETE step)")
            start = datetime.now()
            while (datetime.now() - start).total_seconds() < 20:
                screen = await self.helper.get_screen()
                # Either routed out of Setup, or on the COMPLETE step (still
                # "Setup" screen but btn_next is gone).
                if screen and screen != "Setup":
                    self._log(f"Left wizard → {screen}")
                    return
                if not await self.helper.is_element_visible("btn_next"):
                    self._log("On COMPLETE step (btn_next gone)")
                    return
                await asyncio.sleep(0.5)
            # NOT "non-fatal: record where we ended up". Reaching COMPLETE is the
            # entire point of the step, and logging that it did not happen while
            # returning success is how a run reports 5/5 on a wizard that never
            # finished.
            raise RuntimeError(
                "Setup did not reach COMPLETE within 20s: still on the Setup screen "
                "with btn_next present.\n"
                "        The wizard was driven to the end and did not finish."
            )

        await self.run_test("setup_complete", wait_for_complete)

        async def claim_settled():
            """The node must actually be CLAIMED, not merely left behind.

            The app self-claims local node ownership on the final step and logs
            the outcome. When it cannot read the one-time PIN it logs
            `claim_settled claimed=false` and completes setup anyway, leaving an
            UNCLAIMED node — and every UI-level check still passes, because the
            wizard did reach COMPLETE.

            That is exactly what happened: the node wrote its PIN into the
            backend's CIRIS_HOME while the app waited on a different directory.
            Both halves looked healthy; the ownership was simply never taken.
            """
            log = temp_path("ciris_desktop_setup.log")
            try:
                with open(log, "r", encoding="utf-8", errors="replace") as fh:
                    lines = [ln for ln in fh if "claim_settled" in ln]
            except OSError:
                self._log("claim outcome not observable (no desktop app log) — skipping")
                return
            if not lines:
                self._log("no claim_settled line — app build may predate it; skipping")
                return
            verdict = lines[-1].strip()
            if "claimed=true" not in verdict:
                raise RuntimeError(
                    "Setup completed with the node UNCLAIMED.\n"
                    f"        {verdict}\n"
                    "        The claim PIN is written by the node into ITS CIRIS_HOME; the app "
                    "reads it from the home IT was given.\n"
                    "        If those differ, the PIN is unreadable and ownership is silently "
                    "never taken."
                )
            self._log("node ownership claimed")

        await self.run_test("claim_settled", claim_settled)

        return all(r.success for r in self.results)

    async def test_catchup_add_fedid_flow(
        self,
        fed_label: Optional[str] = None,
        announce: bool = True,
        trace_opt_in: bool = True,
    ) -> bool:
        """Drive the catch-up "Add Federation ID" flow (AddFederationIdScreen).

        For an already-logged-in legacy node (password/OAuth ROOT, no fed-ID).
        Entry point is `btn_add_federation_id` on the Manage Nodes surface
        (this REPLACED the old `btn_upgrade_to_fed_id`). The guided screen then
        drives:

            input_fed_label → toggle_announce_ownership
            → toggle_trace_opt_in (gated on announce) → btn_add_fedid_confirm

        Note: the catch-up label field/confirm use `input_fed_label` /
        `btn_add_fedid_confirm` (distinct from the first-run wizard's
        `input_fedid_label`). The back affordance is `btn_add_fedid_back`.

        Requires the app to be logged in with the Manage Nodes surface
        reachable AND the logged-in owner to have NO fed-ID yet: the client
        renders `btn_add_federation_id` only when `ownerHasFedId == false`
        (from the local node's `GET /v1/setup/owned-nodes`); `null` — e.g. a
        backend that doesn't serve owned-nodes, like the host ciris_engine QA
        backend — fail-closes the button hidden. If the entry point can't be
        reached, the flow SKIPs (tolerated, returns True) with a clear reason
        rather than failing, mirroring the federation walker's tolerated-SKIP
        semantics for state-dependent preconditions.
        """
        print("\n Testing Catch-up Add-Federation-ID Flow")

        if not self.helper:
            raise RuntimeError("Test runner not started")

        if fed_label is None:
            fed_label = f"qa-catchup-{int(time.time())}"

        # ── Reach the entry point ─────────────────────────────────────
        # Canonical path: EpistemicSidebar → Manage group (nav_group_manage)
        # → Nodes surface (nav_epistemic_nodes) → btn_add_federation_id.
        async def reach_entry():
            self._log("Looking for btn_add_federation_id (Manage Nodes surface)")
            if await self.helper.is_element_visible("btn_add_federation_id"):
                return
            # Expand the Manage group if the Nodes row isn't visible yet.
            if not await self.helper.is_element_visible("nav_epistemic_nodes"):
                if await self.helper.is_element_visible("nav_group_manage"):
                    self._log("Expanding sidebar group nav_group_manage")
                    await self.helper.click("nav_group_manage")
                    try:
                        await self.helper.wait_for_element("nav_epistemic_nodes", timeout=3000)
                    except Exception:  # noqa: BLE001
                        pass
            if await self.helper.is_element_visible("nav_epistemic_nodes"):
                self._log("Clicking nav_epistemic_nodes")
                await self.helper.click("nav_epistemic_nodes")
                try:
                    await self.helper.wait_for_element("btn_add_federation_id", timeout=5000)
                except Exception:  # noqa: BLE001
                    pass
                if await self.helper.is_element_visible("btn_add_federation_id"):
                    return
            # Fallback: scan the element tree for any Manage-Nodes-ish nav row.
            elements = await self.helper.get_elements()
            nav_candidates = [
                e.test_tag
                for e in elements
                if "node" in e.test_tag.lower() and ("nav" in e.test_tag.lower() or "manage" in e.test_tag.lower())
            ]
            for tag in nav_candidates:
                self._log(f"trying nav candidate: {tag}")
                await self.helper.click(tag)
                await asyncio.sleep(0.5)
                if await self.helper.is_element_visible("btn_add_federation_id"):
                    return
            raise RuntimeError(
                "btn_add_federation_id not reachable — navigate to the Manage "
                "Nodes surface first (logged-in legacy node required)"
            )

        entry = await self.run_test("reach_add_fedid_entry", reach_entry)
        if not entry.success:
            # TOLERATED SKIP: btn_add_federation_id renders only when the
            # logged-in owner has no fed-ID (ownerHasFedId == false). Any
            # other state — owner already has one, or the backend doesn't
            # serve GET /v1/setup/owned-nodes so the client fail-closes —
            # legitimately hides it. Don't hard-fail the run on that.
            self.results.pop()  # replace the FAIL record with a skip notice
            print(
                "  ⏭️  reach_add_fedid_entry SKIPPED (tolerated): "
                "btn_add_federation_id not rendered — owner already has a "
                "fed-ID, or ownerHasFedId is null (backend without "
                "GET /v1/setup/owned-nodes fail-closes the entry)"
            )
            return all(r.success for r in self.results)

        async def open_catchup():
            self._log("Clicking btn_add_federation_id → AddFederationIdScreen")
            if not await self.helper.click("btn_add_federation_id"):
                raise RuntimeError("Failed to click btn_add_federation_id")
            if not await self.helper.wait_for_element("input_fed_label", timeout=6000):
                raise RuntimeError("input_fed_label did not appear (catch-up screen)")

        await self.run_test("open_add_fedid_screen", open_catchup)

        async def enter_label():
            self._log(f"input_fed_label = {fed_label}")
            await self.helper.input_text("input_fed_label", fed_label)
            await asyncio.sleep(0.2)

        await self.run_test("catchup_enter_label", enter_label)

        async def trace_gated_off():
            self._log("Asserting toggle_trace_opt_in hidden while announce OFF (catch-up)")
            if await self.helper.is_element_visible("toggle_trace_opt_in"):
                raise RuntimeError("toggle_trace_opt_in visible before announce ON (catch-up gating broken)")

        await self.run_test("catchup_trace_gated_off", trace_gated_off)

        if announce:

            async def announce_on():
                self._log("Clicking toggle_announce_ownership → ON (catch-up)")
                if not await self.helper.click("toggle_announce_ownership"):
                    raise RuntimeError("Failed to click toggle_announce_ownership")
                if not await self.helper.wait_for_element("toggle_trace_opt_in", timeout=4000):
                    raise RuntimeError("toggle_trace_opt_in did not appear after announce ON (catch-up)")

            await self.run_test("catchup_announce_on", announce_on)

            if trace_opt_in:

                async def opt_in():
                    self._log("Clicking toggle_trace_opt_in → ON (catch-up)")
                    if not await self.helper.click("toggle_trace_opt_in"):
                        raise RuntimeError("Failed to click toggle_trace_opt_in")
                    await asyncio.sleep(0.2)

                await self.run_test("catchup_trace_opt_in_on", opt_in)

        async def confirm():
            self._log("Clicking btn_add_fedid_confirm")
            # btn_add_fedid_confirm uses testable() (position-only) in the
            # client, so /click may report not-clickable; record best-effort.
            clicked = await self.helper.click("btn_add_fedid_confirm")
            if not clicked:
                raise RuntimeError(
                    "btn_add_fedid_confirm not clickable via /click "
                    "(client uses testable(), not testableClickable())"
                )
            await asyncio.sleep(0.5)

        await self.run_test("catchup_confirm", confirm)

        return all(r.success for r in self.results)

    async def test_element_tree(self) -> bool:
        """Debug test - print current element tree."""
        print("\n Element Tree")

        if not self.helper:
            raise RuntimeError("Test runner not started")

        elements = await self.helper.get_elements()
        screen = await self.helper.get_screen()

        print(f"\nScreen: {screen}")
        print(f"Elements ({len(elements)}):")
        for elem in sorted(elements, key=lambda e: e.test_tag):
            print(f"  • {elem.test_tag:30s} at ({elem.center_x}, {elem.center_y})")

        return True

    def print_summary(self) -> None:
        """Print test summary."""
        passed = sum(1 for r in self.results if r.success)
        failed = sum(1 for r in self.results if not r.success)
        total = len(self.results)

        print(f"\n{'=' * 50}")
        print(f" Test Summary: {passed}/{total} passed")

        if failed > 0:
            print(f"\n[FAIL] Failed tests:")
            for r in self.results:
                if not r.success:
                    print(f"   • {r.name}: {r.error}")

        print(f"{'=' * 50}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CIRIS Desktop App / Web UI QA Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Desktop app testing (primary)
  %(prog)s desktop                       Test desktop app (show element tree)
  %(prog)s desktop-login                 Test login flow on desktop app
  %(prog)s desktop-chat                  Test chat flow on desktop app

  # Legacy browser-based testing
  %(prog)s e2e --wipe                    Full E2E test with clean slate
  %(prog)s setup --provider anthropic    Test setup wizard with Anthropic
  %(prog)s e2e --headless --mock-llm     Headless with mock LLM
        """,
    )

    # Commands
    parser.add_argument(
        "command",
        nargs="?",
        default="desktop",
        choices=[
            "desktop",
            "desktop-login",
            "desktop-chat",
            "desktop-setup",
            "desktop-catchup",
            "desktop-up",
            "federation",
            "e2e",
            "setup",
            "interact",
            "models",
            "licensed_agent",
            "list",
        ],
        help="Test command to run (default: desktop)",
    )

    # Server options
    parser.add_argument(
        "--wipe",
        action="store_true",
        default=True,
        help="Wipe all data before testing (clean slate) - enabled by default",
    )
    parser.add_argument(
        "--no-wipe",
        action="store_true",
        help="Don't wipe data (continue from existing state)",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock LLM (no API key needed)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Server port (default: 8080)",
    )

    # Desktop app options
    parser.add_argument(
        "--desktop-port",
        type=int,
        default=8091,
        help="Desktop app test automation server port (default: 8091)",
    )
    parser.add_argument(
        "--no-desktop",
        action="store_true",
        help="For desktop-up: start backend + setup admin, but don't launch the desktop app",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="Username for desktop login test (default: admin)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Password for desktop login test (default: qa_test_password_12345)",
    )
    parser.add_argument(
        "--message",
        default=None,
        help="Message for desktop chat test (default: 'Hello, can you hear me?')",
    )
    parser.add_argument(
        "--fed-label",
        default=None,
        help="Federation ID label for desktop-setup/desktop-catchup (default: generated qa-* name)",
    )
    parser.add_argument(
        "--no-announce",
        action="store_true",
        help="For desktop-setup/desktop-catchup: leave the announce decision OFF "
        "(privacy default; trace opt-in stays gated/hidden)",
    )
    parser.add_argument(
        "--no-trace-opt-in",
        action="store_true",
        help="For desktop-setup/desktop-catchup: announce but don't opt into reasoning traces",
    )
    # BYOK LLM options for the desktop-setup AI step. Without a key the AI step
    # takes the keyless 'local' provider (works with --mock-llm). With a key it
    # drives the real BYOK path: provider + key + Test Connection + live-model
    # dropdown (#1062).
    parser.add_argument(
        "--llm-provider",
        default=None,
        help="For desktop-setup: BYOK provider id (e.g. openrouter, groq, together). "
        "Omit for the keyless 'local' provider.",
    )
    parser.add_argument(
        "--llm-key",
        default=None,
        help="For desktop-setup: BYOK API key literal (prefer --llm-key-file).",
    )
    parser.add_argument(
        "--llm-require-live-models",
        action="store_true",
        help=(
            "Strict BYOK: a real key was supplied, so the live model dropdown MUST populate — "
            "the text-field fallback becomes a failure instead of a silent pass."
        ),
    )
    parser.add_argument(
        "--llm-key-expect-rejected",
        action="store_true",
        help=(
            "CI mode: the supplied key is SYNTHETIC and the pass is the provider refusing it — "
            "proof the key reached the wire. Guards the stale-click-closure regression without "
            "a real secret."
        ),
    )
    parser.add_argument(
        "--llm-key-file",
        default=None,
        help="For desktop-setup: file holding the BYOK API key (e.g. ~/.openrouter_key).",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="For desktop-setup: exact model id to select from the live dropdown "
        "(default: whatever the wizard auto-selects as recommended).",
    )

    # Browser options
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no window)",
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        help="Slow down browser actions by N milliseconds",
    )

    # LLM options
    parser.add_argument(
        "--provider",
        default="openrouter",
        choices=["openai", "anthropic", "openrouter", "groq", "google", "together", "local"],
        help="LLM provider (default: openrouter)",
    )
    parser.add_argument(
        "--api-key",
        help="API key (or set LLM_API_KEY env var, or use ~/.provider_key file)",
    )
    parser.add_argument(
        "--model",
        help="Specific model to select (default: auto-select recommended)",
    )

    # Portal options (for licensed_agent flow)
    parser.add_argument(
        "--portal-url",
        default="https://portal.ciris.ai",
        help="CIRIS Portal URL for device auth (default: https://portal.ciris.ai)",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=300,
        help="Timeout for Portal authorization polling in seconds (default: 300)",
    )

    # Test options
    parser.add_argument(
        "--tests",
        help="Comma-separated list of specific tests to run",
    )
    parser.add_argument(
        "--output-dir",
        default="web_ui_qa_reports",
        help="Directory for screenshots and reports",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Server startup timeout in seconds",
    )

    # Verbosity
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    # Keep open
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep browser and server running after tests (for demos)",
    )

    # Federation walk-test options
    parser.add_argument(
        "--launch",
        action="store_true",
        help="For federation: wipe + launch backend + desktop app before walking (full bring-up)",
    )
    parser.add_argument(
        "--json-report",
        default=None,
        help="For federation: write the FederationWalkReport JSON to this path",
    )
    parser.add_argument(
        "--platform",
        choices=["desktop", "android", "ios"],
        default=None,
        help=(
            "Which of the five targets to drive. THE SAME FLOW RUNS ON ALL OF THEM: "
            "one CIRISClient Compose app, one TestAutomationServer on 9091, so a "
            "command differs only in transport (desktop binds 9091 directly; android "
            "forwards adb 8091->9091; ios forwards 18091->9091). Applies to EVERY "
            "command, not just `federation`. Defaults to desktop. The older "
            "--android/--ios switches remain as aliases."
        ),
    )
    parser.add_argument(
        "--ios-udid",
        default="booted",
        help="For --platform ios: simulator UDID, or 'booted' for the running one (default).",
    )
    parser.add_argument(
        "--ios-app-path",
        default=None,
        help=(
            "For --platform ios: path to the built *.app for the SIMULATOR "
            "(-sdk iphonesimulator). Discovered from DerivedData when unset."
        ),
    )
    parser.add_argument(
        "--ios-physical",
        action="store_true",
        help=(
            "For --platform ios: target a physical device (devicectl/pymobiledevice3) "
            "instead of a simulator. CI uses the simulator — it needs no signing "
            "identity, provisioning profile or registered UDID."
        ),
    )
    parser.add_argument(
        "--screenshot-on-success",
        metavar="PATH",
        default=None,
        help=(
            "Capture the final screen to PATH when the run PASSES. Review material "
            "for the 5-platform gallery: a green tick says a reply rendered, a "
            "picture shows WHAT rendered. Never fails the run on its own."
        ),
    )
    parser.add_argument(
        "--android",
        action="store_true",
        help="For federation --launch: target an Android emulator instead of the desktop app. "
        "Starts/discovers an emulator, installs the debug APK, port-forwards 8091→9091, "
        "then runs the walk-test against the Android TestAutomationServer.",
    )
    parser.add_argument(
        "--android-avd",
        default="Medium_Phone_API_36.1_2",
        help="AVD name to boot when no emulator is running (default: Medium_Phone_API_36.1_2)",
    )
    parser.add_argument(
        "--android-device",
        default=None,
        help="Explicit ADB device serial to target (default: first emulator-* device)",
    )
    parser.add_argument(
        "--ios",
        action="store_true",
        help="For federation --launch: target a physical iOS device instead of the desktop app. "
        "Launches ai.ciris.mobile with CIRIS_TEST_MODE=true via devicectl, then iproxy-forwards "
        "host:18091→device:9091 (test server) and host:18080→device:8080 (embedded backend). "
        "Walk-test points at the forwarded ports.",
    )
    parser.add_argument(
        "--ios-device-id",
        default=None,
        help="For --ios: specific physical-device UDID (libimobiledevice). "
        "If unset, the first connected device is used.",
    )
    parser.add_argument(
        "--ios-bundle-id",
        default="ai.ciris.mobile",
        help="For --ios: bundle ID to launch (default: ai.ciris.mobile).",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=None,
        help="Backend API port the walk-test queries for state assertions. "
        "Defaults: 8080 for desktop/android, 18080 for --ios. Set explicitly to override.",
    )

    args = parser.parse_args()
    _reconcile_platform(args)
    _apply_platform_defaults(args)
    # Remembered so the capture wrapper can read --platform/--screenshot-on-success
    # without parsing argv a second time (which would diverge the moment a
    # command mutates its own args).
    global _LAST_ARGS
    _LAST_ARGS = args
    return args


#: The parsed args, kept so the success-capture wrapper can see them.
_LAST_ARGS: Optional[argparse.Namespace] = None


def _reconcile_platform(args: argparse.Namespace) -> None:
    """Make `--platform` and the legacy `--android`/`--ios` switches one fact.

    Both spellings exist because `--android`/`--ios` predate this and are wired
    into existing invocations; `--platform` is the one that applies to every
    command. Rather than have two sources of truth drift, they are collapsed here
    into BOTH representations, so downstream code can read whichever it already
    reads and get the same answer.
    """
    explicit = getattr(args, "platform", None)
    legacy_android = bool(getattr(args, "android", False))
    legacy_ios = bool(getattr(args, "ios", False))

    if explicit is None:
        args.platform = "android" if legacy_android else "ios" if legacy_ios else "desktop"
    elif (legacy_android and explicit != "android") or (legacy_ios and explicit != "ios"):
        # Contradicting yourself is a mistake worth surfacing, not silently
        # resolving in favour of whichever the code happens to read first.
        raise SystemExit(
            f"--platform {explicit} contradicts the legacy "
            f"--{'android' if legacy_android else 'ios'} switch; pass only one."
        )

    args.android = args.platform == "android"
    args.ios = args.platform == "ios"


def _apply_platform_defaults(args: argparse.Namespace) -> None:
    """Fill in port defaults that depend on the target platform.

    - desktop (default): test-server :9091 (bound DIRECTLY), API :8080
    - --android:          test-server :8091 forwards to device :9091; API :8080→8080
    - --ios:              test-server :18091→9091; API :18080→8080 (iproxy convention)

    Honors any explicit user override (--desktop-port / --api-port).
    """
    if getattr(args, "ios", False):
        # The 18xxx convention is for PHYSICAL devices only, where iproxy tunnels
        # over USB and the offset avoids colliding with a host backend. A
        # SIMULATOR shares the host network stack: the app's 9091 is reachable at
        # localhost:9091 with no forward at all, exactly like desktop. Applying
        # the offset to a simulator points the driver at a dead port and reports
        # "the app is not running in test mode" — the wrong cause, which is the
        # same trap documented below for desktop's 8091-vs-9091.
        physical = getattr(args, "ios_physical", False)
        if args.desktop_port == 8091:
            args.desktop_port = 18091 if physical else 9091
        if args.api_port is None:
            args.api_port = 18080 if physical else 8080
    elif not getattr(args, "android", False):
        # DESKTOP binds 9091 DIRECTLY — TestAutomationServer.kt:39
        # (`private val port: Int = 9091`). Android and iOS reach it through a
        # forward (adb 8091->9091, iproxy 18091->9091), which is why the shared
        # 8091 default is correct for them; on desktop there is no forward to
        # translate it, so 8091 hits nothing.
        #
        # The effect was that EVERY desktop test aborted with "CIRIS Desktop app
        # is not running with test mode enabled" while the app was running and
        # answering `{"status":"ok","testMode":true}` on 9091. The failure names
        # the wrong cause — it reads as an app/config problem, so the operator
        # goes and checks CIRIS_TEST_MODE instead of the port.
        if args.desktop_port == 8091:
            args.desktop_port = 9091
    if args.api_port is None:
        # DEFAULT TO THE BACKEND PORT THE RUN IS ACTUALLY USING.
        #
        # `--port` is what everything else honours — the adb forward, the health
        # probe, the app's own backend. Hardcoding 8080 here meant that with
        # `--port 9000` the UI would send successfully to 9000 while the reply
        # assertion logged into 8080: a closed port, or worse, an UNRELATED
        # server that answers. The check would then report on a conversation
        # that was never had.
        args.api_port = getattr(args, "port", None) or 8080


def list_tests() -> None:
    """List available tests."""
    print("\n Available Tests:\n")

    # Legacy browser-based (Playwright) steps — agent/web-UI flow only.
    browser_info = {
        "load_setup": "Load the setup wizard page (browser)",
        "navigate_llm": "Navigate to LLM configuration step (browser, agent-only)",
        "select_provider": "Select LLM provider (browser, agent-only)",
        "enter_key": "Enter API key (browser, agent-only)",
        "load_models": "Load available models (browser, agent-only)",
        "select_model": "Select a model from the list (browser, agent-only)",
        "complete_setup": "Complete remaining setup steps (browser)",
        "send_message": "Send a test message to the agent (browser)",
        "receive_response": "Wait for and validate agent response (browser)",
    }

    print("  Browser (Playwright) steps:")
    for name, desc in browser_info.items():
        print(f"    • {name:20s} - {desc}")

    # Desktop test-server driven first-run wizard steps (2.9.14 three-screen flow).
    print("\n  Desktop first-run wizard steps (test server :8091):")
    node_info = {
        "wait_for_setup_wizard": "Land on the Setup wizard (first-run)",
        "you_step": "YOU → fed-ID label + username/password + age band → btn_next",
        "join_federation": "JOIN_FEDERATION → announce/traces/analyze/location → btn_next",
        "ai_configuration": "AI (agent builds) → provider → btn_next (final)",
        "setup_complete": "COMPLETE (self-claim + leave wizard)",
    }
    for name, desc in node_info.items():
        print(f"    • {name:24s} - {desc}")

    print("\n  Desktop catch-up (Add Federation ID) steps:")
    catchup_info = {
        "reach_add_fedid_entry": "reach btn_add_federation_id (Manage Nodes)",
        "open_add_fedid_screen": "btn_add_federation_id → input_fed_label",
        "catchup_enter_label": "input_fed_label",
        "catchup_announce_on": "toggle_announce_ownership (gates toggle_trace_opt_in)",
        "catchup_trace_opt_in_on": "toggle_trace_opt_in",
        "catchup_confirm": "btn_add_fedid_confirm",
    }
    for name, desc in catchup_info.items():
        print(f"    • {name:24s} - {desc}")

    print("\n Test Groups:\n")
    print("  Desktop (native Compose, test server :8091):")
    print("    • desktop-setup    - Node-client first-run wizard (announce/trace/fed-ID/age)")
    print("    • desktop-catchup  - Catch-up Add-Federation-ID flow")
    print("    • desktop-login    - Login flow")
    print("    • desktop-chat     - Chat interaction")
    print("  Browser (Playwright, legacy agent/web UI):")
    print("    • e2e            - All browser tests in sequence")
    print("    • setup          - Browser setup wizard tests")
    print("    • interact       - Browser interaction tests")
    print("    • models         - Browser model listing tests")
    print("    • licensed_agent - First-time licensed agent flow (Portal device auth)")

    print("\n Examples:\n")
    print("  # Node-client wizard against a freshly-launched first-run desktop app")
    print("  python -m tools.qa_runner.modules.web_ui desktop-setup --launch")
    print("  # Catch-up Add-Federation-ID against a logged-in desktop app")
    print("  python -m tools.qa_runner.modules.web_ui desktop-catchup --launch")
    print("  # Legacy browser flow")
    print("  python -m tools.qa_runner.modules.web_ui e2e --wipe")
    print()


def get_test_list(command: str, specific_tests: Optional[str]) -> Optional[List[str]]:
    """Get list of tests to run based on command and specific tests."""
    if specific_tests:
        return [t.strip() for t in specific_tests.split(",")]

    # NOTE: these are the LEGACY browser-based (Playwright) step groups for
    # the agent/web-UI flow. The LLM provider/key steps (navigate_llm,
    # select_provider, enter_key, load_models, select_model) are AGENT-ONLY —
    # the node-client first-run wizard has NO LLM step. The node-client
    # wizard + catch-up flows are driven natively via the desktop test server
    # (see `desktop-setup` / `desktop-catchup` commands and
    # DesktopAppTestRunner.test_setup_wizard_flow / test_catchup_add_fedid_flow).
    test_groups = {
        "e2e": None,  # Full flow
        "setup": [
            "load_setup",
            "navigate_llm",
            "select_provider",
            "enter_key",
            "load_models",
            "select_model",
            "complete_setup",
        ],
        "interact": [
            "send_message",
            "receive_response",
        ],
        "models": [
            "load_setup",
            "navigate_llm",
            "select_provider",
            "enter_key",
            "load_models",
        ],
        "licensed_agent": ["licensed_agent"],  # Special flow
    }

    return test_groups.get(command)


TEST_ADMIN_USERNAME = "admin"
TEST_ADMIN_PASSWORD = "qa_test_password_12345"


def _kill_port(port: int) -> None:
    """SIGKILL whatever is listening on a port."""
    try:
        # `lsof` is POSIX-only and absent on Windows (and on minimal Linux
        # images), where it raised FileNotFoundError instead of finding nothing.
        from tools.qa_runner.platform_procs import pids_listening_on

        for pid in pids_listening_on(port):
            try:
                os.kill(int(pid), 9)
            except Exception:
                pass
    except Exception:
        pass


def resolved_qa_home() -> Path:
    """The home directory the harness may treat as its own, honouring CIRIS_HOME.

    Split out from _wipe_dev_data so the DECISION can be tested without running
    the destruction. A test that calls _wipe_dev_data for real also clears
    `<repo>/data`, i.e. it damages the working tree of whoever runs the suite --
    which it duly did the first time I wrote one.

    Falls back to ~/ciris, the product's default, when CIRIS_HOME is unset.
    """
    env_home = os.environ.get("CIRIS_HOME")
    return Path(env_home).expanduser() if env_home else Path.home() / "ciris"


def _wipe_dev_data() -> None:
    """Wipe every data location the CIRIS backend may use, for a clean first run.

    HONOURS CIRIS_HOME. This used to hardcode `Path.home() / "ciris"`, so an
    operator who set CIRIS_HOME to a scratch directory still had their REAL
    ~/ciris/data deleted -- on every single desktop-setup invocation. It is a
    destructive operation aimed at whichever directory the harness assumed,
    rather than the one it was told to use.

    The signing key is preserved so device identity survives a reset.
    """
    home_ciris = resolved_qa_home()
    repo_root = Path(__file__).resolve().parents[4]

    signing_key = home_ciris / "agent_signing.key"
    key_backup = None
    if signing_key.exists():
        key_backup = signing_key.read_bytes()

    for data_dir in [home_ciris / "data", repo_root / "data"]:
        if data_dir.exists():
            shutil.rmtree(data_dir, ignore_errors=True)
            print(f" wiped {data_dir}")
        data_dir.mkdir(parents=True, exist_ok=True)

    # Restore signing key
    if key_backup:
        signing_key.write_bytes(key_backup)
        (repo_root / "data" / "agent_signing.key").write_bytes(key_backup)

    # Rewrite minimal .env so the server doesn't re-enter first-run after setup completes
    env_path = home_ciris / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text('CIRIS_CONFIGURED="true"\n', encoding="utf-8")


def _desktop_home(server: "object") -> str:
    """The CIRIS_HOME the desktop app must use: the one the BACKEND is using.

    They have to be the same directory and they were not. `server_manager` does
    `env.setdefault("CIRIS_HOME", project_root)`, so a run that does not export
    CIRIS_HOME puts the backend's home in the REPO CHECKOUT. The desktop app
    inherits no such default and falls back to the product's `~/ciris`.

    Both halves then run, both look healthy, and every file one writes the other
    cannot see. That is what broke the ownership claim: the node minted its
    one-time PIN and wrote `<repo>/claim_pin`, while the app waited on
    `~/ciris/claim_pin`, gave up after 10s, and completed setup with the node
    LEFT UNCLAIMED — reporting success the whole way, because nothing in the
    flow compares the two homes.

    Read from the server object so it cannot drift from what the backend was
    actually given.
    """
    home = getattr(getattr(server, "config", None), "project_root", None)
    return str(os.environ.get("CIRIS_HOME") or home or "")


def _desktop_urls(brain_base_url: str) -> "tuple[str, str]":
    """(CIRIS_API_URL, CIRIS_NODE_URL) for the desktop app — BOTH the brain.

    The client splits its calls across two configured addresses: role/services
    from CIRIS_API_URL, and the setup flow plus folded/reachable from
    CIRIS_NODE_URL. Pointed at the real node, `listModels` 404s, because
    /v1/setup is split and the node owns only half of it.

    The agent now serves BOTH halves — its own routes plus anything unmatched
    forwarded to the node (routes/node_proxy.py) — and reports the node's
    folded/reachable in its own health. So the node address IS the brain address:
    one surface, no split, nothing for the client to get wrong.

    Set CIRIS_DESKTOP_NODE_URL to drive a bare node deliberately.
    """
    api = os.environ.get("CIRIS_DESKTOP_API_URL", "").strip() or brain_base_url
    node = os.environ.get("CIRIS_DESKTOP_NODE_URL", "").strip() or api
    return api, node


def _find_desktop_jar() -> Optional[Path]:
    """Locate the desktop uber jar.

    The jar is no longer BUILT here — :desktopApp lives in CIRISAI/CIRISClient
    and ships inside the pinned `ciris-client` wheel. Three places it can be,
    newest first, because this runs against three different trees:

      1. ciris_engine/desktop_app/  — where CI vendors it and where the wheel
         packages it (`setup.py` derives the wheel's platform tag from it).
      2. the INSTALLED ciris_client package — what a user who pip-installed has,
         and the only copy present when the repo checkout carries no artifacts.
      3. the legacy gradle output — a stale local build from before the client
         adoption. Last, so it can never shadow a current jar.
    """
    repo_root = Path(__file__).resolve().parents[4]

    search: list[str] = [
        str(repo_root / "ciris_engine" / "desktop_app" / "CIRIS-*.jar"),
    ]

    try:
        import ciris_client

        search.append(str(Path(ciris_client.__file__).parent / "_artifacts" / "CIRIS-*.jar"))
    except ImportError:
        # The jar-free universal wheel is a supported configuration, and so is
        # a checkout with nothing installed. Not an error; just one fewer place.
        pass

    search.append(str(repo_root / "client" / "desktopApp" / "build" / "compose" / "jars" / "CIRIS-*.jar"))

    for pattern in search:
        candidates = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if candidates:
            return Path(candidates[0])
    return None


def _complete_setup(base_url: str, mock_llm: bool) -> bool:
    """Call /v1/setup/complete to create the known-password admin user.

    Mirrors qa_runner.server.APIServerManager._complete_qa_setup.
    """
    payload = {
        "llm_provider": "mock" if mock_llm else "openai",
        "llm_api_key": "test-key-for-qa",
        "llm_model": "mock-model" if mock_llm else "gpt-4",
        "template_id": "default",
        "enabled_adapters": ["api"],
        "adapter_config": {},
        "admin_username": TEST_ADMIN_USERNAME,
        "admin_password": TEST_ADMIN_PASSWORD,
        "agent_port": int(base_url.rsplit(":", 1)[-1]),
    }
    try:
        r = requests.post(f"{base_url}/v1/setup/complete", json=payload, timeout=30)
        if r.status_code == 200:
            return True
        print(f" [FAIL] /v1/setup/complete: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        print(f" [FAIL] /v1/setup/complete error: {e}")
        return False


ANDROID_PACKAGE = "ai.ciris.mobile.debug"
ANDROID_ACTIVITY = "ai.ciris.mobile.MainActivity"


def _android_sdk_paths() -> Dict[str, Path]:
    """Locate the Android SDK binaries we need."""
    sdk_root = Path(os.environ.get("ANDROID_SDK_ROOT", "")) if os.environ.get("ANDROID_SDK_ROOT") else None
    if not sdk_root or not sdk_root.exists():
        sdk_root = Path.home() / "Android" / "Sdk"
    return {
        "adb": sdk_root / "platform-tools" / "adb",
        "emulator": sdk_root / "emulator" / "emulator",
    }


def _adb(args: List[str], serial: Optional[str] = None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run an adb command, optionally targeting a specific device serial."""
    paths = _android_sdk_paths()
    cmd: List[str] = [str(paths["adb"])]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _adb_devices(only_ready: bool = True) -> List[str]:
    """Return list of device serials; if only_ready, filter to 'device' state."""
    out = _adb(["devices"]).stdout
    serials: List[str] = []
    for line in out.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            serial, state = parts[0], parts[1]
            if (not only_ready) or state == "device":
                serials.append(serial)
    return serials


def _pick_emulator_serial(preferred: Optional[str] = None) -> Optional[str]:
    """Pick an emulator serial; prefer the explicit one, else the first emulator-* device."""
    serials = _adb_devices(only_ready=True)
    if preferred and preferred in serials:
        return preferred
    for s in serials:
        if s.startswith("emulator-"):
            return s
    return None


def _wait_for_boot(serial: str, timeout: int = 120) -> bool:
    """Poll until the emulator is fully booted (sys.boot_completed == 1)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = _adb(["shell", "getprop", "sys.boot_completed"], serial=serial, timeout=5)
            if r.stdout.strip() == "1":
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _start_emulator(avd: str) -> Optional[subprocess.Popen]:
    """Start the named AVD as a background process. Returns the Popen handle."""
    paths = _android_sdk_paths()
    if not paths["emulator"].exists():
        print(f" [FAIL] emulator binary not found at {paths['emulator']}")
        return None
    cmd = [
        str(paths["emulator"]),
        "-avd",
        avd,
        "-no-snapshot-save",
        "-no-audio",
        "-no-boot-anim",
    ]
    # HEADLESS ON CI. A hosted runner has no GPU and, on the Linux image, only
    # the Xvfb display this workflow starts for the desktop app. Left to
    # autodetect, the emulator negotiates host GPU rendering and spends the whole
    # boot window failing to — it never reaches adb, and the error you get is a
    # timeout that says nothing about graphics. swiftshader_indirect is the
    # software renderer Google documents for exactly this.
    if os.environ.get("CI"):
        cmd += ["-no-window", "-gpu", "swiftshader_indirect"]
    log_path = temp_path("ciris_android_emulator.log")
    log_file = open(log_path, "w")
    print(f"  emulator: starting {avd} (log: {log_path})")
    return subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True)


def _ensure_emulator(args: argparse.Namespace) -> Optional[str]:
    """Make sure an emulator is up. Returns its adb serial, or None on failure."""
    # Already running?
    serial = _pick_emulator_serial(args.android_device)
    if serial:
        print(f"  emulator already up: {serial}")
        return serial

    # No emulator → boot the requested AVD.
    paths = _android_sdk_paths()
    # A MISSING EMULATOR IS A SETUP PROBLEM, NOT A CRASH. GitHub's ubuntu
    # runners ship the Android SDK but neither the emulator package nor any
    # system image, so this raised a bare FileNotFoundError mid-traceback and
    # the actual cause — one absent binary — had to be read out of a stack.
    if not Path(paths["emulator"]).exists():
        print(f" [FAIL] no emulator binary at {paths['emulator']}")
        print("        The Android SDK is present but the emulator package is not.")
        print("        Install it with:")
        print('          sdkmanager "emulator" "system-images;android-34;google_apis;x86_64"')
        print('          avdmanager create avd -n ciris_qa -k "system-images;android-34;google_apis;x86_64"')
        return None
    list_out = subprocess.run([str(paths["emulator"]), "-list-avds"], capture_output=True, text=True, timeout=10).stdout
    avds = [a.strip() for a in list_out.splitlines() if a.strip()]
    if not avds:
        print(" [FAIL] no AVDs configured — create one with `avdmanager create avd ...`")
        return None
    avd = args.android_avd if args.android_avd in avds else avds[0]
    if avd != args.android_avd:
        print(f" [WARN] AVD '{args.android_avd}' not found, using '{avd}'")

    if _start_emulator(avd) is None:
        return None

    # COLD BOOT TAKES MINUTES, NOT 90 SECONDS.
    #
    # 90s was the deadline and the emulator never made it: "emulator did not
    # appear in adb within 90s" on a run where provisioning had worked and the
    # AVD had genuinely started. A cold x86_64 system image on a hosted runner
    # routinely needs 2-4 minutes before adb sees it — so the gate was reporting
    # a bring-up failure for an emulator that was simply still booting, the same
    # too-short-deadline mistake as the 45s reply assertion.
    deadline = time.time() + int(os.environ.get("CIRIS_QA_EMULATOR_BOOT_SECONDS", "300"))
    while time.time() < deadline:
        serial = _pick_emulator_serial(args.android_device)
        if serial:
            break
        time.sleep(2)
    else:
        print(" [FAIL] emulator did not appear in adb within 90s")
        return None

    print(f"  emulator: {serial} attached, waiting for boot…")
    if not _wait_for_boot(serial, timeout=180):
        print(" [FAIL] emulator never finished booting")
        return None
    print(f"  emulator: {serial} booted")
    return serial


def _find_debug_apk() -> Optional[Path]:
    """Locate the built debug APK.

    GLOB, DO NOT HARDCODE. This named one exact file, carrying the module name
    the shell had before it became `:android` (apps/settings.gradle.kts). Gradle
    emits its artifact under the CURRENT module name, so the finder would have
    missed a perfectly good APK sitting right beside the one it was looking for,
    and reported the build as not-yet-done forever.

    Globbing the debug output directory means the module can be renamed again
    without silently breaking this.
    """
    out = _apps_root() / "android" / "build" / "outputs" / "apk" / "debug"
    apks = sorted(out.glob("*-debug.apk"))
    if not apks:
        return None
    if len(apks) > 1:
        print(f"  note: {len(apks)} debug APKs in {out}; using {apks[0].name}")
    return apks[0]


def _apps_root() -> Path:
    """The gradle root that owns the app shells.

    NOT `client/`. apps/settings.gradle.kts is explicit that the shared client is
    no longer built from source here — it arrives as a published .aar and this
    tree holds only the shells, with `include(":android")`. The APK builder was
    never migrated, so it ran `./gradlew` in a `client/` directory that this
    repo does not contain:

        FileNotFoundError: .../CIRISAgent/client

    on a runner where the emulator had booted and everything else was ready. The
    APK FINDER already pointed at apps/; only the builder was left behind, so the
    two halves of the same file disagreed about where the app comes from.
    """
    return Path(__file__).resolve().parents[4] / "apps"


def _build_debug_apk() -> bool:
    apps_dir = _apps_root()
    gradlew = apps_dir / "gradlew"
    if not gradlew.exists():
        print(f" [FAIL] no gradle wrapper at {gradlew}")
        return False
    print(f"  building debug APK (./gradlew :android:assembleDebug in {apps_dir})…")
    r = subprocess.run(
        ["./gradlew", ":android:assembleDebug"],
        cwd=str(apps_dir),
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if r.returncode != 0:
        print(f" [FAIL] gradle build failed:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}")
        return False
    return True


async def run_android_up(args: argparse.Namespace) -> int:
    """Bring up an Android emulator running the debug APK in test mode.

    Architectural note: the Android app embeds its own Python backend via
    Chaquopy and PythonRuntimeService, listening on the emulator's
    localhost:8080. Unlike the desktop path, we do NOT start a host-side
    backend — it would never be reachable from the emulator. Instead we
    forward host:8080 → emulator:8080 so the federation walk-test's API
    state checks (POST /v1/auth/login, GET /v1/system/agent-mode) land on
    the device's own backend. Setup wizard runs on the device on first
    boot; if the test environment isn't already configured, the walk-test
    will fail at login — that's a real diagnostic the surface needs to
    expose.

    Steps:
      1. Discover or boot an Android emulator.
      2. Build the debug APK if missing.
      3. Force-stop + install + launch with debug.CIRIS_TEST_MODE=true
         (debug builds also flip BuildConfig.TEST_MODE_ENABLED on).
      4. `adb forward tcp:8091 tcp:9091` — TestAutomationServer.
         `adb forward tcp:8080 tcp:8080` — embedded backend (best-effort).
      5. Poll http://localhost:8091/health for {"status":"ok"}.
    """
    print(" CIRIS android-up")

    # 1. Emulator.
    print("[1/5] Discovering / booting Android emulator…")
    serial = _ensure_emulator(args)
    if not serial:
        return 1

    # Free host ports we plan to forward into the emulator. If a host backend
    # or stale forward is bound to 8080/8091, the new adb forward will fail
    # silently (overwriting the old map) or — worse — collide with a real
    # listener and confuse the walk-test about whose API it's hitting.
    _kill_port(args.port)
    _kill_port(args.desktop_port)
    try:
        _adb(["forward", "--remove", f"tcp:{args.desktop_port}"], serial=serial, timeout=5)
        _adb(["forward", "--remove", f"tcp:{args.port}"], serial=serial, timeout=5)
    except Exception:
        pass

    # 2. APK.
    apk = _find_debug_apk()
    if not apk:
        print("  debug APK missing — building")
        if not _build_debug_apk():
            return 1
        apk = _find_debug_apk()
    if not apk:
        print(" [FAIL] debug APK still missing after build")
        return 1
    print(f"  apk: {apk} ({apk.stat().st_size // (1024 * 1024)} MB)")

    # 3. Install + launch.
    print("[2/5] Installing APK and launching with CIRIS_TEST_MODE=true…")
    _adb(["shell", "am", "force-stop", ANDROID_PACKAGE], serial=serial, timeout=15)
    install = _adb(["install", "-r", str(apk)], serial=serial, timeout=300)
    if "Success" not in install.stdout:
        print(f" [FAIL] install failed:\n{install.stdout}\n{install.stderr}")
        return 1
    print("  install: ok")

    # Debug builds flip TEST_MODE_ENABLED=true automatically; set the prop
    # too in case anyone is testing a release build via adb.
    _adb(["shell", "setprop", "debug.CIRIS_TEST_MODE", "true"], serial=serial, timeout=10)

    launch = _adb(
        ["shell", "am", "start", "-n", f"{ANDROID_PACKAGE}/{ANDROID_ACTIVITY}", "--es", "CIRIS_TEST_MODE", "true"],
        serial=serial,
        timeout=15,
    )
    if launch.returncode != 0:
        print(f" [FAIL] launch failed: {launch.stderr}")
        return 1
    print("  launch: ok")

    # 4. Port forward host:8091 → device:9091 (test server) AND
    #    host:8080 → device:8080 (embedded backend).
    print("[3/5] Configuring adb port-forwards…")
    forward = _adb(["forward", f"tcp:{args.desktop_port}", "tcp:9091"], serial=serial, timeout=10)
    if forward.returncode != 0:
        print(f" [FAIL] adb forward {args.desktop_port}→9091 failed: {forward.stderr}")
        return 1
    print(f"  forward: host:{args.desktop_port} → {serial}:9091 (test server)")

    forward_api = _adb(["forward", f"tcp:{args.port}", f"tcp:{args.port}"], serial=serial, timeout=10)
    if forward_api.returncode == 0:
        print(f"  forward: host:{args.port} → {serial}:{args.port} (embedded backend)")
    else:
        print(
            f"  ⚠️  adb forward {args.port}→{args.port} failed: {forward_api.stderr.strip()}\n"
            "       backend-state assertions in the walk-test will fail; walk continues."
        )

    # 5. Poll /health.
    print("[4/5] Waiting for AndroidTestAutomationServer to come up…")
    server_url = f"http://localhost:{args.desktop_port}"
    deadline = time.time() + 90
    healthy = False
    last_payload: dict = {}
    while time.time() < deadline:
        try:
            r = requests.get(f"{server_url}/health", timeout=2)
            payload = r.json() if r.status_code == 200 else {}
            # ASSERT WHAT THE NEXT STEP REQUIRES, not something weaker.
            # This accepted status=="ok" alone while run_desktop_tests demands
            # testMode as well, so bring-up reported "[OK] reachable" and the
            # very next line failed on the same URL. A precondition that is
            # looser than its consumer's is not a check, it is a false green.
            if payload.get("status") == "ok" and payload.get("testMode", False):
                healthy = True
                break
            if payload.get("status") == "ok":
                last_payload = payload
        except Exception:
            pass
        time.sleep(2)
    if not healthy:
        if last_payload:
            print(
                f"  ⚠️  /health IS up but never reported testMode: {last_payload}\n"
                "       The app is running WITHOUT test mode, so the automation cannot drive\n"
                "       it. A debug build should set BuildConfig.TEST_MODE_ENABLED itself;\n"
                "       confirm with: adb logcat -d | grep -i testmode"
            )
        else:
            print(
                "  ⚠️  /health did not respond within 90s — the test server may not have started.\n"
                "       Common causes: BuildConfig.TEST_MODE_ENABLED is false on this build, or the app\n"
                "       crashed during init. Inspect with: adb logcat -d *:E"
            )
        return 1
    print(f" [OK] AndroidTestAutomationServer reachable at {server_url}")

    # Best-effort: wait for the device's embedded Python backend too. The
    # mode-change flow in the walk-test depends on it; if it's still booting,
    # the walk will degrade to UI-only assertions.
    print("[5/5] Best-effort wait on embedded Python backend…")
    backend_ok = False
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = requests.get(f"http://localhost:{args.port}/v1/system/health", timeout=2)
            if r.status_code in (200, 401, 403):
                backend_ok = True
                break
        except Exception:
            pass
        time.sleep(2)
    if backend_ok:
        print(f" [OK] embedded backend reachable at http://localhost:{args.port}")
    else:
        print(
            f"  ⚠️  embedded backend not yet ready at http://localhost:{args.port};\n"
            "       walk will proceed but mode-change API assertions may fail."
        )

    # Stash serial for teardown.
    args._android_serial = serial  # type: ignore[attr-defined]
    return 0


def _android_teardown(args: argparse.Namespace, keep_open: bool) -> None:
    """Best-effort: remove the adb forwards and (optionally) force-stop the app."""
    serial = getattr(args, "_android_serial", None)
    if not serial:
        return
    for host_port in (args.desktop_port, args.port):
        try:
            _adb(["forward", "--remove", f"tcp:{host_port}"], serial=serial, timeout=5)
        except Exception:
            pass
    if not keep_open:
        try:
            _adb(["shell", "am", "force-stop", ANDROID_PACKAGE], serial=serial, timeout=10)
        except Exception:
            pass


async def run_desktop_up(args: argparse.Namespace) -> int:
    """End-to-end: wipe → start backend in first-run → setup → launch desktop → login.

    Leaves backend + desktop running so a human (or agent) can drive the UI.
    This is the canonical repeatable path for getting a clean, logged-in
    desktop app up.
    """
    from .server_manager import ServerConfig, ServerManager

    print(" CIRIS desktop-up")

    # 1. Clean slate
    print("[1/5] Stopping anything on 8080/8091 and wiping dev data...")
    _kill_port(args.port)
    _kill_port(args.desktop_port)
    from tools.qa_runner.platform_procs import desktop_process_pattern, kill_processes_matching

    kill_processes_matching(desktop_process_pattern())
    # CIRIS-linux handled by desktop_process_pattern() above; pkill is POSIX-only.
    time.sleep(1)
    _wipe_dev_data()

    # 2. Start backend in first-run mode
    # CIRIS_TESTING_MODE relaxes the setup validator that otherwise rejects 'admin'
    os.environ["CIRIS_TESTING_MODE"] = "true"
    print("[2/5] Starting backend (first-run mode, CIRIS_TESTING_MODE=true)...")
    cfg = ServerConfig(
        port=args.port,
        mock_llm=args.mock_llm,
        wipe_data=False,  # we already did it
        first_run_mode=True,
        startup_timeout=args.timeout,
    )
    server = ServerManager(cfg)
    status = server.start()
    if not status.running:
        print(f" [FAIL] backend failed: {status.error}")
        return 1

    # 3. Complete setup
    print("[3/5] Completing setup wizard via /v1/setup/complete...")
    if not _complete_setup(server.base_url, args.mock_llm):
        server.stop()
        return 1
    # Username only. The password is a fixed constant in this file
    # (TEST_ADMIN_PASSWORD) and anyone who needs it reads it there. Echoing it
    # puts a working credential into CI logs, terminal scrollback, and every
    # transcript of a QA session, for no information the reader lacks.
    print(f" [OK] admin created: {TEST_ADMIN_USERNAME} (password: see TEST_ADMIN_PASSWORD)")

    # Restart backend without CIRIS_FORCE_FIRST_RUN so /v1/setup/status
    # returns is_first_run=false and the desktop goes to the Login screen,
    # not the Setup wizard.
    print(" restarting backend in configured mode...")
    server.stop()
    cfg2 = ServerConfig(
        port=args.port,
        mock_llm=args.mock_llm,
        wipe_data=False,
        first_run_mode=False,
        startup_timeout=args.timeout,
    )
    server = ServerManager(cfg2)
    status = server.start()
    if not status.running:
        print(f" [FAIL] backend restart failed: {status.error}")
        return 1

    # 4. Launch desktop app
    if not args.no_desktop:
        print("[4/5] Launching desktop app (CIRIS_TEST_MODE=true)...")
        jar = _find_desktop_jar()
        if not jar:
            print(
                " [FAIL] No desktop jar found. It ships in the ciris-client wheel now, not gradle.\n"
                "        Install the pinned client, or vendor it with\n"
                "        tools/dev/vendor_desktop_jar.py <wheel-dir> ciris_engine/desktop_app"
            )
            server.stop()
            return 1
        env = os.environ.copy()
        env["CIRIS_TEST_MODE"] = "true"
        env["CIRIS_TEST_PORT"] = str(args.desktop_port)
        env["CIRIS_API_URL"], env["CIRIS_NODE_URL"] = _desktop_urls(server.base_url)
        # SAME HOME AS THE BACKEND, or the app cannot see the files the node writes.
        if _home := _desktop_home(server):
            env["CIRIS_HOME"] = _home
        log_path = temp_path("ciris_desktop_up.log")
        with open(log_path, "w") as log:
            subprocess.Popen(
                ["java", "-jar", str(jar)],
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        print(f"  logs: {log_path}")

        # Wait for test server
        deadline = time.time() + 60
        server_url = f"http://localhost:{args.desktop_port}"
        while time.time() < deadline:
            try:
                if requests.get(f"{server_url}/health", timeout=2).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            print(" [WARN] desktop test server didn't come up; continuing anyway")

        # 5. Log in via the UI
        print("[5/5] Logging in via UI...")
        helper = DesktopAppHelper(DesktopAppConfig(server_url=server_url))
        await helper.start()
        try:
            await helper.wait_for_screen("Login", timeout=60000)
            await helper.input_text("input_username", TEST_ADMIN_USERNAME)
            await helper.input_text("input_password", TEST_ADMIN_PASSWORD)
            await helper.click("btn_login_submit")
            # Any post-login screen is success
            deadline = time.time() + 30
            while time.time() < deadline:
                s = await helper.get_screen()
                if s and s != "Login":
                    print(f" [OK] logged in → {s}")
                    break
                await asyncio.sleep(0.5)
            else:
                print(" [WARN] still on Login after 30s")
        finally:
            await helper.stop()
    else:
        print("[4/5] Skipping desktop launch (--no-desktop)")

    print()
    print(f"[OK] Ready. Backend: {server.base_url} Desktop test server: http://localhost:{args.desktop_port}")
    # Username only — see the note at the admin-created line above.
    print(f"   Admin: {TEST_ADMIN_USERNAME} (password: see TEST_ADMIN_PASSWORD)")
    _hint = (
        "taskkill /F /IM CIRIS-windows.exe"
        if sys.platform == "win32"
        else "pkill -9 -f 'CIRIS-(macos|linux)|main.py --adapter api'"
    )
    print(f"   Processes left running — kill with: {_hint}")
    return 0


async def run_desktop_first_run_up(args: argparse.Namespace) -> int:
    """Bring-up for the SETUP WIZARD test: wipe → backend in FIRST-RUN mode →
    launch desktop JAR with CIRIS_TEST_MODE=true.

    Unlike run_desktop_up, setup is NOT completed via /v1/setup/complete and
    the backend is NOT restarted in configured mode — the whole point is to
    leave the desktop app sitting on the Setup wizard so
    test_setup_wizard_flow can drive it through the UI.
    """
    from .server_manager import ServerConfig, ServerManager

    print(" CIRIS desktop first-run bring-up (setup wizard)")

    # 1. Clean slate
    print("[1/3] Stopping anything on 8080/8091 and wiping dev data...")
    _kill_port(args.port)
    _kill_port(args.desktop_port)
    from tools.qa_runner.platform_procs import desktop_process_pattern, kill_processes_matching

    kill_processes_matching(desktop_process_pattern())
    # CIRIS-linux handled by desktop_process_pattern() above; pkill is POSIX-only.
    time.sleep(1)
    _wipe_dev_data()
    # _wipe_dev_data rewrites ~/ciris/.env with CIRIS_CONFIGURED="true" (for
    # the configured-mode path). First-run must NOT see it — remove it so the
    # backend's setup probe reports first_run and the desktop routes to the
    # Setup wizard. (CIRIS_FORCE_FIRST_RUN=1 is also set by ServerManager.)
    stale_env = Path.home() / "ciris" / ".env"
    if stale_env.exists():
        stale_env.unlink()

    # 2. Start backend in first-run mode and LEAVE it there.
    # CIRIS_TESTING_MODE relaxes the setup validator that otherwise rejects 'admin'.
    os.environ["CIRIS_TESTING_MODE"] = "true"
    print("[2/3] Starting backend (first-run mode, CIRIS_TESTING_MODE=true)...")
    cfg = ServerConfig(
        port=args.port,
        mock_llm=args.mock_llm,
        wipe_data=False,  # we already did it
        first_run_mode=True,
        startup_timeout=args.timeout,
    )
    server = ServerManager(cfg)
    status = server.start()
    if not status.running:
        print(f" [FAIL] backend failed: {status.error}")
        return 1

    # 3. Launch desktop app with the test-automation server enabled.
    print("[3/3] Launching desktop app (CIRIS_TEST_MODE=true)...")
    jar = _find_desktop_jar()
    if not jar:
        print(
            " [FAIL] No desktop jar found. It ships in the ciris-client wheel now, not gradle.\n"
            "        Install the pinned client, or vendor it with\n"
            "        tools/dev/vendor_desktop_jar.py <wheel-dir> ciris_engine/desktop_app"
        )
        server.stop()
        return 1
    env = os.environ.copy()
    env["CIRIS_TEST_MODE"] = "true"
    env["CIRIS_TEST_PORT"] = str(args.desktop_port)
    env["CIRIS_API_URL"], env["CIRIS_NODE_URL"] = _desktop_urls(server.base_url)
    # SAME HOME AS THE BACKEND, or the app cannot see the files the node writes
    # (the claim PIN in particular).
    if _home := _desktop_home(server):
        env["CIRIS_HOME"] = _home
    log_path = temp_path("ciris_desktop_setup.log")
    with open(log_path, "w") as log:
        subprocess.Popen(
            ["java", "-jar", str(jar)],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    print(f"  logs: {log_path}")

    # Wait for the desktop test server
    deadline = time.time() + 60
    server_url = f"http://localhost:{args.desktop_port}"
    while time.time() < deadline:
        try:
            if requests.get(f"{server_url}/health", timeout=2).status_code == 200:
                print(f" [OK] desktop test server up at {server_url}")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        print(" [FAIL] desktop test server didn't come up within 60s")
        print(f"     inspect: {log_path}")
        return 1

    print(f"[OK] First-run stack ready. Backend: {server.base_url} (first-run) Desktop: {server_url}")
    return 0


_IOS_IPROXY_PROCS: List[subprocess.Popen] = []


def _kill_iproxy_children() -> None:
    """Tear down every iproxy process spawned by run_ios_up().

    Idempotent — atexit may invoke this twice on abnormal exit paths.
    """
    while _IOS_IPROXY_PROCS:
        p = _IOS_IPROXY_PROCS.pop()
        try:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        except Exception:
            pass


#: How long to wait for a rendered reply. Must EXCEED the agent's own
#: `interaction_timeout` (APIAdapterConfig, 110s), because until interact returns
#: the client has nothing to render and a shorter deadline measures our patience
#: rather than the product. Set from CIRIS_QA_RESPONSE_DEADLINE for a slow host.
RESPONSE_DEADLINE_SECONDS = int(os.environ.get("CIRIS_QA_RESPONSE_DEADLINE", "150"))


def _is_new_agent_reply(msg: dict, baseline_ids: set, sent: str) -> bool:
    """Is this history row a NEW answer from the agent to the message we sent?

    Every clause closes a way this went green while the product was silent or
    broken:

      * NEW — absent from the pre-send baseline. Any agent row from an earlier
        interaction would otherwise satisfy "an agent replied".
      * message_type == "agent", NOT `is_agent`. routes/agent.py sets
        `is_agent = True` for message_type "system" AND "error" deliberately,
        so the agent does not re-observe its own notifications. Keying on
        is_agent accepts the error text emitted when processing FAILED as
        proof that it succeeded — green exactly when the product broke.
      * non-empty, and not the echo of what we sent.
    """
    if msg.get("id") in baseline_ids:
        return False
    if msg.get("message_type") != "agent":
        return False
    content = (msg.get("content") or "").strip()
    return bool(content) and content != sent



def qa_log_dir() -> Path:
    """Where bring-up writes everything it learns, so CI can upload it.

    A FAILURE YOU CANNOT DIAGNOSE FROM THE ARTIFACT COSTS MORE THAN THE FAILURE.
    Every truncated `stderr[:200]` in a CI log is a round trip: someone re-runs
    the job with more logging to find out what the first run already knew. So the
    full stdout/stderr of every command lands in a file here, and the console
    keeps the short form for readability.

    Overridable with CIRIS_QA_LOG_DIR so the workflow can point it somewhere it
    already uploads.
    """
    d = Path(os.environ.get("CIRIS_QA_LOG_DIR") or (Path(tempfile.gettempdir()) / "ciris-qa-logs"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record(name: str, proc: subprocess.CompletedProcess, cmd: Optional[List[str]] = None) -> Path:
    """Persist a command's full result and return the file written."""
    path = qa_log_dir() / f"{name}.log"
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"$ {' '.join(cmd or getattr(proc, 'args', []) or [name])}\n")
            fh.write(f"# returncode={proc.returncode}\n")
            if proc.stdout:
                fh.write("--- stdout ---\n" + str(proc.stdout) + "\n")
            if proc.stderr:
                fh.write("--- stderr ---\n" + str(proc.stderr) + "\n")
            fh.write("\n")
    except OSError:
        pass
    return path


def _fail(step: str, proc: Optional[subprocess.CompletedProcess] = None, hint: str = "") -> None:
    """One shape for every failure: what broke, the real error, where the rest is.

    Prints a TAIL of stderr rather than a fixed-width slice — the useful part of
    a toolchain error is almost always at the end, and `[:200]` reliably cuts it
    off mid-sentence.
    """
    print(f" [FAIL] {step}")
    if proc is not None:
        err = (proc.stderr or proc.stdout or "").strip()
        if err:
            tail = err.splitlines()[-6:]
            for line in tail:
                print(f"        {line[:220]}")
        print(f"        rc={proc.returncode}")
    if hint:
        for line in hint.splitlines():
            print(f"        {line}")
    print(f"        full output: {qa_log_dir()}")


def _ios_startup_state(udid: str, bundle_id: str) -> str:
    """One-line summary of how far the app has got, for the wait's progress lines.

    The app writes into Documents/ciris inside its data container, so the
    presence of a data dir, a database and log files is a coarse but honest
    progress bar for a startup that otherwise reports nothing until its HTTP
    server binds. "no container yet" and "logs but no db" are different failures
    and used to look identical from outside.
    """
    box = _simctl(["get_app_container", udid, bundle_id, "data"], timeout=30)
    root = (box.stdout or "").strip().splitlines()
    if not root or not root[0].startswith("/"):
        return "container=<none>"
    base = Path(root[0]) / "Documents" / "ciris"
    if not base.exists():
        return "container=ok ciris=<not created>"
    bits = []
    for name, pattern in (("logs", "logs/*.log"), ("db", "data/*.db")):
        hits = sorted(base.glob(pattern))
        bits.append(f"{name}={len(hits)}")
    newest = max((f.stat().st_mtime for f in base.rglob("*") if f.is_file()), default=0)
    age = f"{time.time() - newest:.0f}s" if newest else "n/a"
    return f"container=ok {' '.join(bits)} last-write={age}-ago"


def _ios_diagnostics(udid: str, bundle_id: str, process_name: str = "iosApp") -> None:
    """Dump everything that explains an iOS bring-up failure, to files.

    Collected on the FAILURE PATH ONLY, because `log show` is slow and large. The
    set is chosen from what actually gets asked when a simulator run misbehaves:
    is the device really booted, did the app install, did it launch, and what did
    it say on the way down.
    """
    print("  collecting iOS diagnostics…")
    probes = [
        ("ios-devices", ["xcrun", "simctl", "list", "devices"]),
        ("ios-listapps", ["xcrun", "simctl", "listapps", udid]),
        ("ios-container", ["xcrun", "simctl", "get_app_container", udid, bundle_id, "data"]),
        # The app's own os_log output — the only place a Swift/Kotlin crash or a
        # "test server refused to bind" message appears.
        #
        # MATCH THE EXECUTABLE, NOT A BUNDLE-ID FRAGMENT. launchd names the process
        # by its binary -- "Successfully spawned iosApp[27615]" -- while the
        # bundle id is ai.ciris.mobile. The old predicate took the last id
        # segment, "mobile", which matched Apple's mobileassetd and not one line
        # from our app: run 33706020778 produced 7 "hits", all asset-daemon
        # noise, and zero of the NSLog("[TestAutomation.ios] ...") lines that
        # say whether the server bound. And 3m from the failure point missed
        # the launch itself; the bring-up budget alone is 120s.
        (
            "ios-oslog",
            [
                "xcrun", "simctl", "spawn", udid, "log", "show",
                "--last", "10m", "--style", "syslog",
                "--predicate", f'process == "{process_name}" OR subsystem CONTAINS "{bundle_id}"',
            ],
        ),
    ]
    for name, cmd in probes:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            _record(name, proc, cmd)
            print(f"    {name}: rc={proc.returncode} -> {qa_log_dir() / (name + '.log')}")
        except Exception as exc:  # noqa: BLE001
            print(f"    {name}: could not collect ({type(exc).__name__})")

    # THE APP'S OWN LOGS, which os_log does not carry. The Python runtime writes
    # into Documents/ciris/logs inside the data container, and that is where a
    # startup that stalls mid-initialisation says WHY — os_log only shows that
    # the process is alive. Without these, a bring-up failure is diagnosable
    # only down to "it did not answer".
    try:
        box = _simctl(["get_app_container", udid, bundle_id, "data"], timeout=60)
        root = (box.stdout or "").strip().splitlines()
        base = Path(root[0]) / "Documents" / "ciris" if root and root[0].startswith("/") else None
        if base and base.exists():
            dest = qa_log_dir() / "ios-app-logs"
            dest.mkdir(parents=True, exist_ok=True)
            copied = 0
            for f in sorted(base.rglob("*.log")) + sorted(base.rglob("*.txt")):
                if f.is_file():
                    shutil.copy2(f, dest / f.name)
                    copied += 1
            print(f"    ios-app-logs: {copied} file(s) -> {dest}")
            # Surface the newest incident inline: the artifact is for later, but
            # the reason should be readable in the job log without a download.
            incidents = sorted(base.rglob("incidents_latest.log"))
            if incidents:
                tail = incidents[0].read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
                print(f"    --- {incidents[0].name} (last {len(tail)} lines) ---")
                for line in tail:
                    print(f"      {line[:160]}")
        else:
            print("    ios-app-logs: no Documents/ciris in the container — the app "
                  "had not started writing yet")
    except Exception as exc:  # noqa: BLE001
        print(f"    ios-app-logs: could not collect ({type(exc).__name__}: {exc})")


def _simctl(args: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run `xcrun simctl ...`. Mirrors `_adb` so both bring-ups read alike."""
    cmd = ["xcrun", "simctl", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        # No Xcode on this host. A TRACEBACK here is the worst possible outcome:
        # in CI it buries the actual condition ("this runner has no Xcode") under
        # a stack that points at subprocess.py, and the reader goes looking for a
        # bug in the automation. Fail as a normal non-zero result so the caller's
        # own diagnostics run and say something true.
        proc = subprocess.CompletedProcess(
            cmd, 127, "", "xcrun not found — this host has no Xcode command line tools."
        )
    except subprocess.TimeoutExpired:
        proc = subprocess.CompletedProcess(
            cmd, 124, "", f"timed out after {timeout}s"
        )
    # Recorded unconditionally, not just on failure: the command BEFORE the one
    # that broke is usually what explains it, and by then it is too late to
    # re-run it in the same state.
    _record("simctl", proc, cmd)
    return proc


def _ios_pick_simulator(requested: Optional[str] = None) -> Optional[str]:
    """Resolve the simulator UDID to drive.

    `booted` is accepted verbatim — simctl understands it and it is what a
    developer with a simulator already open will pass. Otherwise prefer an
    already-booted device (nothing to wait for), then any available iPhone.

    Returns None when no usable simulator exists, which is a REAL failure rather
    than something to paper over: a run that silently targets the wrong device is
    worse than one that stops.
    """
    if requested and requested != "booted":
        return requested

    listing = _simctl(["list", "devices", "available", "-j"], timeout=60)
    if listing.returncode != 0:
        return None
    try:
        devices = json.loads(listing.stdout).get("devices", {})
    except (json.JSONDecodeError, AttributeError):
        return None

    flat = [d for runtime in devices.values() for d in runtime]
    for dev in flat:
        if dev.get("state") == "Booted":
            return dev.get("udid")
    for dev in flat:
        if "iPhone" in (dev.get("name") or ""):
            return dev.get("udid")
    return flat[0].get("udid") if flat else None


def _ios_find_app(explicit: Optional[str] = None) -> Optional[Path]:
    """Locate the built .app bundle for the simulator.

    A SIMULATOR BUILD, not a device build: the two have different architectures
    and a device .app cannot be installed into a simulator. DerivedData is
    searched because that is where xcodebuild puts it and pinning one path would
    break the moment the scheme or configuration changes.
    """
    if explicit:
        app = Path(explicit)
        return app if app.exists() else None

    repo_root = Path(__file__).resolve().parents[4]
    roots = [
        repo_root / "apps" / "ios" / "build",
        Path.home() / "Library" / "Developer" / "Xcode" / "DerivedData",
    ]
    candidates: List[Path] = []
    for root in roots:
        if not root.exists():
            continue
        # iphonesimulator, never iphoneos — see the docstring.
        candidates.extend(root.glob("**/Build/Products/*-iphonesimulator/*.app"))
        candidates.extend(root.glob("**/*-iphonesimulator/*.app"))
    if not candidates:
        return None
    # Newest wins: a stale bundle from a previous scheme is the classic way to
    # test something other than what you just built.
    return max(candidates, key=lambda p: p.stat().st_mtime)


async def run_ios_simulator_up(args: argparse.Namespace) -> int:
    """Bring up the CIRIS client on an iOS SIMULATOR and wait for its test server.

    WHY A SEPARATE FUNCTION FROM `run_ios_up`. That one is physical-device only:
    `devicectl process launch` plus `iproxy` USB tunnelling, and it resolves two
    different UDIDs because devicectl and libimobiledevice disagree about what a
    device's identifier is. None of that applies here, and bolting a mode switch
    onto it would leave one function serving two transports with almost nothing
    in common.

    NO PORT FORWARDING. A simulator shares the host's network stack, so the app's
    TestAutomationServer on 9091 is reachable at localhost:9091 directly — same
    as desktop. The 18091/18080 iproxy convention applies ONLY to physical
    devices; using it here points the driver at a dead port and reports "the app
    is not running in test mode", which names the wrong cause.

    Phases mirror `run_android_up` so the two read alike:
      1. Resolve + boot the simulator
      2. Locate the simulator .app (built separately; this does not build it)
      3. Install
      4. Launch with CIRIS_TEST_MODE=true
      5. Poll /health until the test server answers
    """
    print(" CIRIS ios-simulator-up")

    # 1. Resolve + boot.
    print("[1/5] Resolving iOS simulator…")
    udid = _ios_pick_simulator(getattr(args, "ios_udid", None))
    if not udid:
        # DISTINGUISH THE TWO CAUSES. "No simulator available" and "this host has
        # no Xcode" lead to completely different fixes, and reporting the former
        # for the latter sends the reader to `simctl list` on a machine where
        # simctl does not exist.
        if shutil.which("xcrun") is None:
            _fail(
                "no Xcode toolchain on this host",
                hint="`xcrun` is not on PATH, so no simulator can exist here.\n"
                     "iOS bring-up requires a macOS runner with Xcode; on Linux/Windows\n"
                     "this platform should be SKIPPED, not attempted.",
            )
        else:
            _fail(
                "no available iOS simulator",
                hint="`xcrun simctl list devices available` shows what this host has.\n"
                     "A GitHub macos runner ships at least one iPhone runtime; if the list\n"
                     "is empty the Xcode selection is probably wrong (check xcode-select -p).",
            )
        return 1
    print(f"  simulator: {udid}")

    boot = _simctl(["boot", udid], timeout=180)
    # "Unable to boot device in current state: Booted" is success for our
    # purposes — treating it as failure would make the function non-idempotent
    # and break every second local run.
    already = "current state: Booted" in (boot.stderr or "")
    if boot.returncode != 0 and not already:
        _fail(f"simctl boot {udid}", boot)
        return 1
    status = _simctl(["bootstatus", udid, "-b"], timeout=300)
    if status.returncode != 0:
        _fail("simulator never finished booting", status)
        _ios_diagnostics(udid, getattr(args, "ios_bundle_id", None) or "ai.ciris.mobile")
        return 1
    print("  booted")

    # 2. Locate the app.
    print("[2/5] Locating the simulator .app…")
    bundle_id = getattr(args, "ios_bundle_id", None) or "ai.ciris.mobile"
    app = _ios_find_app(getattr(args, "ios_app_path", None))
    if not app:
        # `apps/ios/scripts/rebuild_and_deploy.sh` — the script that ships to the
        # App Store — BUILDS AND INSTALLS. So the bundle can legitimately already
        # be on the simulator with no .app left for us to point at. Re-installing
        # is not required; relaunching it in test mode is.
        already = _simctl(["get_app_container", udid, bundle_id, "app"], timeout=60)
        if already.returncode == 0:
            print(f"  no .app located, but {bundle_id} is already installed — install skipped")
        else:
            _fail(
                "no *Debug-iphonesimulator*/*.app found and the bundle is not installed",
                hint="Build it with `bash apps/ios/scripts/rebuild_and_deploy.sh`, which\n"
                     "runs xcodegen, rebuilds Resources.zip and lays down the SIMULATOR\n"
                     "Python bundle — a bare `xcodebuild -scheme iosApp` skips all three\n"
                     "and produces an app that launches to nothing.\n"
                     "Or pass --ios-app-path explicitly.",
            )
            return 1
    else:
        print(f"  app: {app}")

    # 3. Install (skipped when the build script already did it).
    print("[3/5] Installing…" if app else "[3/5] Install skipped — already present")
    install = _simctl(["install", udid, str(app)], timeout=300) if app else None
    if install is not None and install.returncode != 0:
        _fail(f"simctl install {app.name}", install,
              hint="A device (iphoneos) build cannot install into a simulator — the\n"
                   "architectures differ. Confirm this bundle came from an\n"
                   "-sdk iphonesimulator build.")
        _ios_diagnostics(udid, getattr(args, "ios_bundle_id", None) or "ai.ciris.mobile")
        return 1

    # 4. Launch in test mode. simctl passes environment through to the app only
    # via the SIMCTL_CHILD_ prefix; setting CIRIS_TEST_MODE directly would set it
    # on simctl itself and the app would never see it.
    print("[4/5] Launching with CIRIS_TEST_MODE=true…")
    _simctl(["terminate", udid, bundle_id], timeout=60)  # idempotent; ignore rc
    env = dict(os.environ)
    env["SIMCTL_CHILD_CIRIS_TEST_MODE"] = "true"
    env["SIMCTL_CHILD_CIRIS_TESTING_MODE"] = "true"
    launch = subprocess.run(
        ["xcrun", "simctl", "launch", udid, bundle_id],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    _record("simctl-launch", launch, ["xcrun", "simctl", "launch", udid, bundle_id])
    if launch.returncode != 0:
        _fail(f"simctl launch {bundle_id}", launch,
              hint="If this says the bundle is unknown, the install silently targeted a\n"
                   "different simulator — check the UDID above against `simctl listapps`.")
        _ios_diagnostics(udid, bundle_id)
        return 1

    # 5. Poll /health — the same signal android-up waits on.
    port = getattr(args, "desktop_port", None) or 9091
    server_url = f"http://localhost:{port}"
    # 120s IS THE BUDGET, NOT A GUESS. iOS comes up in ~15-20s when it is
    # working, so if the test server has not bound in two minutes something is
    # WRONG and waiting longer just delays the report. What was missing was not
    # patience — it was any record of what the app was doing while we waited:
    # the failure said "no /health in 120s" and nothing about the state of the
    # thing that did not answer.
    wait_secs = int(os.environ.get("CIRIS_QA_IOS_HEALTH_SECONDS", "120"))
    print(f"[5/5] Waiting for the test server at {server_url} (up to {wait_secs}s)…")
    deadline = time.time() + wait_secs
    started = time.time()
    last_note = 0.0
    while time.time() < deadline:
        try:
            r = requests.get(f"{server_url}/health", timeout=2)
            if r.status_code == 200:
                print(f" [OK] iOS simulator ready after {time.time() - started:.0f}s")
                return 0
        except Exception:  # noqa: BLE001
            pass

        # A DEAD APP IS NOT A SLOW APP. Without this the two are indistinguishable
        # from the outside — both are "no answer on 9091" — and a crash burned the
        # whole window before reporting a timeout that named the wrong cause.
        # TIMESTAMPED PROGRESS, so the log shows WHERE it stopped rather than
        # only that it did. Each line carries the wall clock (to correlate with
        # os_log), the elapsed time, whether the process is still alive, and how
        # far the app has got in writing its own state into the container.
        elapsed = time.time() - started
        if elapsed - last_note >= 15:
            last_note = elapsed
            alive = _simctl(["spawn", udid, "launchctl", "list"], timeout=30)
            running = bundle_id in (alive.stdout or "")
            stamp = datetime.now().strftime("%H:%M:%S")
            print(f"  [{stamp}] +{elapsed:.0f}s  app={'running' if running else 'EXITED'}  {_ios_startup_state(udid, bundle_id)}")
            # A DEAD APP IS NOT A SLOW APP. From outside both are "no answer on
            # 9091"; only one is worth waiting for, so stop as soon as we know.
            if not running:
                _fail(
                    f"the app EXITED while we waited for {server_url}/health after {elapsed:.0f}s",
                    hint="It launched and then stopped, so this is a crash on startup\n"
                         "rather than a slow one. The os_log dump below covers the\n"
                         "launch window.",
                )
                _ios_diagnostics(udid, bundle_id)
                return 1
        time.sleep(2)

    _fail(
        f"no /health from {server_url} within {wait_secs}s",
        hint="The app launched but its TestAutomationServer never answered.\n"
             "Most likely causes, in order:\n"
             "  1. CIRIS_TEST_MODE did not reach the app — simctl only forwards env\n"
             "     vars with the SIMCTL_CHILD_ prefix.\n"
             "  2. This build does not embed the test server.\n"
             "  3. The app crashed on launch — see the os_log dump below.\n"
             "A simulator needs NO port forward: 9091 is reached directly on the host.",
    )
    _ios_diagnostics(udid, bundle_id)
    return 1


async def run_ios_up(args: argparse.Namespace) -> int:
    """End-to-end iOS bring-up: devicectl process launch + iproxy forwards.

    Unlike run_desktop_up (which wipes data + completes setup), the iOS
    flow assumes the device app is already configured — device data is
    sovereign. We just:
      1. Pick the connected device (or honor --ios-device-id)
      2. devicectl process launch --terminate-existing with CIRIS_TEST_MODE=true
      3. Spawn iproxy <desktop_port>->9091 (iOS test server) and iproxy <api_port>->8080
      4. Poll both /health endpoints until ready (or fail)

    iproxy children are registered for cleanup at process exit; killing
    the runner SIGTERMs them so we don't leak port-forwards.
    """
    import atexit

    from ..mobile.ios.idevice_helper import IDeviceHelper

    print(" CIRIS ios-up")

    # 1. Resolve device
    # iOS has TWO UDIDs per device, depending on which tool is asking:
    #   - CoreDevice UUID (e.g. "A53DA92F-972A-5A28-86E3-E6E86E02EE79") — used by xcrun devicectl
    #   - libimobiledevice UDID (e.g. "00008110-0016395C1ED9401E") — used by iproxy, ideviceinstaller
    # We need both: devicectl for launching the app, iproxy for port-forwarding.
    try:
        ios = IDeviceHelper(device_id=args.ios_device_id)
    except RuntimeError as e:
        print(f" [FAIL] {e}")
        return 1
    devices = ios.get_devices()
    if not devices:
        print(" [FAIL] No physical iOS device connected. Plug in + trust, then retry.")
        return 1
    # CoreDevice UUID for devicectl
    devicectl_udid = args.ios_device_id or devices[0].identifier
    # libimobiledevice UDID for iproxy — query idevice_id directly
    try:
        idev_result = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True, timeout=10)
        iproxy_udid = idev_result.stdout.strip().splitlines()[0] if idev_result.stdout.strip() else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        iproxy_udid = None
    if not iproxy_udid:
        print(
            "  ❌ Cannot resolve libimobiledevice UDID via `idevice_id -l`. "
            "Install libimobiledevice (brew install libimobiledevice)."
        )
        return 1
    print(f"[1/4] device: devicectl={devicectl_udid}  iproxy={iproxy_udid}")

    # 2. devicectl process launch with test-mode env vars.
    # CIRIS_TEST_MODE  → enables the iOS POSIX test-automation server on :9091
    # CIRIS_TESTING_MODE → relaxes the setup validator so 'admin' / qa creds
    #                      are accepted by /v1/setup/complete (mirrors what
    #                      run_desktop_up sets via os.environ on the host).
    IOS_TEST_ENV = '{"CIRIS_TEST_MODE":"true","CIRIS_TESTING_MODE":"true"}'
    print(f"[2/4] Launching {args.ios_bundle_id} (CIRIS_TEST_MODE=true, CIRIS_TESTING_MODE=true)...")
    launch_cmd = [
        "xcrun",
        "devicectl",
        "device",
        "process",
        "launch",
        "--device",
        devicectl_udid,
        "--terminate-existing",
        "--environment-variables",
        IOS_TEST_ENV,
        args.ios_bundle_id,
    ]
    try:
        result = subprocess.run(
            launch_cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        print(" [FAIL] devicectl process launch timed out after 60s")
        return 1
    if result.returncode != 0:
        print(f" [FAIL] devicectl process launch failed: {result.stderr.strip() or result.stdout.strip()}")
        return 1
    print(" [OK] app launched")

    # 3. iproxy forwards — test-automation server + backend
    # iOS POSIX test server runs on device :9091 (matches Android emulator port,
    # NOT the desktop :8091 — see TestAutomationServer.ios.kt). Backend on :8080.
    IOS_TEST_REMOTE_PORT = 9091
    IOS_BACKEND_REMOTE_PORT = 8080
    print(
        f"[3/4] iproxy {args.desktop_port}->{IOS_TEST_REMOTE_PORT} "
        f"and {args.api_port}->{IOS_BACKEND_REMOTE_PORT}..."
    )
    atexit.register(_kill_iproxy_children)
    for local_port, remote_port, label in (
        (args.desktop_port, IOS_TEST_REMOTE_PORT, "test-automation"),
        (args.api_port, IOS_BACKEND_REMOTE_PORT, "backend api"),
    ):
        try:
            proc = subprocess.Popen(
                ["iproxy", str(local_port), str(remote_port), "-u", iproxy_udid],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print(" [FAIL] iproxy not found. Install libimobiledevice (brew install libimobiledevice).")
            _kill_iproxy_children()
            return 1
        _IOS_IPROXY_PROCS.append(proc)
        print(f" [OK] iproxy {local_port}->{remote_port} ({label}) pid={proc.pid}")
        # Brief settle — iproxy needs a moment before the first connect
        await asyncio.sleep(0.4)

    # 4. Poll both endpoints until healthy
    print("[4/4] Waiting for test-automation + backend to respond...")
    test_url = f"http://localhost:{args.desktop_port}/health"
    api_url = f"http://localhost:{args.api_port}/v1/system/health"
    deadline = time.time() + 60
    test_ok = api_ok = False
    while time.time() < deadline:
        if not test_ok:
            try:
                if requests.get(test_url, timeout=2).status_code == 200:
                    test_ok = True
                    print(f" [OK] test-automation up at {test_url}")
            except Exception:
                pass
        if not api_ok:
            try:
                # backend health may return 200 OR 503 (degraded) — both prove the
                # process is up and forwarding; the walk-test will surface real
                # health from its own state assertions.
                if requests.get(api_url, timeout=2).status_code in (200, 503):
                    api_ok = True
                    print(f" [OK] backend api up at {api_url}")
            except Exception:
                pass
        if test_ok and api_ok:
            break
        await asyncio.sleep(1)

    if not test_ok:
        print(f" [FAIL] test-automation did not respond at {test_url} within 60s")
        _kill_iproxy_children()
        return 1
    if not api_ok:
        print(f" [WARN] backend api did not respond at {api_url} within 60s — walk will still try")

    # 5. First-run detection + auto-setup. If the device is at the Setup wizard,
    # the walk-test's login step will fail (no input_username on a Setup screen).
    # Hit /v1/setup/status via the iproxy-forwarded backend; if first_run is true,
    # POST /v1/setup/complete with the standard QA admin creds, then re-launch the
    # app so StartupViewModel re-checks status and routes to Login.
    api_base = f"http://localhost:{args.api_port}"
    if not await _ios_complete_setup_if_needed(
        api_base=api_base,
        devicectl_udid=devicectl_udid,
        bundle_id=args.ios_bundle_id,
        test_url=test_url,
        api_url=api_url,
    ):
        # Setup failed or relaunch didn't come back healthy. Bail with cleanup.
        _kill_iproxy_children()
        return 1

    print()
    print(
        f"✅ Ready. iOS test-automation: http://localhost:{args.desktop_port}  Backend: http://localhost:{args.api_port}"
    )
    return 0


async def _ios_complete_setup_if_needed(
    api_base: str,
    devicectl_udid: str,
    bundle_id: str,
    test_url: str,
    api_url: str,
) -> bool:
    """If the iOS device is at the Setup wizard, complete setup via API
    and re-launch the app so the UI routes to Login.

    Returns True if the device is ready (already configured OR successfully
    set up + relaunched), False on a real failure that should abort bring-up.

    The relaunch is necessary because iOS StartupViewModel only checks
    /v1/setup/status once at startup; without it, the UI stays on the
    Setup screen even though the backend has been told setup is complete.
    """
    # Probe setup status
    try:
        r = requests.get(f"{api_base}/v1/setup/status", timeout=5)
    except Exception as e:  # noqa: BLE001
        print(f" [WARN] /v1/setup/status probe failed: {e} — assuming configured, walk may fail at login")
        return True
    if r.status_code != 200:
        print(f" [WARN] /v1/setup/status returned {r.status_code} — assuming configured, walk may fail at login")
        return True
    data = r.json().get("data", r.json())  # tolerate either envelope
    first_run = bool(data.get("first_run") or data.get("firstRun") or data.get("is_first_run"))
    if not first_run:
        print(f" [INFO] device already configured (first_run=false) — skipping setup")
        return True

    # Device needs setup. POST /v1/setup/complete with QA creds.
    print(f" device is first-run — completing setup via {api_base}/v1/setup/complete")
    payload = {
        # On iOS the embedded backend runs without mock-llm — use a placeholder
        # OpenAI config; the walk-test doesn't exercise the LLM path.
        "llm_provider": "openai",
        "llm_api_key": "test-key-for-ios-walk",
        "llm_model": "gpt-4",
        "template_id": "default",
        "enabled_adapters": ["api"],
        "adapter_config": {},
        "admin_username": TEST_ADMIN_USERNAME,
        "admin_password": TEST_ADMIN_PASSWORD,
        # agent_port is the *embedded* backend's port (always 8080 inside the
        # device sandbox), not the host-side iproxy-forwarded port.
        "agent_port": 8080,
    }
    try:
        r = requests.post(f"{api_base}/v1/setup/complete", json=payload, timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f" [FAIL] /v1/setup/complete error: {e}")
        return False
    if r.status_code != 200:
        print(f" [FAIL] /v1/setup/complete returned {r.status_code}: {r.text[:300]}")
        return False
    print(f" [OK] setup completed — admin user '{TEST_ADMIN_USERNAME}' created")

    # Re-launch the app so the StartupViewModel re-checks setup status.
    # iproxy children stay running — the kernel-level forward survives the
    # app restart, the iOS-side socket gets rebound when the app comes back.
    print(f" re-launching {bundle_id} so the UI routes to Login...")
    relaunch_cmd = [
        "xcrun",
        "devicectl",
        "device",
        "process",
        "launch",
        "--device",
        devicectl_udid,
        "--terminate-existing",
        # Keep both env vars on the relaunch — TESTING_MODE no longer
        # strictly needed (setup already complete) but harmless, and
        # consistent with the initial launch is easier to reason about.
        "--environment-variables",
        '{"CIRIS_TEST_MODE":"true","CIRIS_TESTING_MODE":"true"}',
        bundle_id,
    ]
    try:
        result = subprocess.run(relaunch_cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        print(" [FAIL] devicectl re-launch timed out after 60s")
        return False
    if result.returncode != 0:
        print(f" [FAIL] re-launch failed: {result.stderr.strip() or result.stdout.strip()}")
        return False

    # Wait for both endpoints to come back. Same loop shape as the initial poll
    # — but with a longer test-automation timeout, because Compose has to do a
    # full re-mount before the embedded server rebinds :9091.
    print("  ⏳ waiting for test-automation + backend to come back after re-launch...")
    loop = asyncio.get_event_loop()
    deadline = loop.time() + 90
    test_ok = api_ok = False
    while loop.time() < deadline:
        if not test_ok:
            try:
                if requests.get(test_url, timeout=2).status_code == 200:
                    test_ok = True
                    print(" [OK] test-automation back up after re-launch")
            except Exception:
                pass
        if not api_ok:
            try:
                if requests.get(api_url, timeout=2).status_code in (200, 503):
                    api_ok = True
                    print(" [OK] backend api back up after re-launch")
            except Exception:
                pass
        if test_ok and api_ok:
            return True
        await asyncio.sleep(1)
    print(f" [FAIL] post-setup re-launch did not come back healthy (test_ok={test_ok}, api_ok={api_ok})")
    return False


async def run_federation_walk(args: argparse.Namespace) -> int:
    """Walk the federation Network screens via the test-automation server.

    Targets the Compose-Desktop app (default) or a physical iOS device
    (`--platform ios`). On iOS the test-automation server runs in the
    embedded Beeware Python; iproxy forwards device:9091/8080 to host
    :18091/:18080. The walk itself is platform-agnostic — only the
    transport URLs and bring-up path differ.

    Exit codes:
        0 — all walk steps PASS
        1 — at least one FAIL / ERROR (or only-SKIP outside of expected cascade)
        2 — cannot reach the test-automation server
    """
    server_url = f"http://localhost:{args.desktop_port}"
    api_base_url = f"http://localhost:{args.api_port}"
    is_android = bool(getattr(args, "android", False))
    is_ios = bool(getattr(args, "ios", False))
    if is_android and is_ios:
        print("federation: --android and --ios are mutually exclusive")
        return 2
    target_label = "android emulator" if is_android else "ios device" if is_ios else "desktop app"

    # Optional full bring-up: backend + client, then walk.
    if args.launch:
        if is_android:
            print("federation: --launch --android — emulator + adb-forward bring-up")
            rc = await run_android_up(args)
        elif is_ios:
            print("federation: --launch --ios — devicectl + iproxy bring-up")
            rc = await run_ios_up(args)
        else:
            print("federation: --launch requested, bringing up backend + desktop first")
            rc = await run_desktop_up(args)
        if rc != 0:
            print(f"federation: bring-up failed (rc={rc})")
            return rc

    # Verify reachability
    print(f"federation: checking {target_label} test-automation server at {server_url}")
    if not await check_desktop_app_running(server_url):
        print()
        print(f"FATAL: cannot reach the {target_label}'s test-automation server at {server_url}.")
        if is_android:
            print("       Either re-run with --launch --android, or manually:")
            print("         ~/Android/Sdk/platform-tools/adb shell am force-stop ai.ciris.mobile.debug")
            print("         ~/Android/Sdk/platform-tools/adb install -r androidApp-debug.apk")
            print(
                "         ~/Android/Sdk/platform-tools/adb shell am start -n ai.ciris.mobile.debug/ai.ciris.mobile.MainActivity"
            )
            print(f"         ~/Android/Sdk/platform-tools/adb forward tcp:{args.desktop_port} tcp:9091")
        elif is_ios:
            print("       Make sure the iOS app is running with CIRIS_TEST_MODE=true")
            print("       and that iproxy is forwarding the device's :9091/:8080:")
            print()
            print("         xcrun devicectl device process launch -d <UDID> \\")
            print("           --terminate-existing \\")
            print('           --environment-variables \'{"CIRIS_TEST_MODE":"true"}\' \\')
            print("           ai.ciris.mobile")
            print(f"         iproxy {args.desktop_port} 9091 -u <UDID> &")
            print(f"         iproxy {args.api_port} 8080 -u <UDID> &")
            print()
            print("       or use --launch --ios to bring it all up automatically.")
        else:
            print("       Start the desktop app with CIRIS_TEST_MODE=true first, e.g.:")
            print("         export CIRIS_TEST_MODE=true")
            print("         cd client && ./gradlew :desktopApp:run")
            print("       or use --launch to bring up the full stack.")
        return 2

    config = DesktopAppConfig(
        server_url=server_url,
        screenshot_dir=args.output_dir,
    )
    helper = DesktopAppHelper(config)
    await helper.start()
    try:
        walker = FederationWalkTest(
            helper=helper,
            verbose=args.verbose,
            login_username=args.username or "admin",
            login_password=args.password or "qa_test_password_12345",
            api_base_url=api_base_url,
        )
        report = await walker.run()
    finally:
        await helper.stop()
        if is_android and args.launch:
            _android_teardown(args, keep_open=args.keep_open)

    # Output
    report.print_summary()
    if args.json_report:
        Path(args.json_report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_report).write_text(report.to_json())
        print(f"federation: JSON report written to {args.json_report}")

    if report.all_passed:
        return 0
    return 1


async def run_desktop_tests(args: argparse.Namespace) -> int:
    """Run desktop app tests."""
    # Check if desktop app is running
    print(" Checking CIRIS Desktop app...")
    server_url = f"http://localhost:{args.desktop_port}"

    if not await check_desktop_app_running(server_url):
        # SAY WHAT ANSWERED. This printed one message for three different
        # conditions and named only one of them, so on Android it announced that
        # the DESKTOP app was not in test mode seconds after bring-up had
        # reported the Android test server healthy on that very port.
        from .desktop_app_helper import attribute_device_failure, describe_test_server

        print(f"\n[FAIL] the test server is not usable: {await describe_test_server(server_url)}")
        platform = getattr(args, "platform", "desktop")
        # NAME THE OWNER. On a device the automation port and the embedded
        # backend are two listeners in one process, so asking the sibling turns
        # "something died" into "which layer died" — the difference between a
        # client bug and a process kill, which run 33704781359 could not settle.
        if platform in ("android", "ios"):
            backend_url = f"http://localhost:{getattr(args, 'port', 8080)}"
            print(f"  -> {await attribute_device_failure(server_url, backend_url)}")
        if platform == "android":
            print("\nAndroid: the app is launched with `--es CIRIS_TEST_MODE true` and")
            print("  `setprop debug.CIRIS_TEST_MODE true`, and a debug build should set")
            print("  BuildConfig.TEST_MODE_ENABLED itself. If /health is up but testMode")
            print("  is false, the build is not a test-mode build — check with:")
            print("    adb shell am start -n <pkg>/<activity> --es CIRIS_TEST_MODE true")
            print("    adb logcat -d | grep -i testmode")
        elif platform == "ios":
            print("\niOS: simctl forwards only SIMCTL_CHILD_-prefixed env vars;")
            print("  CIRIS_TEST_MODE must be set as SIMCTL_CHILD_CIRIS_TEST_MODE.")
        else:
            print("\nTo start the desktop app with test mode:")
            print("  export CIRIS_TEST_MODE=true")
            print("  ciris-desktop        # or: CIRIS_TEST_MODE=true ciris-agent")
        return 1

    print("[OK] Desktop app running with test mode")

    # Create and start runner
    config = DesktopAppConfig(
        server_url=server_url,
        screenshot_dir=args.output_dir,
    )
    runner = DesktopAppTestRunner(config=config, verbose=args.verbose)

    try:
        await runner.start()

        if args.command == "desktop":
            # Just show element tree
            await runner.test_element_tree()
            return 0

        elif args.command == "desktop-login":
            success = await runner.test_login_flow(
                username=args.username or "admin",
                password=args.password or "qa_test_password_12345",
            )
            runner.print_summary()
            return 0 if success else 1

        elif args.command == "desktop-chat":
            success = await runner.test_chat_flow(
                message=args.message or "Hello, can you hear me?",
            )
            runner.print_summary()
            return 0 if success else 1

        elif args.command == "desktop-setup":
            # First-run wizard (2.9.14, three screens):
            #   YOU (fed-ID + account + age) → JOIN_FEDERATION (consent)
            #   → [AI] → COMPLETE
            _byok_key = args.llm_key
            if not _byok_key and args.llm_key_file:
                _key_path = Path(args.llm_key_file).expanduser()
                if _key_path.is_file():
                    _byok_key = _key_path.read_text().strip()
                else:
                    print(f" [WARN] --llm-key-file not found: {_key_path} — falling back to keyless local")
            success = await runner.test_setup_wizard_flow(
                username=args.username or TEST_ADMIN_USERNAME,
                password=args.password or TEST_ADMIN_PASSWORD,
                fed_label=args.fed_label,
                announce=not args.no_announce,
                trace_opt_in=not args.no_trace_opt_in,
                llm_key_expect_rejected=getattr(args, "llm_key_expect_rejected", False),
                llm_require_live_models=getattr(args, "llm_require_live_models", False),
                llm_provider=args.llm_provider,
                llm_api_key=_byok_key,
                llm_model=args.llm_model,
            )
            runner.print_summary()
            return 0 if success else 1

        elif args.command == "desktop-catchup":
            # Catch-up "Add Federation ID" flow (AddFederationIdScreen):
            #   btn_add_federation_id → input_fed_label →
            #   toggle_announce_ownership (gates toggle_trace_opt_in) →
            #   btn_add_fedid_confirm
            success = await runner.test_catchup_add_fedid_flow(
                fed_label=args.fed_label,
                announce=not args.no_announce,
                trace_opt_in=not args.no_trace_opt_in,
            )
            runner.print_summary()
            return 0 if success else 1

    finally:
        await runner.stop()

    return 0


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Handle list command
    if args.command == "list":
        list_tests()
        return 0

    # Handle desktop-up (full orchestration: wipe → setup → launch → login)
    if args.command == "desktop-up":
        return await run_desktop_up(args)

    # Federation Network screen walk-test
    if args.command == "federation":
        return await run_federation_walk(args)

    # Node-client first-run setup wizard: --launch brings up backend in
    # FIRST-RUN mode + desktop app sitting on the Setup wizard, then drives it.
    if args.command == "desktop-setup" and args.launch:
        # BRING UP THE PLATFORM THAT WAS ASKED FOR.
        #
        # This called run_desktop_first_run_up() unconditionally, so
        # `--platform android` booted no emulator and installed no APK — it
        # started the DESKTOP app, on the Android port, and the whole run was then
        # reported as an Android result. A gate that claims five platforms while
        # exercising three is worse than one that admits to three.
        #
        # `--platform` is the single source of truth (platforms.py); bring-up is
        # the one place it legitimately changes behaviour.
        platform = getattr(args, "platform", None) or "desktop"
        if platform == "android":
            print("desktop-setup: --platform android — emulator + adb-forward bring-up")
            rc = await run_android_up(args)
        elif platform == "ios":
            print("desktop-setup: --platform ios — simulator bring-up")
            rc = await run_ios_simulator_up(args)
        else:
            rc = await run_desktop_first_run_up(args)
        if rc != 0:
            print(f"desktop-setup: {platform} bring-up failed (rc={rc})")
            return rc

    # Catch-up Add-Federation-ID flow: --launch brings up the full configured
    # + logged-in stack first (same bring-up as desktop-up).
    if args.command == "desktop-catchup" and args.launch:
        rc = await run_desktop_up(args)
        if rc != 0:
            print(f"desktop-catchup: bring-up failed (rc={rc})")
            return rc

    # Handle desktop commands (connect to already-running app)
    if args.command.startswith("desktop"):
        return await run_desktop_tests(args)

    # Legacy browser-based testing
    # Ensure Playwright is installed
    print(" Checking Playwright installation...")
    try:
        ensure_playwright_installed()
        print("[OK] Playwright ready")
    except Exception as e:
        print(f"[FAIL] Playwright setup failed: {e}")
        print("   Run: pip install playwright && playwright install firefox")
        return 1

    # Build configs
    server_config = ServerConfig(
        port=args.port,
        wipe_data=args.wipe and not args.no_wipe,
        mock_llm=args.mock_llm,
        startup_timeout=args.timeout,
    )

    browser_config = BrowserConfig(
        headless=args.headless,
        slow_mo=args.slow_mo,
        screenshot_dir=args.output_dir,
    )

    test_config = WebUITestConfig.from_env()
    test_config.llm_provider = args.provider

    if args.api_key:
        test_config.llm_api_key = args.api_key

    if args.model:
        test_config.llm_model = args.model

    # Get tests to run
    tests = get_test_list(args.command, args.tests)

    # Create runner
    runner = WebUITestRunner(
        server_config=server_config,
        browser_config=browser_config,
        test_config=test_config,
        keep_open=args.keep_open,
    )

    # Run tests
    if tests:
        suite = await runner.run_selected_tests(tests)
    else:
        suite = await runner.run_e2e_flow()

    # Print summary and save report
    runner.print_summary(suite)
    report_path = runner.save_report(suite)
    print(f" Report saved: {report_path}")

    return 0 if suite.success else 1


async def _main_with_capture() -> int:
    """Run the command, and on SUCCESS capture the final screen.

    Wrapped here rather than inside each command so every flow — today's
    `interact`, tomorrow's p2p chat or video — gets the same review artifact
    without opting in.

    ON SUCCESS *AND* FAILURE. This was success-only on the theory that the
    gallery should show "what shipped", not "what broke". That cost a whole
    run: the reply assertion failed, there was no screenshot, and the one
    question worth answering — was the answer on screen? — could not be settled
    from the artifacts at all. The failing screen is the single most useful
    frame in the run, and the gallery already labels each tile PASS/FAIL, so a
    red tile with a photograph beats a red tile with a gap.

    The capture NEVER changes the exit code. It is evidence for a human, not an
    assertion: a run that answered correctly but could not be photographed still
    passed, and failing it would make the gallery a source of false red.
    """
    rc = await main()

    dest = getattr(_LAST_ARGS, "screenshot_on_success", None) if _LAST_ARGS else None
    if not dest:
        return rc

    try:
        from pathlib import Path as _Path

        from .platforms import CaptureKind, build_platform

        platform = build_platform(_LAST_ARGS)
        written = platform.capture(CaptureKind.SCREENSHOT, _Path(dest))
        if written:
            print(f" [OK] screenshot ({platform.name}) -> {written}")
        else:
            # Say so rather than leaving a silently absent file: an empty slot in
            # the gallery should be explained, not mysterious.
            print(f" [WARN] {platform.name}: no screenshot captured (endpoint or tool unavailable)")
    except Exception as exc:  # noqa: BLE001
        print(f" [WARN] screenshot capture failed (non-fatal): {type(exc).__name__}: {exc}")
    return rc


def run() -> None:
    """Entry point for console script."""
    try:
        sys.exit(asyncio.run(_main_with_capture()))
    except KeyboardInterrupt:
        print("\n[WARN] Test interrupted by user")
        sys.exit(130)


if __name__ == "__main__":
    run()
