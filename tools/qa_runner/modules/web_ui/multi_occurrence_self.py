"""One person across all five platforms, through the UI, with no AI.

The `multi-occurrence-self` scenario of `five-platform-live-qa.yml`. Each platform
is its own job, because an iOS simulator shares its host's ports with a macOS
desktop node and all five nodes must be up at once:

    linux    runs the wizard and creates the fedID (no assistant)
    android  joins; linux approves
    windows  joins; the roster holds 2 keys, so a second key must agree
    macos    joins; 2 of 3 must agree
    ios      joins; 3 of 4 must agree

Then every device must show all five under one person. Nothing here calls a node's
API: everything a person would do goes through the client's TestAutomationServer.

RENDEZVOUS. Jobs on separate runners cannot reach each other, and an artifact can
only be uploaded by a workflow step, not many times from inside one. So signals
are commit statuses on the run's SHA, one context per fact. They are public, and
only carry what is safe in public: stage flags, a match code, a contact code. No
PIN or secret ever crosses; each client reads its own claim PIN from its own disk.

A device that fails says so, and every device waiting on it stops at once with
that reason rather than sitting out a deadline.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
from typing import Callable, Dict, List, Optional

#: The order they join. The first creates the identity. `MOS_DEVICES` narrows it,
#: for a run where only some platforms carry the server under test: a device on an
#: older server can't stand in for it, and one failed join ends the scenario.
ALL_DEVICES = ["linux", "android", "windows", "macos", "ios"]
_ASKED = os.environ.get("MOS_DEVICES", "").split()
ORDER = [d for d in ALL_DEVICES if d in _ASKED] if _ASKED and "all" not in _ASKED else ALL_DEVICES
#: Past this many keys an addition is held for the roster (CC 3.3.6.3).
UNILATERAL_KEYS = 1
#: A commit status description holds 140 characters.
CHUNK = 130
#: macOS runners queue and iOS is slow, so a peer gets a long time to arrive.
PEER_DEADLINE_S = 3000.0
#: A contact request took ~93 s to cross; a held addition crosses the same way.
STEP_DEADLINE_S = 600.0
#: From the wizard finishing to the client settling on the node.
HANDOVER_DEADLINE_S = 90.0
#: A cold device reaching the wizard's first question.
WIZARD_DEADLINE_S = 180.0
POLL_S = 10.0


def needed_assents(keys_before: int) -> int:
    """Extra signatures an addition needs beyond the proposer's, from a roster of
    `keys_before`: strictly more than half must agree (CC 4.5.13 self_roster_add)."""
    if keys_before <= UNILATERAL_KEYS:
        return 0
    return keys_before // 2 + 1 - 1


def chunks(text: str, size: int = CHUNK) -> List[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


class SignalFailed(RuntimeError):
    """Another device reported failure; waiting further is pointless."""


class Signals:
    """Facts shared between the jobs of one run, as commit statuses."""

    def __init__(
        self,
        repo: str,
        sha: str,
        run: str,
        gh: Optional[Callable[[List[str]], str]] = None,
        sleep: Callable[[float], "asyncio.Future"] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.repo, self.sha, self.prefix = repo, sha, f"mos/{run}/"
        self._gh = gh or self._run_gh
        self._sleep, self._clock = sleep, clock

    @staticmethod
    def _run_gh(args: List[str]) -> str:
        # One failed poll of GitHub must not end a five-device run. Blocks the
        # loop while it backs off, as the call itself does.
        for wait in (2, 5, 15, 30, None):
            try:
                return subprocess.run(
                    ["gh", *args], check=True, capture_output=True, text=True, timeout=90
                ).stdout
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if wait is None:
                    raise
                time.sleep(wait)
        raise AssertionError("unreachable")

    def put(self, key: str, value: str = "yes") -> None:
        self._gh(
            [
                "api",
                f"repos/{self.repo}/statuses/{self.sha}",
                "-f",
                "state=success",
                "-f",
                f"context={self.prefix}{key}",
                "-f",
                f"description={value}",
            ]
        )

    def all(self) -> Dict[str, str]:
        raw = self._gh(
            ["api", "--paginate", f"repos/{self.repo}/commits/{self.sha}/statuses?per_page=100"]
        )
        rows = json.loads(raw.replace("][", ",")) if raw.strip() else []
        out: Dict[str, str] = {}
        # Newest first: the first row seen for a context is its current value.
        for row in rows:
            ctx = row.get("context", "")
            if ctx.startswith(self.prefix):
                out.setdefault(ctx[len(self.prefix) :], row.get("description") or "")
        return out

    def put_text(self, key: str, text: str) -> None:
        parts = chunks(text)
        for i, part in enumerate(parts):
            self.put(f"{key}/{i}", part)
        self.put(f"{key}/count", str(len(parts)))

    @staticmethod
    def _failure(facts: Dict[str, str]) -> Optional[str]:
        for key, value in facts.items():
            if key.startswith("failed/"):
                return f"{key[len('failed/'):]}: {value}"
        return None

    async def wait(self, key: str, deadline_s: float) -> str:
        end = self._clock() + deadline_s
        while True:
            facts = self.all()
            failed = self._failure(facts)
            if failed:
                raise SignalFailed(f"stopping, another device failed ({failed})")
            if key in facts:
                return facts[key]
            if self._clock() >= end:
                raise TimeoutError(f"no {key!r} after {deadline_s:.0f}s")
            await self._sleep(POLL_S)

    async def wait_text(self, key: str, deadline_s: float) -> str:
        count = int(await self.wait(f"{key}/count", deadline_s))
        facts = self.all()
        return "".join(facts[f"{key}/{i}"] for i in range(count))


class Device:
    """One client, driven the way a person drives it."""

    def __init__(self, runner, name: str, signals: Signals, password: str):
        self.runner, self.helper = runner, runner.helper
        self.name, self.signals, self.password = name, signals, password

    def log(self, msg: str) -> None:
        print(f"[{self.name} {time.strftime('%H:%M:%S')}] {msg}", flush=True)

    async def tags(self, prefix: str) -> List[str]:
        return [t for t in (await self.helper.get_element_list()) if t.startswith(prefix)]

    async def must_click(self, tag: str, timeout_ms: int = 20000) -> None:
        if not await self.helper.wait_for_element(tag, timeout=timeout_ms) or not await self.helper.click(tag):
            await self.runner._dump_tree(f"could not click {tag}")
            raise RuntimeError(f"{self.name}: could not click {tag}")

    async def identity(self) -> None:
        why = await self.helper.reach_surface("identity-management")
        if why:
            await self.runner._dump_tree("identity")
            raise RuntimeError(f"{self.name}: could not reach My Identity: {why}")

    async def text(self, tag: str) -> str:
        el = await self.helper.get_element(tag)
        return (el.text or "") if el else ""

    # ── the creator ──────────────────────────────────────────────────────────

    async def create_identity(self, fed_label: str) -> None:
        self.log(f"wizard: creating {fed_label}, no assistant")
        ok = await self.runner.test_setup_wizard_flow(
            username="qaadmin",
            password=self.password,
            fed_label=fed_label,
            announce=True,
            # Sending traces is what grants the canonical consent to carry this
            # node's rows. Without it nothing of this identity leaves the node,
            # announced or not, and no other device can find it.
            trace_opt_in=True,
            run_without_ai=True,
        )
        if not ok:
            raise RuntimeError("the setup wizard did not complete")
        await self.sign_in_after_handover()

    async def sign_in_after_handover(self) -> None:
        """The client follows the backend to the node, then lands on the login
        screen or on the shell. Either can take a while: wait for one of them."""
        deadline = time.monotonic() + HANDOVER_DEADLINE_S
        while time.monotonic() < deadline:
            tags = {e.test_tag for e in await self.helper.get_elements()}
            if "btn_my_things" in tags:
                return
            if tags & {"input_username", "btn_local_login"}:
                if not await self.runner.test_login_flow(
                    username="qaadmin", password=self.password, run_without_ai=True
                ):
                    raise RuntimeError("could not log in after the wizard")
                return
            await asyncio.sleep(1)
        raise RuntimeError("neither the login screen nor the shell appeared after the wizard")

    async def publish_contact_code(self) -> None:
        why = await self.helper.reach_surface("contacts")
        if why:
            raise RuntimeError(f"could not reach People for the contact code: {why}")
        await self.must_click("btn_contact_code_open")
        if not await self.helper.wait_for_element("text_contact_code", timeout=30000):
            raise RuntimeError("no contact code appeared")
        code = await self.text("text_contact_code")
        if not code:
            raise RuntimeError("the contact code is empty")
        self.log(f"contact code: {len(code)} characters")
        self.signals.put_text("code", code)

    async def approve(self, joiner: str, keys_before: int) -> None:
        # The add-a-device window lasts minutes and a macOS job can queue for far
        # longer, so it opens only once the joiner is up.
        await self.signals.wait(f"ready/{joiner}", PEER_DEADLINE_S)
        await self.identity()
        await self.must_click("btn_approve_device_open")
        self.signals.put(f"window/{joiner}")
        match = await self.signals.wait(f"requested/{joiner}", PEER_DEADLINE_S)
        end = time.monotonic() + STEP_DEADLINE_S
        request_id = None
        while request_id is None:
            for tag in await self.tags("text_approve_device_code_"):
                if await self.text(tag) == match:
                    request_id = tag[len("text_approve_device_code_") :]
            if request_id is None:
                if time.monotonic() > end:
                    await self.runner._dump_tree("approve")
                    raise RuntimeError(f"{joiner}'s request with code {match} never appeared")
                await asyncio.sleep(3)
        self.log(f"{joiner}: the code on screen matches ({match})")
        await self.must_click(f"btn_approve_device_{request_id}")
        await self.must_click("btn_confirm_device_request_confirm")
        held = needed_assents(keys_before) > 0
        if held and not await self.helper.wait_for_element("text_approve_device_held_window", timeout=60000):
            await self.runner._dump_tree("held")
            raise RuntimeError(f"a roster of {keys_before} did not hold {joiner}'s addition")
        self.signals.put(f"approved/{joiner}", "held" if held else "direct")

    # ── a joining device ─────────────────────────────────────────────────────

    async def send_join_request(self) -> None:
        """Send, and as a person would, send again while the other device's
        address is still on its way, if the client is not already doing so."""
        end = time.monotonic() + STEP_DEADLINE_S
        while time.monotonic() < end:
            # The client re-sends by itself for five minutes while the other
            # device can't be reached, with the button hidden, so a person would
            # only press it again once it comes back.
            if await self.helper.wait_for_optional_element("btn_add_device_send", timeout=1000):
                await self.must_click("btn_add_device_send")
            if await self.helper.wait_for_optional_element("text_add_device_match_code", timeout=45000):
                return
            self.log(f"no match code yet: {await self.text('add_device_refusal')!r}")
        await self.runner._dump_tree("match code")
        raise RuntimeError(f"no match code: {await self.text('add_device_refusal')}")

    async def type_into(self, tag: str, text: str) -> None:
        """The field below the fold, or not composed yet, on a phone's screen."""
        await self.helper.wait_for_optional_element(tag, timeout=30000)
        await self.helper.scroll_into_view(tag)
        if not await self.helper.input_text(tag, text):
            await self.runner._dump_tree(f"could not fill {tag}")
            raise RuntimeError(f"{self.name}: could not fill {tag}")

    async def open_wizard(self) -> None:
        """A first run can start at the Login chooser, as the creator's wizard
        finds too: take the local path until the wizard's first question shows."""
        end = time.monotonic() + WIZARD_DEADLINE_S
        while time.monotonic() < end:
            tags = {e.test_tag for e in await self.helper.get_elements()}
            if "btn_setup_add_this_device" in tags:
                return
            if "btn_local_login" in tags:
                await self.helper.click("btn_local_login")
            await asyncio.sleep(1)
        await self.runner._dump_tree("open wizard")
        raise RuntimeError("the wizard's first question never appeared")

    async def join(self) -> None:
        await self.signals.wait(f"window/{self.name}", PEER_DEADLINE_S)
        code = await self.signals.wait_text("code", 60)
        self.log("wizard: adding this device to the identity")
        await self.open_wizard()
        await self.must_click("btn_setup_add_this_device", 60000)
        await self.type_into("input_add_device_name", f"qa-{self.name}")
        await self.type_into("input_add_device_contact", code)
        await self.send_join_request()
        self.signals.put(f"requested/{self.name}", await self.text("text_add_device_match_code"))
        await self.signals.wait(f"approved/{self.name}", PEER_DEADLINE_S)
        await self.finish_wizard_after_approval()
        self.signals.put(f"joined/{self.name}")

    async def finish_wizard_after_approval(self) -> None:
        """The approval only holds the claim. A person presses on through the
        wizard, and its last step applies the claim and collects the session."""
        end = time.monotonic() + STEP_DEADLINE_S
        account_filled = answered_ai = answered_traces = False
        while time.monotonic() < end:
            tags = {e.test_tag for e in await self.helper.get_elements()}
            if "btn_my_things" in tags:
                return
            if "btn_add_device_finish_retry" in tags:
                await self.helper.click("btn_add_device_finish_retry")
            elif "btn_next" in tags:
                if "input_username" in tags and not account_filled:
                    await self.type_into("input_username", "qaadmin")
                    await self.type_into("input_password", self.password)
                    await self.type_into("input_password_confirm", self.password)
                    account_filled = True
                if "opt_run_without_ai" in tags and not answered_ai:
                    await self.helper.click("opt_run_without_ai")
                    answered_ai = True
                if "trace_consent_yes" in tags and not answered_traces:
                    await self.helper.click("trace_consent_yes")
                    answered_traces = True
                await self.helper.click("btn_next")
            elif tags & {"input_username", "btn_local_login"}:
                await self.sign_in_after_handover()
                return
            await asyncio.sleep(2)
        await self.runner._dump_tree("after join")
        raise RuntimeError(f"never left the wizard: {await self.text('text_add_device_status')}")

    async def assent_to(self, joiner: str) -> None:
        """Agree to `joiner`'s held addition, if it still needs this key."""
        await self.signals.wait(f"approved/{joiner}", PEER_DEADLINE_S)
        end = time.monotonic() + STEP_DEADLINE_S
        while time.monotonic() < end:
            if f"joined/{joiner}" in self.signals.all():
                return  # Quorum landed without this key.
            await self.identity()
            buttons = await self.tags("btn_self_roster_assent_")
            if buttons:
                await self.must_click(buttons[0])
                await self.must_click("btn_confirm_roster_answer_confirm")
                self.log(f"assented to {joiner}'s addition")
                self.signals.put(f"assent/{joiner}/{self.name}")
                return
            await asyncio.sleep(10)
        await self.runner._dump_tree("assent")
        raise RuntimeError(f"no roster proposal for {joiner} reached {self.name}")

    # ── the finish line ──────────────────────────────────────────────────────

    async def prove_five(self) -> None:
        """Every device shows all five, or the run failed. Rows are read from the
        screen: a passing status is not evidence a person would see this."""
        await self.signals.wait(f"joined/{ORDER[-1]}", PEER_DEADLINE_S)
        end = time.monotonic() + STEP_DEADLINE_S
        rows: List[str] = []
        while time.monotonic() < end:
            await self.identity()
            rows = [t for t in await self.tags("identity_row_")]
            if len(rows) >= len(ORDER):
                break
            await asyncio.sleep(15)
        self.log(f"device rows on this screen: {len(rows)}")
        if len(rows) < len(ORDER):
            await self.runner._dump_tree("five rows")
            raise RuntimeError(f"shows {len(rows)} of {len(ORDER)} devices")
        self.signals.put(f"sees-five/{self.name}", str(len(rows)))


