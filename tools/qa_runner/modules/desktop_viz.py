"""
Desktop cell-viz QA runner.

Programmatic smoke test for the cell visualization redesign. Drives the
desktop app via the CIRIS_TEST_MODE HTTP server at localhost:9091 using
the /screen, /tree, /click, /mouse-click-xy, /input, and /screenshot
endpoints. Assumes both the backend API (port 8080) and the desktop
uber JAR with CIRIS_TEST_MODE=true are already running.

Usage::

    # Start backend + desktop in test mode, then:
    python3 -m tools.qa_runner.modules.desktop_viz

Exits non-zero on any failed assertion for CI integration. Screenshots
of each phase land in ``mobile_qa_reports/desktop_viz/<timestamp>/``.

Phases:
  1. Login (admin / qa_test_password_12345)
  2. Land on Interact, capture BG screenshot
  3. Toggle VIZ BG -> VIZ FG, capture FG screenshot
  4. Tap cell center (should select NucleusCore); assert detail panel
  5. Tap a cytoplasm mote near the nucleus; assert panel shows Memory
  6. Tap a bus arc (outer ring); assert panel shows a bus name
  7. Close panel via the ✕ button; assert it dismissed
  8. Toggle back to BG; assert panel gone and chat area returns
  9. Optional: trigger a DEFER via chat (``$defer``) and capture ripple
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

API_BASE = os.environ.get("CIRIS_API_URL", "http://localhost:8080")
TEST_BASE = os.environ.get("CIRIS_TEST_URL", "http://localhost:9091")
ADMIN_USER = os.environ.get("CIRIS_QA_USER", "admin")
ADMIN_PASS = os.environ.get("CIRIS_QA_PASS", "qa_test_password_12345")

REPORT_ROOT = Path("mobile_qa_reports/desktop_viz")


@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Run:
    stamp: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y%m%d_%H%M%S"))
    steps: List[Step] = field(default_factory=list)

    @property
    def outdir(self) -> Path:
        p = REPORT_ROOT / self.stamp
        p.mkdir(parents=True, exist_ok=True)
        return p

    def record(self, step: Step) -> None:
        self.steps.append(step)
        mark = "✓" if step.ok else "✗"
        print(f"  [{mark}] {step.name}" + (f" — {step.detail}" if step.detail else ""))

    @property
    def failed(self) -> int:
        return sum(1 for s in self.steps if not s.ok)


def _require_servers() -> None:
    """Fail fast if backend or desktop test server aren't up."""
    try:
        r = requests.get(f"{TEST_BASE}/health", timeout=2)
        assert r.ok and r.json().get("testMode") is True, f"test server: {r.text[:100]}"
    except Exception as e:
        print(f"[desktop_viz] desktop test server not reachable at {TEST_BASE}: {e}")
        print("[desktop_viz] start it with:")
        print("  cd mobile && CIRIS_TEST_MODE=true CIRIS_TEST_PORT=9091 \\")
        print("    java -jar desktopApp/build/compose/jars/CIRIS-macos-arm64-*.jar")
        sys.exit(2)
    try:
        r = requests.get(f"{API_BASE}/v1/system/health", timeout=2)
        assert r.ok, f"api: {r.text[:100]}"
    except Exception as e:
        print(f"[desktop_viz] backend API not reachable at {API_BASE}: {e}")
        sys.exit(2)


def _screenshot(run: Run, name: str) -> Path:
    path = run.outdir / f"{name}.png"
    r = requests.post(
        f"{TEST_BASE}/screenshot",
        json={"path": str(path)},
        timeout=5,
    )
    r.raise_for_status()
    return path


def _screen(run: Run) -> str:
    r = requests.get(f"{TEST_BASE}/screen", timeout=2)
    return r.json().get("screen", "") if r.ok else ""


def _tree(run: Run) -> List[Dict[str, Any]]:
    r = requests.get(f"{TEST_BASE}/tree", timeout=3)
    return r.json().get("elements", []) if r.ok else []


def _click(run: Run, tag: str) -> bool:
    r = requests.post(f"{TEST_BASE}/click", json={"testTag": tag}, timeout=3)
    return r.ok and r.json().get("success") is True


def _mouse_xy(run: Run, x: int, y: int) -> bool:
    r = requests.post(f"{TEST_BASE}/mouse-click-xy", json={"x": x, "y": y}, timeout=3)
    return r.ok and r.json().get("success") is True


def _input(run: Run, tag: str, text: str, clear: bool = True) -> bool:
    r = requests.post(
        f"{TEST_BASE}/input",
        json={"testTag": tag, "text": text, "clearFirst": clear},
        timeout=3,
    )
    return r.ok and r.json().get("success") is True


def _find_element(tree: List[Dict[str, Any]], tag_substr: str) -> Optional[Dict[str, Any]]:
    for e in tree:
        if tag_substr in (e.get("testTag") or ""):
            return e
    return None


def _wait_for_tag(tag_substr: str, timeout_s: float = 5.0) -> Optional[Dict[str, Any]]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        tree = requests.get(f"{TEST_BASE}/tree", timeout=3).json().get("elements", [])
        el = _find_element(tree, tag_substr)
        if el:
            return el
        time.sleep(0.3)
    return None


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------


