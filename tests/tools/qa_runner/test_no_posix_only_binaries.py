"""The QA runner must not shell out to binaries that only exist on POSIX.

THE BUG. The Windows runner cleared checkout, wheel build and desktop app build,
then died on the first cleanup call:

    subprocess.run(["pkill", "-9", "-f", "CIRIS-macos"], capture_output=True)
    FileNotFoundError: [WinError 2] The system cannot find the file specified

Two defects in one line. `pkill` does not exist on Windows -- and the pattern
names a **macOS** binary, so even where it ran it was hunting a process that
could not be there. `lsof` had the same problem in two more places.

This is the third Windows failure in a row from the same underlying cause: the
suite had only ever been maintained against whatever machine it happened to run
on. Each fix uncovered the next one a layer down, because nothing asserted the
general property -- only the specific crash was ever repaired.

So this file asserts the property. It is a SOURCE-LEVEL test, and that is the
point: the crash needs Windows to happen, but the mistake is visible on any
platform. It fails here, on Linux, at the moment someone types `pkill` -- which
is months before a Windows user finds out.

A NOTE ON THE SILENT VARIANT, which is worse than the crash. In
`identity_update_tests.py` the `pkill` calls sat inside `except Exception: pass`,
so on Windows they did not fail -- they quietly did nothing, and a test whose
entire job was "stop the server, restart it, check it came back" passed without
ever stopping a server. A crash tells you it is broken; this does not. Both
shapes are caught here, because both are just the binary named in the source.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
QA_RUNNER = REPO / "tools" / "qa_runner"

#: Binaries with no Windows equivalent under the same name. Reaching for any of
#: these from shared code means that path cannot run on a third of our targets.
POSIX_ONLY = {
    "pkill": "kill_processes_matching()",
    "pgrep": "kill_processes_matching() / psutil",
    "killall": "kill_processes_matching()",
    "lsof": "pids_listening_on()",
    "ps": "psutil, or docker ps via the docker CLI",
    "uname": "platform.system()",
    "which": "shutil.which()",
    "chmod": "os.chmod()",
    "ln": "os.symlink()",
    "df": "shutil.disk_usage()",
    "sed": "str.replace / re.sub",
    "grep": "re",
}

#: The one module allowed to name them: it is the shim, and it guards every call
#: behind a platform check plus a FileNotFoundError handler.
EXEMPT = {"platform_procs.py"}

#: Modules that are POSIX-only by nature -- they drive Xcode or the Android SDK
#: on a developer machine and are never reached from the Windows workflow.
EXEMPT_DIRS = {"ios", "macos"}


def _iter_sources():
    for path in QA_RUNNER.rglob("*.py"):
        if path.name in EXEMPT:
            continue
        if EXEMPT_DIRS & set(path.relative_to(QA_RUNNER).parts):
            continue
        yield path


def _argv0_literals(path: pathlib.Path) -> list[tuple[int, str]]:
    """First element of every list literal handed to a subprocess.* call.

    Parsed rather than grepped so that `docker ps` -- argv0 `docker`, perfectly
    portable -- does not trip the `ps` rule, and so a bare mention in a comment
    or a docstring is not a finding.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        # subprocess.run / .Popen / .check_output / .call
        if not (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == "subprocess"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
            head = first.elts[0]
            if isinstance(head, ast.Constant) and isinstance(head.value, str):
                found.append((node.lineno, head.value))
        elif isinstance(first, ast.Constant) and isinstance(first.value, str):
            # shell=True string form; take the first word
            word = first.value.strip().split()
            if word:
                found.append((node.lineno, word[0]))
    return found


def test_no_posix_only_binary_is_invoked() -> None:
    """The assertion that would have caught all three Windows failures."""
    failures = []
    for path in _iter_sources():
        for lineno, argv0 in _argv0_literals(path):
            base = pathlib.PurePosixPath(argv0).name
            if base in POSIX_ONLY:
                rel = path.relative_to(REPO)
                failures.append(f"{rel}:{lineno} invokes {base!r} -- use {POSIX_ONLY[base]}")

    assert not failures, (
        f"{len(failures)} POSIX-only binary invocation(s) in the QA runner. On Windows these "
        "raise FileNotFoundError [WinError 2], or -- worse, if wrapped in a bare except -- "
        "silently do nothing and let the test pass without doing its job.\n  "
        + "\n  ".join(failures)
    )


def test_the_desktop_pattern_is_not_hardcoded_to_one_platform() -> None:
    """`CIRIS-macos` was hardcoded on Windows AND on Linux, so it never matched."""
    failures = []
    for path in _iter_sources():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for literal in ('"CIRIS-macos"', "'CIRIS-macos'", '"CIRIS-linux"', "'CIRIS-linux'", '"CIRIS-windows"'):
                if literal in line:
                    failures.append(f"{path.relative_to(REPO)}:{i} hardcodes {literal}")
    assert not failures, (
        "the desktop binary name is platform-specific; use desktop_process_pattern() so the "
        "runner hunts the process that can actually exist on the host it is running on.\n  "
        + "\n  ".join(failures)
    )


@pytest.mark.parametrize("plat,expected", [("win32", "CIRIS-windows"), ("darwin", "CIRIS-macos"), ("linux", "CIRIS-linux")])
def test_desktop_pattern_resolves_per_platform(monkeypatch: pytest.MonkeyPatch, plat: str, expected: str) -> None:
    from tools.qa_runner import platform_procs

    monkeypatch.setattr(platform_procs.sys, "platform", plat, raising=False)
    monkeypatch.setattr(platform_procs, "IS_WINDOWS", plat == "win32", raising=False)
    assert platform_procs.desktop_process_pattern() == expected


def test_helpers_never_raise_when_the_tool_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cleanup and diagnosis must not be able to fail a run.

    A cleanup helper that raises converts "the last run left a process behind"
    into "the suite cannot start", which is strictly worse than the mess it was
    tidying -- and is precisely how the Windows run died.
    """
    from tools.qa_runner import platform_procs

    def boom(*a, **k):
        raise FileNotFoundError(2, "The system cannot find the file specified")

    monkeypatch.setattr(platform_procs.subprocess, "run", boom, raising=True)
    assert platform_procs.kill_processes_matching("anything") == 0
    assert platform_procs.pids_listening_on(8080) == []


#: Modules on the Windows desktop path. The mobile/ios suites drive an Android
#: emulator or Xcode from a developer machine and never run on the Windows
#: workflow, so their /tmp screenshot paths are out of scope here.
WINDOWS_REACHABLE = [
    "tools/qa_runner/modules/web_ui/__main__.py",
    "tools/qa_runner/modules/web_ui/server_manager.py",
    "tools/qa_runner/modules/web_ui/desktop_app_helper.py",
]


@pytest.mark.parametrize("rel", WINDOWS_REACHABLE)
def test_no_hardcoded_tmp_on_the_windows_path(rel: str) -> None:
    """`Path("/tmp") / x` is `\\tmp\\x` on Windows, and that directory does not exist.

    This killed Boot 1 the moment the readiness gate was fixed and the run got
    far enough to open a log file:

        FileNotFoundError: [Errno 2] No such file or directory: '\\tmp\\ciris_desktop_setup.log'

    tempfile.gettempdir() is correct everywhere and honours TMPDIR/TEMP/TMP.
    """
    path = REPO / rel
    if not path.exists():
        pytest.skip(f"{rel} not in this checkout")
    hits = [
        f"{rel}:{i}"
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if ('"/tmp' in line or "'/tmp" in line) and not line.lstrip().startswith("#")
    ]
    assert not hits, (
        f"hardcoded /tmp at {hits}; on Windows this resolves to \\tmp on the current "
        "drive and raises FileNotFoundError. Use platform_procs.temp_path()."
    )


def test_temp_path_lands_in_the_real_temp_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """It must follow the runner's configured scratch space, not assume one."""
    from tools.qa_runner import platform_procs

    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    import importlib
    import tempfile as _tf

    importlib.reload(_tf)
    result = platform_procs.temp_path("ciris_desktop_setup.log")
    assert result.name == "ciris_desktop_setup.log"
    assert result.parent.is_dir(), "temp_path pointed at a directory that does not exist"
    # The decisive property: writable, which \tmp on Windows was not.
    result.write_text("ok", encoding="utf-8")
    assert result.read_text(encoding="utf-8") == "ok"
    result.unlink()


def test_empty_pid_list_means_unknown_not_free() -> None:
    """Guard the contract, since misreading it would reintroduce a race.

    pids_listening_on() returns [] when it CANNOT TELL -- no lsof, no netstat,
    a timeout. Callers must not treat that as proof the port is free.
    """
    import inspect

    from tools.qa_runner import platform_procs

    doc = inspect.getdoc(platform_procs.pids_listening_on) or ""
    assert "could not tell" in doc.lower() or "cannot be determined" in doc.lower()