async def play(device: Device, run: str) -> None:
    """This device's part of the whole run, in order."""
    name, signals = device.name, device.signals
    position = ORDER.index(name)
    signals.put(f"ready/{name}")
    if position == 0:
        await device.create_identity(f"mos-{run}")
        await device.publish_contact_code()
        for i, joiner in enumerate(ORDER[1:], start=1):
            await device.approve(joiner, keys_before=i)
            await signals.wait(f"joined/{joiner}", PEER_DEADLINE_S)
    else:
        await signals.wait(f"joined/{ORDER[position - 1]}" if position > 1 else "code/count", PEER_DEADLINE_S)
        await device.join()
        # Help every later addition that still needs this key.
        for i, joiner in enumerate(ORDER[position + 1 :], start=position + 1):
            if needed_assents(i) > 0:
                await device.assent_to(joiner)
    await device.prove_five()
    # Stay up until everyone has checked: a node gone early is a row gone stale.
    for other in ORDER:
        await signals.wait(f"sees-five/{other}", PEER_DEADLINE_S)
    device.log("one person across five devices")


async def run_device(runner, args) -> bool:
    """`desktop-mos`: play this device's part, and report failure to the others."""
    env = os.environ
    signals = Signals(env["GITHUB_REPOSITORY"], env["GITHUB_SHA"], f"{env['GITHUB_RUN_ID']}-{env.get('GITHUB_RUN_ATTEMPT', '1')}")
    device = Device(runner, args.mos_device, signals, args.password or "qa_test_password_12345")
    try:
        await play(device, env["GITHUB_RUN_ID"])
        return True
    except SignalFailed as e:
        device.log(str(e))
        return False
    except Exception as e:  # noqa: BLE001 - reported to the other jobs, then re-raised as a failure
        reason = re.sub(r"\s+", " ", str(e))[:130] or type(e).__name__
        device.log(f"FAILED: {reason}")
        signals.put(f"failed/{device.name}", reason)
        return False