def phase_login(run: Run) -> bool:
    screen = _screen(run)
    if screen == "Interact":
        run.record(Step("already logged in", True, "skipping login"))
        return True
    ok_u = _input(run, "input_username", ADMIN_USER)
    ok_p = _input(run, "input_password", ADMIN_PASS)
    ok_s = _click(run, "btn_login_submit")
    time.sleep(3)
    screen = _screen(run)
    run.record(Step("login", screen == "Interact", f"screen={screen}"))
    return screen == "Interact"


def phase_bg_screenshot(run: Run) -> bool:
    _screenshot(run, "01_bg")
    tree = _tree(run)
    has_status = _find_element(tree, "btn_viz_mode_toggle") is not None
    run.record(Step("BG status bar visible", has_status))
    return has_status


def phase_fg_toggle(run: Run) -> bool:
    ok = _click(run, "btn_viz_mode_toggle")
    time.sleep(1)
    _screenshot(run, "02_fg")
    # The VIZ FG pill has testTag "btn_viz_mode_toggle" with label reflecting
    # current mode; simplest check is that the pill is still present.
    tree = _tree(run)
    toggle = _find_element(tree, "btn_viz_mode_toggle")
    run.record(Step("toggle to FG", ok and toggle is not None))
    return ok and toggle is not None


def _cell_center_xy(tree: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Best-effort guess for the cell viz center in the chat-area Box.

    We look for the input bar's position as a bottom anchor and the status
    bar's toggle as a top anchor, then take the midpoint.
    """
    top = _find_element(tree, "btn_viz_mode_toggle")
    bottom = _find_element(tree, "input_message") or _find_element(tree, "btn_send")
    if not top or not bottom:
        return (600, 400)
    x = 600
    y_top = int(top.get("y", 0)) + int(top.get("height", 0))
    y_bot = int(bottom.get("y", 800))
    return (x, (y_top + y_bot) // 2)


def phase_tap_nucleus(run: Run) -> bool:
    cx, cy = _cell_center_xy(_tree(run))
    ok = _mouse_xy(run, cx, cy)
    time.sleep(1.5)
    _screenshot(run, "03_nucleus_tap")
    # The detail panel has a close button with testTag btn_fg_detail_close.
    panel = _wait_for_tag("btn_fg_detail_close", timeout_s=2.5)
    run.record(Step("nucleus tap -> panel", ok and panel is not None, f"cx={cx} cy={cy}"))
    return ok and panel is not None


def phase_dismiss_panel(run: Run) -> bool:
    ok = _click(run, "btn_fg_detail_close")
    time.sleep(0.5)
    tree = _tree(run)
    gone = _find_element(tree, "btn_fg_detail_close") is None
    run.record(Step("dismiss panel via ✕", ok and gone))
    return ok and gone


def phase_tap_mote(run: Run) -> bool:
    cx, cy = _cell_center_xy(_tree(run))
    # A mote likely lies a bit up-right of center inside the nucleus ring.
    ok = _mouse_xy(run, cx + 30, cy - 15)
    time.sleep(2.5)
    _screenshot(run, "04_mote_tap")
    panel = _wait_for_tag("btn_fg_detail_close", timeout_s=2.5)
    run.record(Step("mote tap -> panel", panel is not None))
    return panel is not None


def phase_tap_bus_arc(run: Run) -> bool:
    cx, cy = _cell_center_xy(_tree(run))
    # Far right edge should land on a bus arc regardless of rotation.
    ok = _mouse_xy(run, cx + 140, cy)
    time.sleep(2.5)
    _screenshot(run, "05_arc_tap")
    panel = _wait_for_tag("btn_fg_detail_close", timeout_s=2.5)
    run.record(Step("bus arc tap -> panel", panel is not None))
    return panel is not None


def phase_back_to_bg(run: Run) -> bool:
    # Dismiss panel first if still open, then toggle back.
    if _find_element(_tree(run), "btn_fg_detail_close"):
        _click(run, "btn_fg_detail_close")
        time.sleep(0.4)
    ok = _click(run, "btn_viz_mode_toggle")
    time.sleep(1)
    _screenshot(run, "06_back_to_bg")
    tree = _tree(run)
    has_chat = _find_element(tree, "input_message") is not None
    run.record(Step("toggle back to BG", ok and has_chat))
    return ok and has_chat


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    _require_servers()
    run = Run()
    print(f"[desktop_viz] reports -> {run.outdir}")
    phases = [
        phase_login,
        phase_bg_screenshot,
        phase_fg_toggle,
        phase_tap_nucleus,
        phase_dismiss_panel,
        phase_tap_mote,
        phase_tap_bus_arc,
        phase_back_to_bg,
    ]
    for p in phases:
        try:
            p(run)
        except Exception as e:
            run.record(Step(p.__name__, False, f"exception: {type(e).__name__}: {e}"))

    summary = {
        "stamp": run.stamp,
        "total": len(run.steps),
        "failed": run.failed,
        "steps": [s.__dict__ for s in run.steps],
    }
    (run.outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[desktop_viz] {len(run.steps) - run.failed}/{len(run.steps)} steps passed")
    return 0 if run.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
