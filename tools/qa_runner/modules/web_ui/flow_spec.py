"""Run a declarative UI flow against the client's test-automation surface.

WHY THIS EXISTS. Every UI flow in this harness has been hand-written imperative
Python against the client's HTTP endpoints, and the failures have not been in the
app — they have been in our encoding of it. The canonical case (CIRISClient#39) is
`btn_menu` clicked to reach `menu_logout`: `btn_menu` opens ADVANCED, `menu_logout`
lives under GOVERNANCE. The click succeeded, because clicks always do, and the run
then waited out its timeout on an element that was never going to render. Nothing
was broken. We had encoded an assumption about composition that only the client
knows, and there was no place to state it where anything could check it.

THE LANGUAGE IS NOT OURS TO INVENT. CIRISClient answered #39 with a canonical
form, and it is deliberately a NARROWING of the `interactive_config` language this
repo already has in 83 steps across 22 adapters, not a second one beside it. This
module implements that form for the test direction:

    step_id / title       what the card is and what it is called
    requires:             LINKS — what must be true to reach it (the #39 fix)
    do:                   the interactions themselves
    expect:               what must be true after

`requires` is the half that matters. It is the place where "`menu_logout` requires
the GOVERNANCE menu open" is written down as data, checked BEFORE the step runs,
and reported as a precondition failure rather than as a mystery timeout twenty
seconds later.

WHY A STEP DECLARES BOTH SIDES. A flow that only asserts the end state cannot say
which step broke it. Asserting before and after each step turns "the flow failed"
into "step 3 of 7 failed, its preconditions held, its click succeeded, and the
screen did not change" — which is a bug report rather than a symptom.

STRICT BY CONSTRUCTION. Unknown keys are a load error, not a warning. A spec with
a typo'd key would otherwise assert nothing and pass, which is the vacuous-green
shape this harness has now produced three times (CIRISAgent#1151's absent-screen
check, `without_ai_recorded`, the lsof teardown). A spec that does not parse is
loud; a spec that parses asserts everything it says.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

#: Keys a step may carry. Anything else is a load error — see STRICT above.
_STEP_KEYS = {"step_id", "title", "description", "requires", "do", "expect", "optional_step"}
_COND_KEYS = {"screen", "visible", "absent", "text"}
_ACTION_KEYS = {"click", "input", "scroll_to", "wait", "wait_ms"}
_FLOW_KEYS = {"flow", "title", "description", "client", "steps"}


class SpecError(Exception):
    """The spec itself is wrong. Raised at load time, before anything is driven."""


@dataclass
class Condition:
    """A `requires` or `expect` block: what must be true at a point in the flow."""

    screen: Optional[str] = None
    visible: List[str] = field(default_factory=list)
    absent: List[str] = field(default_factory=list)
    text: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def parse(cls, raw: Any, where: str) -> "Condition":
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise SpecError(f"{where}: expected a mapping, got {type(raw).__name__}")
        unknown = set(raw) - _COND_KEYS
        if unknown:
            raise SpecError(f"{where}: unknown key(s) {sorted(unknown)}; allowed: {sorted(_COND_KEYS)}")
        return cls(
            screen=raw.get("screen"),
            visible=list(raw.get("visible") or []),
            absent=list(raw.get("absent") or []),
            text=dict(raw.get("text") or {}),
        )

    def is_empty(self) -> bool:
        return not (self.screen or self.visible or self.absent or self.text)

    def describe(self) -> str:
        bits = []
        if self.screen:
            bits.append(f"screen={self.screen}")
        if self.visible:
            bits.append(f"visible={self.visible}")
        if self.absent:
            bits.append(f"absent={self.absent}")
        if self.text:
            bits.append(f"text={self.text}")
        return ", ".join(bits) or "(nothing)"


@dataclass
class Action:
    """One interaction. Exactly one of click/input/scroll_to/wait per entry."""

    kind: str
    target: str
    value: Optional[str] = None
    wait_ms: int = 500

    @classmethod
    def parse(cls, raw: Any, where: str) -> "Action":
        if not isinstance(raw, dict):
            raise SpecError(f"{where}: expected a mapping, got {type(raw).__name__}")
        unknown = set(raw) - _ACTION_KEYS
        if unknown:
            raise SpecError(f"{where}: unknown key(s) {sorted(unknown)}; allowed: {sorted(_ACTION_KEYS)}")
        wait_ms = int(raw.get("wait_ms", 500))
        verbs = [k for k in ("click", "input", "scroll_to", "wait") if k in raw]
        if len(verbs) != 1:
            raise SpecError(
                f"{where}: exactly one of click/input/scroll_to/wait per action, got {verbs or 'none'}"
            )
        verb = verbs[0]
        if verb == "input":
            spec = raw["input"]
            if not isinstance(spec, dict) or len(spec) != 1:
                raise SpecError(f"{where}: `input` takes one {{tag: text}} pair")
            tag, text = next(iter(spec.items()))
            return cls("input", str(tag), str(text), wait_ms)
        return cls(verb, str(raw[verb]), None, wait_ms)

    def describe(self) -> str:
        if self.kind == "input":
            return f"input {self.target!r} = {self.value!r}"
        return f"{self.kind} {self.target!r}"


@dataclass
class Step:
    step_id: str
    title: str
    description: str = ""
    requires: Condition = field(default_factory=Condition)
    do: List[Action] = field(default_factory=list)
    expect: Condition = field(default_factory=Condition)
    #: A step that may legitimately not apply on this build. It still asserts
    #: everything it says WHEN its preconditions hold; it is skipped, loudly, when
    #: they do not. Never use this to paper over a step that ought to work.
    optional_step: bool = False

    @classmethod
    def parse(cls, raw: Any, index: int) -> "Step":
        where = f"step[{index}]"
        if not isinstance(raw, dict):
            raise SpecError(f"{where}: expected a mapping, got {type(raw).__name__}")
        unknown = set(raw) - _STEP_KEYS
        if unknown:
            raise SpecError(f"{where}: unknown key(s) {sorted(unknown)}; allowed: {sorted(_STEP_KEYS)}")
        for required_key in ("step_id", "title"):
            if not raw.get(required_key):
                raise SpecError(f"{where}: `{required_key}` is required")
        where = f"step {raw['step_id']!r}"
        step = cls(
            step_id=str(raw["step_id"]),
            title=str(raw["title"]),
            description=str(raw.get("description") or ""),
            requires=Condition.parse(raw.get("requires"), f"{where}.requires"),
            do=[Action.parse(a, f"{where}.do[{i}]") for i, a in enumerate(raw.get("do") or [])],
            expect=Condition.parse(raw.get("expect"), f"{where}.expect"),
            optional_step=bool(raw.get("optional_step", False)),
        )
        # A step that neither acts nor asserts is a comment pretending to be a test.
        if not step.do and step.expect.is_empty():
            raise SpecError(f"{where}: has no `do` and no `expect` — it would assert nothing")
        return step


@dataclass
class FlowSpec:
    flow: str
    title: str
    steps: List[Step]
    description: str = ""
    client_floor: Optional[str] = None
    path: Optional[Path] = None

    @classmethod
    def load(cls, path: Path) -> "FlowSpec":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise SpecError(f"{path}: not valid YAML: {exc}") from exc
        if not isinstance(raw, dict):
            raise SpecError(f"{path}: expected a mapping at the top level")
        unknown = set(raw) - _FLOW_KEYS
        if unknown:
            raise SpecError(f"{path}: unknown key(s) {sorted(unknown)}; allowed: {sorted(_FLOW_KEYS)}")
        if not raw.get("flow"):
            raise SpecError(f"{path}: `flow` (the flow's id) is required")
        steps_raw = raw.get("steps") or []
        if not steps_raw:
            raise SpecError(f"{path}: a flow with no steps asserts nothing")
        steps = [Step.parse(s, i) for i, s in enumerate(steps_raw)]
        seen: Dict[str, int] = {}
        for i, s in enumerate(steps):
            if s.step_id in seen:
                raise SpecError(f"{path}: duplicate step_id {s.step_id!r} (steps {seen[s.step_id]} and {i})")
            seen[s.step_id] = i
        return cls(
            flow=str(raw["flow"]),
            title=str(raw.get("title") or raw["flow"]),
            description=str(raw.get("description") or ""),
            client_floor=raw.get("client"),
            steps=steps,
            path=path,
        )


def check_client_floor(floor: Optional[str], actual: Optional[str]) -> Optional[str]:
    """Return a refusal message if `actual` is below `floor`, else None.

    VERSION-LEGIBLE, NOT VERSION-PINNED (CIRISClient#39). A flow states the client
    it was written against. Running it on an older one is refused LOUDLY, because a
    tag that does not exist yet fails as "element not found" — indistinguishable
    from a broken app. A PEP 440 local segment (`0.5.208+preview.gNNNNNNN`) is a
    build of that release, so it satisfies the release's floor.
    """
    if not floor:
        return None
    m = re.match(r"^>=\s*([0-9]+(?:\.[0-9]+)*)$", str(floor).strip())
    if not m:
        return f"`client: {floor!r}` is not understood; use e.g. \">=0.5.208\""
    if not actual:
        return None  # cannot tell; do not invent a refusal
    want = [int(x) for x in m.group(1).split(".")]
    have = [int(x) for x in actual.split("+", 1)[0].split(".") if x.isdigit()]
    if have < want:
        return (
            f"this flow is written against ciris-client {floor}, but {actual} is installed — "
            "tags it drives may not exist yet, which would fail as 'element not found'"
        )
    return None


@dataclass
class StepResult:
    step_id: str
    title: str
    status: str  # "pass" | "fail" | "skipped"
    phase: str = ""  # which half failed: "requires" | "do" | "expect"
    detail: str = ""
    duration_ms: int = 0
    screenshot: Optional[str] = None
    drivable: List[str] = field(default_factory=list)


class FlowRunner:
    """Executes a FlowSpec against a connected DesktopAppHelper."""

    def __init__(self, helper, platform=None, artifacts: Optional[Path] = None) -> None:
        self.helper = helper
        self.platform = platform
        self.artifacts = Path(artifacts) if artifacts else None
        self.results: List[StepResult] = []

    async def _drivable(self) -> List[str]:
        """Tags actually ON SCREEN. The failure message's most useful sentence.

        Uses the element's `visible` flag, not its presence: /tree lists everything
        ever composed (registry-never-forgets), so a presence list would name
        elements the user cannot see and send the reader hunting the wrong bug.
        """
        try:
            elements = await self.helper.get_elements()
        except Exception:  # noqa: BLE001 -- diagnosis must never raise
            return []
        out = []
        for e in elements:
            on_screen = e.visible if e.visible is not None else (e.width > 0 and e.height > 0)
            if on_screen:
                out.append(e.test_tag)
        return sorted(out)

    async def _check(self, cond: Condition, label: str) -> Optional[str]:
        """None if the condition holds, else the FIRST failure, named precisely."""
        if cond.screen:
            actual = await self.helper.get_screen()
            if actual != cond.screen:
                return f"{label}: expected screen {cond.screen!r}, on {actual!r}"
        for tag in cond.visible:
            if not await self.helper.is_element_visible(tag):
                return f"{label}: {tag!r} is not on screen"
        for tag in cond.absent:
            if await self.helper.is_element_visible(tag):
                return f"{label}: {tag!r} is on screen but should not be"
        for tag, want in cond.text.items():
            elem = await self.helper.get_element(tag)
            if elem is None:
                return f"{label}: {tag!r} not found, so its text cannot be checked"
            if want not in (elem.text or ""):
                return f"{label}: {tag!r} text {elem.text!r} does not contain {want!r}"
        return None

    async def _do(self, action: Action) -> Optional[str]:
        try:
            if action.kind == "click":
                ok = await self.helper.click(action.target, timeout=action.wait_ms * 4)
                return None if ok else f"click {action.target!r} did not succeed"
            if action.kind == "input":
                ok = await self.helper.input_text(action.target, action.value or "")
                return None if ok else f"input into {action.target!r} did not succeed"
            if action.kind == "scroll_to":
                ok = await self.helper.scroll_into_view(action.target)
                return None if ok else f"could not bring {action.target!r} on screen"
            if action.kind == "wait":
                ok = await self.helper.wait_for_element(action.target, timeout=action.wait_ms * 4)
                return None if ok else f"{action.target!r} never appeared"
        except Exception as exc:  # noqa: BLE001 -- an action's failure is a result, not a crash
            return f"{action.describe()} raised {type(exc).__name__}: {exc}"
        return f"unknown action kind {action.kind!r}"

    def _shot(self, spec: FlowSpec, step: Step) -> Optional[str]:
        if not (self.platform and self.artifacts):
            return None
        dest = self.artifacts / "shots" / f"flow-{spec.flow}-{step.step_id}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            got = self.platform.capture("screenshot", dest)
        except Exception:  # noqa: BLE001
            return None
        return str(got) if got else None

    async def run(self, spec: FlowSpec) -> bool:
        print(f"\n FLOW {spec.flow} — {spec.title}")
        if spec.description:
            print(f"   {spec.description}")
        print(f"   {len(spec.steps)} steps, from {spec.path}")

        for step in spec.steps:
            started = time.monotonic()
            print(f"\n  [{step.step_id}] {step.title}")

            # BEFORE. A precondition failure is reported as one -- the difference
            # between "this flow cannot start here" and "this element is broken".
            pre = await self._check(step.requires, "requires")
            if pre:
                drivable = await self._drivable()
                if step.optional_step:
                    print(f"     SKIP (optional): {pre}")
                    self.results.append(
                        StepResult(step.step_id, step.title, "skipped", "requires", pre, drivable=drivable)
                    )
                    continue
                print(f"     [FAIL] {pre}")
                print(f"            on screen and drivable now: {drivable}")
                self.results.append(
                    StepResult(
                        step.step_id, step.title, "fail", "requires", pre,
                        int((time.monotonic() - started) * 1000),
                        self._shot(spec, step), drivable,
                    )
                )
                return False
            if not step.requires.is_empty():
                print(f"     requires ok: {step.requires.describe()}")

            for action in step.do:
                err = await self._do(action)
                if err:
                    drivable = await self._drivable()
                    print(f"     [FAIL] {err}")
                    print(f"            on screen and drivable now: {drivable}")
                    self.results.append(
                        StepResult(
                            step.step_id, step.title, "fail", "do", err,
                            int((time.monotonic() - started) * 1000),
                            self._shot(spec, step), drivable,
                        )
                    )
                    return False
                print(f"     did: {action.describe()}")

            post = await self._check(step.expect, "expect")
            drivable = await self._drivable()
            shot = self._shot(spec, step)
            if post:
                print(f"     [FAIL] {post}")
                print(f"            on screen and drivable now: {drivable}")
                self.results.append(
                    StepResult(
                        step.step_id, step.title, "fail", "expect", post,
                        int((time.monotonic() - started) * 1000), shot, drivable,
                    )
                )
                return False
            ms = int((time.monotonic() - started) * 1000)
            print(f"     [OK] {step.expect.describe()} ({ms}ms)")
            self.results.append(
                StepResult(step.step_id, step.title, "pass", "", "", ms, shot, drivable)
            )
        return True

    def write_report(self, spec: FlowSpec) -> Optional[Path]:
        """The machine-readable half. The console half is printed as it goes."""
        if not self.artifacts:
            return None
        dest = self.artifacts / "flows" / f"{spec.flow}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "flow": spec.flow,
            "title": spec.title,
            "spec": str(spec.path),
            "client_floor": spec.client_floor,
            "passed": all(r.status != "fail" for r in self.results),
            "steps": [
                {
                    "step_id": r.step_id, "title": r.title, "status": r.status,
                    "phase": r.phase, "detail": r.detail, "duration_ms": r.duration_ms,
                    "screenshot": r.screenshot, "drivable": r.drivable,
                }
                for r in self.results
            ],
        }
        dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return dest

    def summary(self, spec: FlowSpec) -> str:
        p = sum(1 for r in self.results if r.status == "pass")
        s = sum(1 for r in self.results if r.status == "skipped")
        f = sum(1 for r in self.results if r.status == "fail")
        tail = f", {s} skipped" if s else ""
        return f"{spec.flow}: {p}/{len(spec.steps)} passed{tail}" + (f", {f} FAILED" if f else "")


def discover(paths: Sequence[str]) -> List[Path]:
    """Spec files from an explicit list, or every .yaml under a directory."""
    out: List[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            out.extend(sorted(p.glob("*.yaml")) + sorted(p.glob("*.yml")))
        elif p.exists():
            out.append(p)
        else:
            raise SpecError(f"no such spec or directory: {p}")
    return out
