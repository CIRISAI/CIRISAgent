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
import textwrap
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


def test_the_SIMULATOR_stdlib_source_probes_both_layouts() -> None:
    """Guard the branch that actually runs for a Debug simulator build.

    The script has two stdlib-embedding paths. The first is inside
    `if [ "$CONFIGURATION" = Release ] || [ "$PLATFORM_NAME" = iphoneos ]`,
    which a Debug simulator build never enters; the second, keyed on
    SIM_LIB_DYNLOAD, is the one CI executes. An earlier fix went into the
    first, so CI kept embedding nothing and the test written alongside it
    passed while the product stayed broken -- a mutation putting the
    simulator path back to lib/ did not fail it.

    So assert on SIM_LIB_DYNLOAD specifically: it must be a probe over the
    per-arch directories b14 uses, not a hardcoded lib/.
    """
    src = EMBED.read_text(encoding="utf-8")
    assert "SIM_LIB_DYNLOAD" in src, "no simulator stdlib source at all"
    body = src[src.index("SIM_SLICE="):src.index("stdlib_n=0")]
    assert 'for _libdir in' in body, "the simulator source is not probed"
    for d in ("lib-${SIM_HOST_ARCH}", "lib-arm64", "lib-x86_64"):
        assert d in body, f"{d} not probed -- b14 keeps the simulator stdlib there"
    assert 'ios-arm64_x86_64-simulator/lib/python3.10/lib-dynload"' not in src, (
        "the simulator stdlib source is hardcoded to lib/, which b14 leaves empty"
    )


def test_the_device_branch_probes_layouts_too() -> None:
    """Same two-layout problem, on the path a device build takes."""
    src = EMBED.read_text(encoding="utf-8")
    assert 'for libdir in "lib-${HOST_ARCH}" "lib-arm64" "lib"' in src


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
    assert "pids_listening_on" in hs, "must go through platform_procs, not invoke lsof directly"
    # An INVOCATION, not the word: the docstring explains why lsof is not called
    # here, so a substring check would fail on its own rationale. Look for the
    # binary appearing as a string literal, which is the only way to run it.
    import ast as _ast

    tree = _ast.parse(textwrap.dedent(hs))
    literals = [n.value for n in _ast.walk(tree) if isinstance(n, _ast.Constant) and isinstance(n.value, str)]
    assert not [x for x in literals if x.strip().lower() in ("lsof", "netstat")], (
        "POSIX-only binary invoked directly; platform_procs owns that decision"
    )
