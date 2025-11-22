"""First-run detection for CIRIS Agent.

Determines if this is a first-time run by checking for configuration files.
"""

import os
import platform
import subprocess
import sys
from pathlib import Path


def get_config_paths() -> list[Path]:
    """Get possible configuration file locations in priority order.

    Returns:
        List of paths to check for .env files, in priority order:
        1. Current directory .env (development/local override)
        2. ~/.ciris/.env (user-specific config)
        3. /etc/ciris/.env (system-wide config, Linux/Unix)
    """
    paths = []

    # 1. Current directory (highest priority)
    paths.append(Path.cwd() / ".env")

    # 2. User config directory
    user_ciris_dir = Path.home() / ".ciris"
    paths.append(user_ciris_dir / ".env")

    # 3. System config (Unix/Linux only)
    system_config = Path("/etc/ciris/.env")
    if system_config.parent.exists():  # Only add if /etc/ciris exists
        paths.append(system_config)

    return paths


def is_first_run() -> bool:
    """Check if this is the first run of CIRIS Agent.

    A first run is detected when:
    - No .env file exists in any of the standard config locations
    - No CIRIS_CONFIGURED environment variable is set
    - OR CIRIS_FORCE_FIRST_RUN is set (for testing)

    Returns:
        True if this appears to be a first run, False otherwise.
    """
    # FORCE first-run mode for testing (e.g., QA runner setup tests)
    if os.environ.get("CIRIS_FORCE_FIRST_RUN"):
        return True

    # Quick check: If CIRIS_CONFIGURED env var is set, not first run
    if os.environ.get("CIRIS_CONFIGURED"):
        return False

    # Check all possible config locations
    config_paths = get_config_paths()
    for path in config_paths:
        if path.exists() and path.is_file():
            # Found a config file - not first run
            return False

    return True


def check_macos_python() -> tuple[bool, str]:
    """Check if macOS has a valid Python installation.

    On macOS, /usr/bin/python3 is often a stub that requires Xcode Command Line Tools.
    This function verifies:
    1. If python3 is the system stub
    2. If Xcode Command Line Tools are installed
    3. If Python version is adequate (>= 3.10)

    IMPORTANT: Checks Xcode CLT BEFORE running python3 to avoid triggering
    the macOS installation dialog popup.

    Returns:
        Tuple of (is_valid, message)
    """
    if platform.system() != "Darwin":
        return (True, "")  # Not macOS, skip check

    try:
        # Check which python3 is being used
        which_result = subprocess.run(["which", "python3"], capture_output=True, text=True, timeout=5)
        python_path = which_result.stdout.strip()

        # If it's the system stub, check Xcode CLT BEFORE running python3
        # This prevents the popup dialog
        if python_path == "/usr/bin/python3":
            # Check if Xcode Command Line Tools are installed
            xcode_check = subprocess.run(["xcode-select", "-p"], capture_output=True, timeout=5)

            if xcode_check.returncode != 0:
                # CLT not installed - DO NOT run python3 (would trigger popup)
                return (
                    False,
                    "macOS system Python detected but Xcode Command Line Tools not installed.\n"
                    "Install with: xcode-select --install",
                )
            # CLT is installed, safe to proceed with version check

        # Only check version if we're sure it won't trigger popup
        # (either not system stub, or system stub with CLT installed)
        version_result = subprocess.run(
            ["python3", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if version_result.returncode == 0:
            version_str = version_result.stdout.strip()
            try:
                major, minor = map(int, version_str.split("."))
                if (major, minor) < (3, 10):
                    return (False, f"Python {version_str} detected. CIRIS requires Python 3.10+")
            except ValueError:
                pass  # Couldn't parse version, proceed

        return (True, "")

    except Exception:
        # If we can't check, assume it's okay and let Python itself fail later
        return (True, "")


def is_interactive_environment() -> bool:
    """Check if we're running in an interactive environment.

    Non-interactive environments include:
    - Docker containers (no TTY, DOCKER env var set)
    - Systemd services (no TTY)
    - CI/CD pipelines (CI env var set)
    - Cron jobs (no TTY)

    Returns:
        True if interactive, False if non-interactive
    """
    # Check for CI/CD environments
    ci_indicators = ["CI", "CONTINUOUS_INTEGRATION", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI"]
    if any(os.environ.get(var) for var in ci_indicators):
        return False

    # Check for Docker environment
    if os.environ.get("DOCKER") or os.path.exists("/.dockerenv"):
        return False

    # Check for systemd/service environment
    if os.environ.get("INVOCATION_ID"):  # systemd sets this
        return False

    # Check if stdin/stdout are TTY
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False

    return True


def get_default_config_path() -> Path:
    """Get the default path where config should be saved.

    Returns:
        Path to save .env file:
        - Current directory if it's a git repo (development)
        - ~/.ciris/.env otherwise (user install)
    """
    cwd = Path.cwd()

    # Check if current directory is a git repo
    if (cwd / ".git").exists():
        # Development mode - save in current directory
        return cwd / ".env"

    # Production/user install - save in ~/.ciris/
    user_ciris_dir = Path.home() / ".ciris"
    user_ciris_dir.mkdir(parents=True, exist_ok=True)
    return user_ciris_dir / ".env"
