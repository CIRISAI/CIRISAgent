"""Named UI flows, written once and run on every platform.

A Scenario is "a thing a user does", expressed against the shared
`TestAutomationServer` and nothing else. It never asks which platform it is on:
that is `platforms.py`'s job, and a scenario that needs to know is a bug in that
seam rather than a licence to branch.

WHY THIS EXISTS RATHER THAN A HARDCODED SEQUENCE. The first flow we need is
"configure a live LLM, reach Interact, send a message, get an answer". It will
not be the last — p2p chat and video calling are coming, and a hardcoded
setup->interact->assert chain has to be torn apart to admit them. Registering
flows by name means a new capability is a new file plus one registry line, and
the CI matrix picks it up by naming it.

WHY `supports()` TAKES A PLATFORM. Not every flow will run everywhere, and the
honest way to express that is per-scenario rather than a platform list buried in
CI. A scenario that cannot run on a target must SKIP loudly — never silently
pass, which is the failure mode that let v2.9.42 ship with no APK and 0.5.191
with no XCFramework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional, Protocol

from .platforms import Platform


class ScenarioResult:
    """PASS / FAIL / SKIP with a reason — never a bare bool.

    A bool cannot distinguish "this flow ran and was fine" from "this flow never
    ran", and conflating those is how a green tick comes to mean nothing.
    """

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"

    def __init__(self, status: str, name: str, detail: str = "", screenshot: Optional[str] = None):
        self.status = status
        self.name = name
        self.detail = detail
        self.screenshot = screenshot

    @property
    def ok(self) -> bool:
        return self.status in (self.PASS, self.SKIP)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<{self.name}: {self.status}{' ' + self.detail if self.detail else ''}>"


class Scenario(Protocol):
    """One user-facing flow, platform-agnostic by construction."""

    name: str
    description: str

    def supports(self, platform: Platform) -> bool:
        """May this flow run against `platform`? False means SKIP, not FAIL."""
        ...

    async def run(self, helper, platform: Platform) -> ScenarioResult:
        """Drive the flow through `helper` (the shared TestAutomationServer client)."""
        ...


@dataclass
class _Registry:
    """Scenario lookup by name.

    Deliberately tiny. The value is the seam, not the machinery: CI names a
    scenario, this resolves it, and adding `p2p_chat` later touches this file
    once.
    """

    _scenarios: Dict[str, Scenario] = field(default_factory=dict)

    def register(self, scenario: Scenario) -> Scenario:
        if scenario.name in self._scenarios:
            raise ValueError(f"scenario {scenario.name!r} is already registered")
        self._scenarios[scenario.name] = scenario
        return scenario

    def get(self, name: str) -> Scenario:
        try:
            return self._scenarios[name]
        except KeyError:
            known = ", ".join(sorted(self._scenarios)) or "(none)"
            raise KeyError(f"unknown scenario {name!r}; registered: {known}") from None

    def names(self) -> List[str]:
        return sorted(self._scenarios)


REGISTRY = _Registry()


class InteractScenario:
    """THE release gate: a message in must produce a message out.

    This is the flow the 5-platform CI job runs. It asserts through the UI rather
    than the API on purpose — the API answering while the screen stays blank is
    precisely the failure worth catching, and it is what "Disconnected with no
    reply and no error" looked like in the field.
    """

    name = "interact"
    description = "Reach the Interact screen, send a message, and require a rendered reply"

    def supports(self, platform: Platform) -> bool:
        # Every platform runs the same Compose client, so this flow is universal.
        # If that ever stops being true, the honest fix is a SKIP here — not a
        # branch inside run().
        return True

    #: What gets typed. A greeting rather than a prompt with a checkable answer,
    #: because the assertion is "the UI rendered a reply", not "the model was
    #: correct" — grading content here would make an LLM's word choice a release
    #: gate.
    message = "Hello, can you hear me?"

    async def run(self, helper, platform: Platform) -> ScenarioResult:
        """`helper` is a `DesktopAppTestRunner` (__main__.py:91).

        Named "Desktop" for historical reasons only — it speaks to the shared
        TestAutomationServer over HTTP, so it drives Android and iOS through
        their forwards without knowing it.
        """
        ok = await helper.test_chat_flow(message=self.message)
        status = ScenarioResult.PASS if ok else ScenarioResult.FAIL
        detail = "" if ok else "no reply rendered within the response deadline"
        return ScenarioResult(status, self.name, detail)


REGISTRY.register(InteractScenario())


# ---------------------------------------------------------------------------
# Room reserved, deliberately empty.
#
# `p2p_chat` and `video` land here as their own Scenario classes when the client
# surfaces them. They will need nothing from this module beyond `register(...)`,
# and nothing from `platforms.py` beyond `capture(CaptureKind.VIDEO, ...)` —
# which is why `capture` takes a kind today rather than being named
# `screenshot()`.
# ---------------------------------------------------------------------------


def run_names() -> List[str]:
    return REGISTRY.names()


__all__ = ["Scenario", "ScenarioResult", "REGISTRY", "InteractScenario", "run_names"]
