"""First-run detection for CIRIS Agent.

Determines if this is a first-time run by checking for configuration files.
"""

import logging
import os
import platform
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def get_config_paths() -> list[Path]:
    """Get possible configuration file locations in priority order.

    Uses path_resolution module to detect deployment mode and check appropriate locations.

    Returns:
        List of paths to check for .env files, in priority order:
        - Managed mode (Docker/CIRIS Manager):
          1. /app/.env (manager-provided config)
        - Android mode:
          1. CIRIS_HOME/.env (app's files directory)
        - iOS mode:
          1. CIRIS_HOME/.env (app's files directory)
        - Desktop/Server mode (all other cases):
          1. CIRIS_CONFIG_DIR/.env (if env var set - for dev/testing)
          2. ~/ciris/.env (user-specific config)
          3. /etc/ciris/.env (system-wide config, Linux/Unix)

        Note: As of 2.3.2, CWD-based path detection was removed for consistency.
        Use CIRIS_CONFIG_DIR environment variable for explicit dev/test override.
        Note: ~/.ciris/ is for keys/secrets only, NOT config!
    """
    from ciris_engine.logic.utils.path_resolution import (
        get_ciris_home,
        is_android,
        is_development_mode,
        is_ios,
        is_managed,
    )

    paths = []

    # Managed mode: only check /app/.env
    if is_managed():
        paths.append(Path("/app/.env"))
        return paths

    # Android mode: use get_ciris_home() which handles Android-specific paths
    if is_android():
        ciris_home = get_ciris_home()
        paths.append(ciris_home / ".env")
        logger.info(f"Android mode: checking {ciris_home / '.env'}")
        return paths

    # iOS mode: use get_ciris_home() which handles iOS-specific paths
    if is_ios():
        ciris_home = get_ciris_home()
        paths.append(ciris_home / ".env")
        logger.info(f"iOS mode: checking {ciris_home / '.env'}")
        return paths

    # User config directory — the single canonical location for config
    # Per XDG best practices: use a fixed, predictable path, not CWD
    # ~/ciris/ for config, ~/.ciris/ for secrets/keys only
    user_ciris_dir = Path.home() / "ciris"
    paths.append(user_ciris_dir / ".env")

    # Explicit override via CIRIS_CONFIG_DIR (for dev/testing)
    config_dir_override = os.environ.get("CIRIS_CONFIG_DIR")
    if config_dir_override:
        override_path = Path(config_dir_override) / ".env"
        if override_path not in paths:
            paths.insert(0, override_path)

    # System config (Unix/Linux only, both modes)
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

    In managed/Docker mode: NEVER first-run (manager handles configuration)

    Returns:
        True if this appears to be a first run, False otherwise.
    """
    from ciris_engine.logic.utils.path_resolution import is_managed

    logger.info("Checking first-run status...")

    # Managed mode: NEVER first-run (manager handles configuration)
    if is_managed():
        logger.info("Running in MANAGED mode - not first run (manager handles configuration)")
        return False

    # Log mode detection
    from ciris_engine.logic.utils.path_resolution import is_development_mode

    dev_mode = is_development_mode()
    logger.info(f"Running in {'DEVELOPMENT' if dev_mode else 'INSTALLED'} mode (git repo: {dev_mode})")

    # FORCE first-run mode for testing (e.g., QA runner setup tests)
    force_first_run = os.environ.get("CIRIS_FORCE_FIRST_RUN")
    logger.info(f"CIRIS_FORCE_FIRST_RUN env var: {force_first_run}")
    if force_first_run:
        logger.info("CIRIS_FORCE_FIRST_RUN is set - forcing first-run mode")
        return True

    # Check config files — a file must exist AND contain CIRIS_CONFIGURED="true"
    # File existence alone is not sufficient (file may be a stub after failed wipe)
    config_paths = get_config_paths()
    logger.info(f"Checking config paths: {[str(p) for p in config_paths]}")
    for path in config_paths:
        if path.exists() and path.is_file():
            try:
                content = path.read_text()
                if "CIRIS_CONFIGURED" in content and "true" in content.lower():
                    logger.info(f"Found configured .env at {path} - NOT first run")
                    return False
                else:
                    logger.info(f"Found .env at {path} but CIRIS_CONFIGURED not set - treating as first run")
            except Exception as e:
                logger.warning(f"Could not read {path}: {e}")

    # No valid config found — clear any stale CIRIS_CONFIGURED env var
    if os.environ.get("CIRIS_CONFIGURED"):
        logger.info("CIRIS_CONFIGURED env var is set but no valid .env found — clearing stale env var")
        del os.environ["CIRIS_CONFIGURED"]

    logger.info("No valid config files found - IS first run")
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
        - Android app files/ciris/.env if on Android
        - Current directory if it's a git repo (development)
        - ~/ciris/.env otherwise (user install)

        Note: ~/.ciris/ is for keys/secrets only, NOT config!

    Security: All paths are validated through validate_path_safety() to
    prevent path injection attacks via CIRIS_HOME environment variable.
    """
    from ciris_engine.logic.utils.path_resolution import (
        get_ciris_home,
        is_android,
        is_development_mode,
        is_ios,
        validate_path_safety,
    )

    # Android mode - use get_ciris_home() which validates CIRIS_HOME
    if is_android():
        ciris_home = get_ciris_home()
        # Explicit validation for security audit trail
        config_path = validate_path_safety(ciris_home / ".env", context="Android config path")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Android mode: config path is {config_path}")
        return config_path

    # iOS mode - use get_ciris_home() which validates CIRIS_HOME
    if is_ios():
        ciris_home = get_ciris_home()
        # Explicit validation for security audit trail
        config_path = validate_path_safety(ciris_home / ".env", context="iOS config path")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"iOS mode: config path is {config_path}")
        return config_path

    # Explicit override via CIRIS_CONFIG_DIR
    config_dir_override = os.environ.get("CIRIS_CONFIG_DIR")
    if config_dir_override:
        override_dir = Path(config_dir_override)
        override_dir.mkdir(parents=True, exist_ok=True)
        return override_dir / ".env"

    # Default: ~/ciris/.env for all modes (dev, installed, desktop)
    # Per XDG best practices: fixed path, not CWD
    # ~/.ciris/ is for secrets/keys only
    user_ciris_dir = Path.home() / "ciris"
    user_ciris_dir.mkdir(parents=True, exist_ok=True)
    return user_ciris_dir / ".env"
