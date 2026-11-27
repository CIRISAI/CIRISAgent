"""
CIRIS Desktop App Launcher

Launches the bundled CIRIS Desktop application (Kotlin Compose Multiplatform GUI).
The desktop app JAR is bundled in the pip package during CI build.

The launcher:
1. Finds the bundled desktop JAR in the package
2. Launches it using Java
3. The desktop app connects to the running CIRIS API server
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ciris_engine.logic.utils import win_console as _win_console

#: The running desktop app, so an upgrade can close it.
_desktop_proc: Optional["subprocess.Popen[bytes]"] = None

_win_console.setup()

logger = logging.getLogger(__name__)

#: The desktop client's UI thread rewrites this every 5 s (CIRISClient PLAN-0.5.244 §2.7):
#: one line, ``<epoch_ms> <pid>``, under ``$CIRIS_HOME/run`` (default ``~/ciris``).
UI_HEARTBEAT_NAME = "desktop_ui.heartbeat"
UI_STALE_SECS = 30.0
UI_POLL_SECS = 5.0


def _java_exe_name() -> str:
    return "java.exe" if sys.platform == "win32" else "java"


def _ensure_bundled_jre_executable(jre_root: Path) -> None:
    """Restore +x on bundled JRE binaries.

    PEP 427 wheels install ``package_data`` files with mode 0644, dropping the
    executable bit on the jlinked ``jre/bin/*`` tree that CI stages. Without
    this, the JVM binary cannot be exec'd on macOS/Linux after ``pip install``.
    Idempotent; no-op on Windows and on already-executable files.
    """
    if sys.platform == "win32":
        return
    bin_dir = jre_root / "bin"
    if not bin_dir.is_dir():
        return
    for entry in bin_dir.iterdir():
        if not entry.is_file():
            continue
        try:
            mode = entry.stat().st_mode
            if mode & 0o111:
                continue
            entry.chmod(mode | 0o755)
        except OSError:
            pass


def find_bundled_jre() -> Optional[str]:
    """Find the fat-wheel bundled JRE shipped under ciris_engine/desktop_app/jre/."""
    jre_root = Path(__file__).parent / "desktop_app" / "jre"
    bundled = jre_root / "bin" / _java_exe_name()
    if bundled.exists():
        _ensure_bundled_jre_executable(jre_root)
        return str(bundled)
    return None


def find_java() -> Optional[str]:
    """Find Java executable.

    Preference order:
      1. Bundled JRE shipped in the wheel (standalone install).
      2. JAVA_HOME.
      3. ``java`` on PATH.
    """
    bundled = find_bundled_jre()
    if bundled:
        return bundled

    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        java_path = Path(java_home) / "bin" / _java_exe_name()
        if java_path.exists():
            return str(java_path)

    java = shutil.which("java")
    if java:
        return java

    return None


def find_desktop_jar() -> Optional[Path]:
    """Find the bundled desktop JAR."""
    # Check in package directory
    package_dir = Path(__file__).parent

    # Look for the JAR in desktop_app directory
    jar_dir = package_dir / "desktop_app"
    if jar_dir.exists():
        jars = list(jar_dir.glob("CIRIS-*.jar"))
        if jars:
            return _newest_jar(jars)

    # Fallback: check for development build
    dev_jar = package_dir.parent / "client" / "desktopApp" / "build" / "compose" / "jars"
    if dev_jar.exists():
        jars = list(dev_jar.glob("CIRIS-*.jar"))
        if jars:
            return _newest_jar(jars)

    return None


def _jar_version(jar: Path) -> Tuple[int, ...]:
    found = re.findall(r"\d+(?:\.\d+)+", jar.stem)
    return tuple(int(part) for part in found[-1].split(".")) if found else ()


def _newest_jar(jars: List[Path]) -> Path:
    """The newest JAR by version. A repaired install has the old one on disk too,
    and the first one a directory listing gave back could be either."""
    return max(jars, key=lambda jar: (_jar_version(jar), jar.name))


def _run_from_private_copy(jar: Path) -> Path:
    """The JAR to run: a copy under CIRIS_HOME, or the installed one if that fails.

    A JVM holds its JAR open, and on Windows pip can't move an open file, so
    running the installed JAR makes `pip install -U` fail part way through.
    """
    from ciris_engine.logic.utils.path_resolution import get_ciris_home

    home = get_ciris_home()
    try:
        from ciris_server.upgrade import private_jar  # type: ignore[import-not-found, import-untyped, unused-ignore]

        return _with_class_path(jar, Path(private_jar(jar, home)))
    except ImportError:
        pass  # ciris-server < 0.5.245
    dest = home / "runtime" / "desktop" / jar.name
    try:
        _copy_if_changed(jar, dest)
        return _with_class_path(jar, dest)
    except OSError as e:
        print(f"Running the desktop app in place ({e})", file=sys.stderr)
        return jar


def _copy_if_changed(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        tmp = dest.with_suffix(f".{os.getpid()}.tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest)


def manifest_class_path(jar: Path) -> List[str]:
    """The relative entries of a JAR's manifest ``Class-Path`` (continuation lines joined)."""
    import zipfile

    try:
        with zipfile.ZipFile(jar) as zf:
            text = zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except (OSError, KeyError, zipfile.BadZipFile):
        return []
    joined = re.sub(r"\r?\n ", "", text.replace("\r\n", "\n"))
    for line in joined.split("\n"):
        if line.startswith("Class-Path:"):
            return [e for e in line[len("Class-Path:") :].split() if e and not re.match(r"^[a-z]+:", e)]
    return []


def _with_class_path(installed: Path, private: Path) -> Path:
    """Put the JAR's ``Class-Path`` files beside its private copy, at the same relative paths.

    The JVM resolves ``Class-Path`` against the JAR's own directory and ignores a
    missing entry without a word. ciris-client 0.5.243 reaches FFmpeg through
    ``../../ciris_holon/media/jars/*`` beside the installed JAR, so the private
    copy started with no video. Copies, not references: the copy exists so the
    running JVM holds no file in site-packages open (WinError 32).
    """
    if private == installed:
        return private
    from ciris_engine.logic.utils.path_resolution import get_ciris_home

    home = get_ciris_home().resolve()
    for entry in manifest_class_path(installed):
        source = (installed.parent / entry).resolve()
        if not source.is_file():
            continue
        target = private.parent / entry
        if not target.resolve().is_relative_to(home):
            continue  # never write outside CIRIS_HOME, whatever the manifest names
        try:
            _copy_if_changed(source, target)
            # The client's check_holon_classpath.py verifies each copied JAR against the
            # SHA256SUMS in its directory, so the list travels with the JARs. Compared by
            # content: an edited list can keep its size.
            sums = source.parent / "SHA256SUMS"
            sums_target = target.parent / "SHA256SUMS"
            if sums.is_file() and (not sums_target.is_file() or sums_target.read_bytes() != sums.read_bytes()):
                shutil.copyfile(sums, sums_target)
        except OSError as e:
            print(f"Could not copy {entry} beside the desktop app ({e}); calls may have no video", file=sys.stderr)
    return private


def stop_desktop_app() -> None:
    """Close the running desktop app, if there is one."""
    proc = _desktop_proc
    if proc is not None and proc.poll() is None:
        proc.terminate()


def _check_java_version(java_path: str) -> tuple[bool, str]:
    """Check if Java version is 17 or later.

    Returns:
        Tuple of (is_valid, version_string)
    """
    try:
        result = subprocess.run(
            [java_path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Java version is printed to stderr
        output = result.stderr or result.stdout
        # Parse version from output like: openjdk version "17.0.1" or java version "21"
        for line in output.split("\n"):
            if "version" in line.lower():
                # Extract version number
                import re

                match = re.search(r'"(\d+)', line)
                if match:
                    major_version = int(match.group(1))
                    return (major_version >= 17, line.strip())
        return (False, output.split("\n")[0] if output else "unknown")
    except Exception:
        return (False, "unknown")


def _print_java_install_instructions() -> None:
    """Print platform-specific Java installation instructions."""
    print("\n" + "=" * 70, file=sys.stderr)
    print("  JAVA 17+ REQUIRED FOR CIRIS DESKTOP", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print("\nCIRIS Desktop requires Java 17 or later to run.", file=sys.stderr)
    print("Please install Java using one of the methods below:\n", file=sys.stderr)

    if sys.platform == "darwin":
        print("macOS:", file=sys.stderr)
        print("  Option 1 (Homebrew - recommended):", file=sys.stderr)
        print("    brew install openjdk@17", file=sys.stderr)
        print("    sudo ln -sfn $(brew --prefix)/opt/openjdk@17/libexec/openjdk.jdk \\", file=sys.stderr)
        print("      /Library/Java/JavaVirtualMachines/openjdk-17.jdk", file=sys.stderr)
        print("\n  Option 2 (Download):", file=sys.stderr)
        print("    Download from https://adoptium.net/temurin/releases/", file=sys.stderr)
        print("    Choose: macOS, aarch64 (Apple Silicon) or x64 (Intel)", file=sys.stderr)
    elif sys.platform == "win32":
        print("Windows:", file=sys.stderr)
        print("  Option 1 (winget - recommended):", file=sys.stderr)
        print("    winget install EclipseAdoptium.Temurin.17.JRE", file=sys.stderr)
        print("\n  Option 2 (Chocolatey):", file=sys.stderr)
        print("    choco install temurin17jre", file=sys.stderr)
        print("\n  Option 3 (Download):", file=sys.stderr)
        print("    Download from https://adoptium.net/temurin/releases/", file=sys.stderr)
        print("    Choose: Windows, x64, JRE, .msi installer", file=sys.stderr)
    else:
        # Linux
        print("Ubuntu/Debian:", file=sys.stderr)
        print("  sudo apt update && sudo apt install openjdk-17-jre", file=sys.stderr)
        print("\nFedora/RHEL/CentOS:", file=sys.stderr)
        print("  sudo dnf install java-17-openjdk", file=sys.stderr)
        print("\nArch Linux:", file=sys.stderr)
        print("  sudo pacman -S jre17-openjdk", file=sys.stderr)
        print("\nOther Linux:", file=sys.stderr)
        print("  Download from https://adoptium.net/temurin/releases/", file=sys.stderr)
        print("  Choose: Linux, x64 or aarch64, JRE, .tar.gz", file=sys.stderr)

    print("\n" + "-" * 70, file=sys.stderr)
    print("After installation, verify with: java -version", file=sys.stderr)
    print("Then retry: ciris-agent", file=sys.stderr)
    print("=" * 70 + "\n", file=sys.stderr)


def desktop_app_env(server_url: str, base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The environment the desktop JAR is launched with. ONE definition.

    The client reads two names: CIRIS_API_URL (the brain) and CIRIS_NODE_URL
    (the node). Since ciris-client 0.5.213 it builds its ordinary API client
    from CIRIS_NODE_URL alone and ignores CIRIS_API_URL there -- a deliberate
    fix for the run-without-AI hand-off (CIRISClient#48/#52). This launcher
    set only CIRIS_API_URL, so every desktop started by `ciris-agent` had its
    UI pointed at the bare node on :4243, where only the node-native surface
    and fourteen proxied brain prefixes exist: "Add provider" (PUT
    /v1/setup/llm), list-models, /v1/system/llm, users, memory writes all
    404'd. The QA gate never saw it because its harness set BOTH names to the
    brain -- the intended configuration (routes/node_proxy.py makes :8080 the
    one complete surface) -- while the product did not.

    So: both names point at the brain, an operator's explicit CIRIS_NODE_URL
    is honoured verbatim, and the harness derives its own values from here.
    """
    env: Dict[str, str] = dict(os.environ) if base is None else dict(base)
    env["CIRIS_API_URL"] = server_url
    explicit = (env.get("CIRIS_NODE_URL") or "").strip()
    env["CIRIS_NODE_URL"] = explicit or server_url
    return env


def ui_heartbeat_path(env: Dict[str, str]) -> Path:
    """Where the client writes its heartbeat: the client's own home rule, from the env it runs with."""
    home = (env.get("CIRIS_HOME") or "").strip()
    return (Path(home) if home else Path.home() / "ciris") / "run" / UI_HEARTBEAT_NAME


def ui_heartbeat_age(path: Path, pid: int, now_s: float) -> Optional[float]:
    """Seconds since THIS window's UI thread last wrote, or None if there is nothing to judge.

    None for: no file (a client older than 0.5.244 writes none), an unreadable or
    malformed line, or a line from another process (a previous run's leftover).
    """
    try:
        parts = path.read_text(encoding="utf-8").split()
        epoch_ms, writer = int(parts[0]), int(parts[1])
    except (OSError, ValueError, IndexError):
        return None
    if writer != pid:
        return None
    return max(0.0, now_s - epoch_ms / 1000.0)


def watch_ui_heartbeat(
    proc: "subprocess.Popen[bytes]",
    path: Path,
    report: Callable[[str], None],
    stale_secs: float = UI_STALE_SECS,
    poll_secs: float = UI_POLL_SECS,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Report once when the window stops answering and once when it recovers.

    Reports only; it never ends the window. Caveat: an idle UI thread behind an
    invisible overlay still beats (the 2026-11-27 freeze), and the client's own
    input-swallow check covers that case.
    """
    stuck = False
    while proc.poll() is None:
        age = ui_heartbeat_age(path, proc.pid, clock())
        if age is not None and age > stale_secs and not stuck:
            stuck = True
            report(
                f"CIRIS Desktop (pid {proc.pid}) has not responded for {age:.0f} s. "
                "If the window stays frozen, close it and start CIRIS again."
            )
        elif age is not None and age <= stale_secs and stuck:
            stuck = False
            report(f"CIRIS Desktop (pid {proc.pid}) is responding again.")
        sleep(poll_secs)


def _report_ui(text: str) -> None:
    logger.warning("[DESKTOP-UI] %s", text)
    print(text, file=sys.stderr)


def launch_desktop_app(server_url: str = "http://localhost:8080") -> int:
    """
    Launch the CIRIS Desktop application.

    Args:
        server_url: URL of the running CIRIS API server

    Returns:
        Exit code from the desktop app
    """
    # Check for desktop JAR first — if missing, guide to headless mode
    # (avoids telling users to install Java when desktop isn't available)
    jar_path = find_desktop_jar()
    if not jar_path:
        print("ERROR: Desktop app JAR not found.", file=sys.stderr)
        print("\nThe desktop app JAR was not included in this installation.", file=sys.stderr)
        print("This can happen if you installed the headless wheel.\n", file=sys.stderr)
        print("To fix, try reinstalling with the platform-specific wheel:", file=sys.stderr)
        from ciris_engine.upgrade import console_python

        # This Python's pip, never whichever pip is first on PATH.
        print(f'  "{console_python()}" -m pip install --force-reinstall ciris-agent', file=sys.stderr)
        print("\nOr run in headless server mode:", file=sys.stderr)
        print("  ciris-agent --server", file=sys.stderr)
        return 1

    # Find Java (only needed if desktop JAR is present)
    java = find_java()
    if not java:
        print("ERROR: Java not found!", file=sys.stderr)
        _print_java_install_instructions()
        return 1

    # Check Java version (need 17+)
    is_valid, version_info = _check_java_version(java)
    if not is_valid:
        print(f"ERROR: Java 17+ required, but found: {version_info}", file=sys.stderr)
        _print_java_install_instructions()
        return 1

    jar_path = _run_from_private_copy(jar_path)
    print(f"Launching CIRIS Desktop from: {jar_path}")

    env = desktop_app_env(server_url)

    # Launch desktop app
    global _desktop_proc
    try:
        _desktop_proc = subprocess.Popen([java, "-jar", str(jar_path)], env=env)
        threading.Thread(
            target=watch_ui_heartbeat,
            args=(_desktop_proc, ui_heartbeat_path(env), _report_ui),
            name="desktop-ui-heartbeat",
            daemon=True,
        ).start()
        return _desktop_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        return 0
    except Exception as e:
        print(f"ERROR: Failed to launch desktop app: {e}", file=sys.stderr)
        return 1


def main() -> None:
    """CLI entry point for desktop launcher."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Launch CIRIS Desktop Application",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ciris-desktop                    # Launch desktop app (connects to localhost:8080)
  ciris-desktop --server-url URL   # Connect to specific server
""",
    )

    parser.add_argument(
        "--server-url", default="http://localhost:8080", help="URL of CIRIS API server (default: http://localhost:8080)"
    )

    args = parser.parse_args()

    exit_code = launch_desktop_app(server_url=args.server_url)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
