"""
CIRIS Desktop App Launcher

Launches the bundled CIRIS Desktop application (Kotlin Compose Multiplatform GUI).
The desktop app JAR is bundled in the pip package during CI build.

The launcher:
1. Finds the bundled desktop JAR in the package
2. Launches it using Java
3. The desktop app connects to the running CIRIS API server
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from ciris_engine.logic.utils import win_console as _win_console

_win_console.setup()


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
            return jars[0]

    # Fallback: check for development build
    dev_jar = package_dir.parent / "client" / "desktopApp" / "build" / "compose" / "jars"
    if dev_jar.exists():
        jars = list(dev_jar.glob("CIRIS-*.jar"))
        if jars:
            return jars[0]

    return None


def launch_desktop_app(server_url: str = "http://localhost:8080") -> int:
    """
    Launch the CIRIS Desktop application.

    Args:
        server_url: URL of the running CIRIS API server

    Returns:
        Exit code from the desktop app
    """
    # Find Java
    java = find_java()
    if not java:
        print("ERROR: Java not found. Please install Java 17 or later.", file=sys.stderr)
        print("  - On Ubuntu/Debian: sudo apt install openjdk-17-jre", file=sys.stderr)
        print("  - On macOS: brew install openjdk@17", file=sys.stderr)
        print("  - On Windows: Download from https://adoptium.net/", file=sys.stderr)
        return 1

    # Find desktop JAR
    jar_path = find_desktop_jar()
    if not jar_path:
        print("ERROR: Desktop app JAR not found.", file=sys.stderr)
        print("The desktop app may not be installed. Try reinstalling:", file=sys.stderr)
        print("  pip install --force-reinstall ciris-agent", file=sys.stderr)
        return 1

    print(f"Launching CIRIS Desktop from: {jar_path}")

    # Set environment for desktop app
    env = os.environ.copy()
    env["CIRIS_API_URL"] = server_url

    # Launch desktop app
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
