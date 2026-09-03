"""iOS failures were undiagnosable for three reasons, all ours. Pin each.

Run 33706020778: the app was alive for its whole 120s budget and never answered
/health, and every channel that could have said why was broken on our side --
the os_log predicate matched Apple's mobileassetd instead of our binary, its
window missed the launch, the macOS teardown kill -9'd the simulator app for
holding a client socket on :8080, and buffered stdout stamped every bring-up
stage with the same flush-time second.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "five-platform-live-qa.yml"


def _oslog_probe_src() -> str:
    from tools.qa_runner.modules.web_ui import __main__ as m

    src = inspect.getsource(m._ios_diagnostics)
    m2 = re.search(r'"ios-oslog",(.*?)\],\s*\),', src, re.S)
    assert m2, "ios-oslog probe not found in _ios_diagnostics"
    return m2.group(1)


def test_the_oslog_predicate_names_our_executable_not_a_bundle_id_fragment() -> None:
    """launchd names the process by its binary (iosApp), not by ai.ciris.mobile.

    A predicate built from the last bundle-id segment, "mobile", matched
    mobileassetd and none of our NSLog lines.
    """
    src = _oslog_probe_src()
    assert 'process == "{process_name}"' in src, "predicate must match the executable name exactly"
    assert 'bundle_id.split(".")' not in src, "a bundle-id fragment is not a process name"


def test_the_default_process_name_is_the_xcode_product() -> None:
    from tools.qa_runner.modules.web_ui import __main__ as m

    default = inspect.signature(m._ios_diagnostics).parameters["process_name"].default
    pbx = (ROOT / "apps" / "ios" / "iosApp.xcodeproj" / "project.pbxproj").read_text(encoding="utf-8")
    assert f"productName = {default};" in pbx, f"{default!r} is not the iOS product name"


def test_the_oslog_window_covers_the_whole_bring_up_budget() -> None:
    """3m from the failure point missed the launch; the health wait alone is 120s."""
    src = _oslog_probe_src()
    m2 = re.search(r'"--last",\s*"(\d+)m"', src)
    assert m2, "os_log window must be expressed in minutes"
    assert int(m2.group(1)) * 60 >= 2 * 120, "window must exceed the 120s health budget with room for install+launch"


def test_the_teardown_only_kills_listeners() -> None:
    """lsof without -sTCP:LISTEN returns clients too; the simulator app is one."""
    y = WORKFLOW.read_text(encoding="utf-8")
    for line in y.splitlines():
        if "lsof -ti" in line and "tcp:$port" in line:
            assert "-sTCP:LISTEN" in line, f"port teardown would kill clients as well as listeners: {line.strip()}"
            return
    raise AssertionError("port-teardown lsof line not found")


def test_the_launcher_runs_unbuffered() -> None:
    y = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r'^\s+PYTHONUNBUFFERED:\s*"1"', y, re.M), "stage timestamps are flush-time without PYTHONUNBUFFERED"
