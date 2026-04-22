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
        print("  pip install --force-reinstall ciris-agent", file=sys.stderr)
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
