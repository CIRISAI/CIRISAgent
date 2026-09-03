"""Why the iOS simulator app never showed its UI on CI -- and the three ways we
could not see it. Run 33708152999 was the first with app-side evidence:

    ImportError: dlopen(.../iosApp.app/Frameworks/_struct.framework/_struct): no such file

`import struct` at the first line of kmp_main. The .fwork redirects in
lib-dynload point at frameworks the build phase is supposed to embed, and it
embedded none, because it read the DEVICE slice of Python.xcframework while
building for the simulator. The embedded backend never started; the Compose
view -- with the test server inside it -- was never shown.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EMBED = ROOT / "apps" / "ios" / "scripts" / "embed_native_frameworks.sh"
DEPLOY = ROOT / "apps" / "ios" / "scripts" / "rebuild_and_deploy.sh"


def test_the_embed_phase_picks_the_slice_that_matches_the_sdk() -> None:
    src = EMBED.read_text(encoding="utf-8")
    assert 'PYTHON_SLICE="ios-arm64_x86_64-simulator"' in src, "no simulator slice selection"
    assert re.search(r'PLATFORM_NAME"?\s*=\s*"iphonesimulator"', src), "slice is not chosen from PLATFORM_NAME"
    # The unconditional device path must be gone: it was the whole bug.
    assert 'Python.xcframework/ios-arm64"' not in src, "device slice is still hardcoded"
    assert 'Python.xcframework/${PYTHON_SLICE}"' in src


def test_the_build_log_is_kept_whole() -> None:
    """`-quiet | tail -5` hid the Run Script phase's own output, so the one line
    that says whether extensions were embedded was never visible anywhere."""
    src = DEPLOY.read_text(encoding="utf-8")
    builds = [ln for ln in src.splitlines() if "build 2>&1" in ln]
    assert builds, "xcodebuild invocations not found"
    for ln in builds:
        assert "tee" in ln, f"xcodebuild output is discarded: {ln.strip()}"
        assert "-quiet" not in ln, f"-quiet suppresses Run Script output: {ln.strip()}"
    assert "XCODEBUILD_LOG=" in src


def test_diagnostics_capture_the_interpreter_failure_and_what_was_embedded() -> None:
    from tools.qa_runner.modules.web_ui import __main__ as m

    src = inspect.getsource(m._ios_diagnostics)
    assert 'base.parent.glob("*.log")' in src, "Documents/python_error.log is not collected"
    assert '"app"]' in src and "Frameworks" in src, "the .app's Frameworks/ is not listed"
    assert "_struct.framework" in src, "the embed verdict is not printed inline"


def test_bring_up_refuses_a_port_the_host_already_owns() -> None:
    """The simulator shares the host loopback: a host backend on :8080 satisfies
    the app's own health check and every gate probe. That scored a desktop
    backend as an iOS one while the app's Python had died on first import."""
    from tools.qa_runner.modules.web_ui import __main__ as m

    src = inspect.getsource(m.run_ios_simulator_up)
    guard = src.find("_host_listener(")
    launch = src.find('"launch"')
    assert guard != -1, "no host-listener guard"
    assert launch != -1 and guard < launch, "the guard must run before the app is launched"
    hs = inspect.getsource(m._host_listener)
    assert "-sTCP:LISTEN" in hs, "clients on the port must not count as owners"
