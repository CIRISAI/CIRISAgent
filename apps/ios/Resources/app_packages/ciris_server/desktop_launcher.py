"""CIRIS Desktop launcher (ciris-server wheel).

Locates the per-platform CIRIS Desktop JAR that the wheel bundles under
``ciris-client``'s desktop uber-jar and runs it with the *system* Java
(Java 17+; no JRE is bundled, to keep each platform wheel under PyPI's 100MB
cap — same decision as CIRISAgent's setup.py).

Ported from ``ciris_engine/desktop_launcher.py`` in CIRISAgent, minus the
fat-wheel bundled-JRE path (this wheel never ships a JRE). The desktop app
connects to the node's read API, which is the node's Reticulum listen port + 1
(default 4242 → 4243); see ``ServerConfig::read_api_addr`` in src/config.rs.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

# Default read-API URL the desktop UI talks to: node listen port (4242) + 1.
DEFAULT_SERVER_URL = "http://localhost:4243"


def _java_exe_name() -> str:
    return "java.exe" if sys.platform == "win32" else "java"


def find_java() -> Optional[str]:
    """Find the system Java executable (JAVA_HOME, then PATH).

    The pip-installed wheel relies on a system Java 17+. The Windows installer,
    however, ships a trimmed JRE next to the frozen executable (``<app>/runtime``)
    so it "just works" with no prerequisite — prefer that when present.
    """
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / "runtime" / "bin" / _java_exe_name()
        if bundled.exists():
            return str(bundled)

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
    """Find the desktop JAR, from the ``ciris-client`` package.

    **It used to be bundled INTO this wheel** — gradle built it from the
    vendored ``client/`` tree and CI copied it to
    ``ciris_server/desktop_app/CIRIS-*.jar``. CIRISServer#471 deleted that tree,
    and the jar comes from ``ciris-client[node]`` now.

    That is not only a source change: the embedded jar was ~46 MiB of every one
    of the nine published wheels, against PyPI's 100 MiB per-file ceiling that
    the largest was within 3.4 MiB of (CIRISServer#486). Nine copies of one
    artifact, in a project that also has a 10 GB total quota. It is one
    dependency now.

    The legacy in-wheel location is still checked FIRST, and deliberately: a
    0.5.188-or-earlier wheel already installed somewhere still carries its jar,
    and an upgrade that made the desktop command stop working would be a worse
    failure than a redundant stat.
    """
    package_dir = Path(__file__).parent

    # Legacy: bundled in the wheel (<= 0.5.188).
    jar_dir = package_dir / "desktop_app"
    if jar_dir.exists():
        jars = sorted(jar_dir.glob("CIRIS-*.jar"))
        if jars:
            return jars[0]

    # The package that owns it.
    try:
        import ciris_client

        jar = Path(ciris_client.artifact_path("desktop-uber-jar"))
        if jar.exists():
            return jar
    except ImportError:
        # `ciris-client` is an UNCONDITIONAL dependency, so a failed import is a
        # broken install rather than an optional feature being absent.
        return None
    except Exception as exc:  # noqa: BLE001 - see the two states below
        # THE JAR-FREE WHEEL IS A SUPPORTED CONFIGURATION, NOT A FAULT.
        #
        # CIRISClient splits its artifact by wheel tag: the platform wheels
        # (`macosx_*`, `manylinux_*`, `win_amd64`) carry the uber-jar, and
        # `py3-none-any` is pure Python with no jar. A more specific tag beats
        # `any`, so a desktop pip takes the platform wheel and Android/iOS — which
        # match no platform tag — take the universal one. No environment marker is
        # involved: the installing pip evaluates tags against its OWN target, so
        # nothing depends on what the build host looked like.
        #
        # That means `ciris_client` imports fine here and `artifact_path` raises,
        # on exactly the platforms where a desktop jar could never have run. It is
        # the designed outcome, and it must not read as the same thing as a real
        # resolution failure — "there is deliberately no jar on this platform" and
        # "we could not find out" are different facts, and the launcher's advice
        # to the operator differs for each (CIRISServer#493).
        _record_jar_absence(exc)
        return None

    return None


#: Why the last :func:`find_desktop_jar` came back empty — read by the launcher
#: so its advice matches the cause. `None` means it was never asked.
_JAR_ABSENCE: Optional[str] = None


def _record_jar_absence(exc: BaseException) -> None:
    """Classify why the client package yielded no jar."""
    global _JAR_ABSENCE
    name = type(exc).__name__
    # `ciris_client` publishes `ArtifactUnavailable` for "this build does not
    # carry that artifact" and `ArtifactError` for a resolution fault. Matched by
    # NAME rather than imported, so this file keeps working against a client that
    # renames or reorganises them — the classification degrades to "unknown",
    # which is honest, instead of an ImportError at module scope.
    if name == "ArtifactUnavailable":
        _JAR_ABSENCE = "no-jar-in-this-wheel"
    elif name == "ArtifactError":
        _JAR_ABSENCE = f"artifact-resolution-failed: {exc}"
    else:
        _JAR_ABSENCE = f"unexpected: {name}: {exc}"


def jar_absence_reason() -> Optional[str]:
    """Why the jar is missing, or `None` if the question was never asked."""
    return _JAR_ABSENCE


def _check_java_version(java_path: str) -> Tuple[bool, str]:
    """Return (is_java_17_plus, version_line)."""
    try:
        result = subprocess.run(
            [java_path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stderr or result.stdout
        for line in output.split("\n"):
            if "version" in line.lower():
                import re

                match = re.search(r'"(\d+)', line)
                if match:
                    return (int(match.group(1)) >= 17, line.strip())
        return (False, output.split("\n")[0] if output else "unknown")
    except Exception:
        return (False, "unknown")


def _print_java_install_instructions() -> None:
    """Print platform-specific Java 17+ install instructions."""
    print("\n" + "=" * 70, file=sys.stderr)
    print("  JAVA 17+ REQUIRED FOR CIRIS DESKTOP", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print("\nCIRIS Desktop requires Java 17 or later to run.", file=sys.stderr)
    print("Please install Java using one of the methods below:\n", file=sys.stderr)

    if sys.platform == "darwin":
        print("macOS:", file=sys.stderr)
        print("  brew install openjdk@17", file=sys.stderr)
        print("  # or download from https://adoptium.net/temurin/releases/", file=sys.stderr)
    elif sys.platform == "win32":
        print("Windows:", file=sys.stderr)
        print("  winget install EclipseAdoptium.Temurin.17.JRE", file=sys.stderr)
        print("  # or download from https://adoptium.net/temurin/releases/", file=sys.stderr)
    else:
        print("Ubuntu/Debian:", file=sys.stderr)
        print("  sudo apt update && sudo apt install openjdk-17-jre", file=sys.stderr)
        print("\nFedora/RHEL/CentOS:", file=sys.stderr)
        print("  sudo dnf install java-17-openjdk", file=sys.stderr)
        print("\nArch Linux:", file=sys.stderr)
        print("  sudo pacman -S jre17-openjdk", file=sys.stderr)
        print("  # or download from https://adoptium.net/temurin/releases/", file=sys.stderr)

    print("\n" + "-" * 70, file=sys.stderr)
    print("After installation, verify with: java -version", file=sys.stderr)
    print("Then retry: ciris-server", file=sys.stderr)
    print("=" * 70 + "\n", file=sys.stderr)


def launch_desktop_app(server_url: str = DEFAULT_SERVER_URL) -> int:
    """Launch the CIRIS Desktop app, pointed at ``server_url``.

    Returns the desktop app's exit code (1 on any precondition failure).
    """
    jar_path = find_desktop_jar()
    if not jar_path:
        reason = jar_absence_reason()
        if reason == "no-jar-in-this-wheel":
            # Expected on Android / iOS / any tag with no platform wheel. Telling
            # this operator to "reinstall the platform-specific wheel" would send
            # them after a wheel that does not exist for their platform.
            print("The desktop app is not available on this platform.", file=sys.stderr)
            print(
                "\nThe installed `ciris-client` is the pure-Python build, which "
                "carries no\ndesktop JAR — that is deliberate: the desktop app is "
                "packaged only for\nmacOS, Linux and Windows.\n",
                file=sys.stderr,
            )
            print("Run the node headless instead:", file=sys.stderr)
            print("  ciris-server serve", file=sys.stderr)
            return 1
        print("ERROR: Desktop app JAR not found.", file=sys.stderr)
        if reason:
            print(f"\nReason: {reason}", file=sys.stderr)
        print("\nThe desktop JAR was not included in this installation.", file=sys.stderr)
        print("This happens if you installed a wheel built without the JAR", file=sys.stderr)
        print("(e.g. a headless server build).\n", file=sys.stderr)
        print("To fix, reinstall the platform-specific wheel:", file=sys.stderr)
        print("  pip install --force-reinstall ciris-server", file=sys.stderr)
        print("\nOr run the node headless:", file=sys.stderr)
        print("  ciris-server serve", file=sys.stderr)
        return 1

    java = find_java()
    if not java:
        print("ERROR: Java not found!", file=sys.stderr)
        _print_java_install_instructions()
        return 1

    is_valid, version_info = _check_java_version(java)
    if not is_valid:
        print(f"ERROR: Java 17+ required, but found: {version_info}", file=sys.stderr)
        _print_java_install_instructions()
        return 1

    print(f"Launching CIRIS Desktop from: {jar_path}")

    env = os.environ.copy()
    env["CIRIS_API_URL"] = server_url
    # Tell the UI where the node's home IS, rather than leaving it to infer.
    # The JVM's `user.home` comes from the passwd entry and ignores $HOME, so a
    # node started under an overridden HOME wrote its claim PIN somewhere the UI
    # would never look. We know the answer here; state it.
    from ciris_server.cli import _default_user_home

    env.setdefault("CIRIS_HOME", _default_user_home())

    try:
        result = subprocess.run([java, "-jar", str(jar_path)], env=env)
        return result.returncode
    except KeyboardInterrupt:
        print("\nShutting down...")
        return 0
    except Exception as e:
        print(f"ERROR: Failed to launch desktop app: {e}", file=sys.stderr)
        return 1


def main() -> None:
    """CLI entry point for the ``ciris-desktop`` command (UI only)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Launch the CIRIS Desktop application (UI only; "
        "assumes a node is already serving the read API).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ciris-desktop                    # Launch desktop (connects to localhost:4243)
  ciris-desktop --server-url URL   # Connect to a specific node read API
""",
    )
    parser.add_argument(
        "--server-url",
        default=DEFAULT_SERVER_URL,
        help=f"URL of the CIRIS node read API (default: {DEFAULT_SERVER_URL})",
    )
    args = parser.parse_args()
    sys.exit(launch_desktop_app(server_url=args.server_url))


if __name__ == "__main__":
    main()
