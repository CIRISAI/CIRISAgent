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

#: Whether the first-run reasoning has already been logged at INFO once.
#: The decision cannot change without a restart, so repeating it is noise.
_FIRST_RUN_LOGGED = False


def _mark_first_run_logged() -> None:
    global _FIRST_RUN_LOGGED
    _FIRST_RUN_LOGGED = True


def get_config_paths() -> list[Path]:
    """The .env files this process may read, in priority order.

    ONE HOME. `get_ciris_home()` is the single resolver (managed /app →
    CIRIS_HOME → Android/iOS sandbox → dev cwd → ~/ciris) and the .env this
    process reads is THAT home's .env. `CIRIS_CONFIG_DIR` may put a config file
    ahead of it (the HA add-on keeps config apart from data); nothing else is
    consulted. The read path is the write path: `get_default_config_path()`
    resolves the same way.

    Until 2.11.3 this list ended with `~/ciris/.env` and `/etc/ciris/.env` as
    "legacy fallbacks" whatever the home was, and main.py's boot loader merged
    every one of them into os.environ. A run launched with CIRIS_HOME=X and no
    X/.env therefore booted on X's keys and identity but on ~/ciris's
    CIRIS_DB_PATH / CIRIS_DATA_DIR / AUDIT_LOG_PATH: a freshly minted node key
    against an already-claimed store, which the server correctly refuses to
    own AND refuses to let anyone claim. Two homes in one process is never
    what the operator asked for — home X is home X.

    Returns:
        - Managed:      [/app/.env]
        - Android/iOS:  [<sandbox home>/.env]
        - Otherwise:    [CIRIS_CONFIG_DIR/.env] (when set) + [<home>/.env],
                        plus [/etc/ciris/.env] ONLY when the home is the
                        implicit ~/ciris default — a system install's
                        site-wide file belongs to a home nobody named.

        Note: ~/.ciris/ is for keys/secrets only, NOT config!
    """
    from ciris_engine.logic.utils.path_resolution import (
        get_ciris_home,
        is_android,
        is_ios,
        is_managed,
        validate_path_safety,
    )

    # Managed mode: only /app/.env — the manager owns the mount layout.
    if is_managed():
        return [Path("/app/.env")]

    ciris_home = get_ciris_home()

    # App sandboxes: the one home the platform gave us.
    if is_android() or is_ios():
        logger.info(f"App sandbox: checking {ciris_home / '.env'}")
        return [ciris_home / ".env"]

    paths: list[Path] = []

    # Explicit config dir (HA add-on, dev/testing) goes first.
    config_dir_override = os.environ.get("CIRIS_CONFIG_DIR")
    if config_dir_override:
        try:
            override_dir = validate_path_safety(Path(config_dir_override).expanduser(), context="CIRIS_CONFIG_DIR")
            paths.append(override_dir / ".env")
        except ValueError as e:
            logger.warning(f"Invalid CIRIS_CONFIG_DIR, skipping: {e}")

    home_env = ciris_home / ".env"
    if home_env not in paths:
        paths.append(home_env)

    # The site-wide file is a SYSTEM install's, i.e. the ~/ciris home. A home
    # somewhere else — named with CIRIS_HOME, or detected as a dev cwd — is
    # complete on its own.
    #
    # THE TEST IS THE HOME, NOT WHETHER CIRIS_HOME IS EXPORTED YET. Keying on
    # `not os.environ.get("CIRIS_HOME")` made this function answer differently
    # depending on WHEN in the boot it was called: main.py runs load_boot_env()
    # first (CIRIS_HOME unset → /etc/ciris/.env in the list, loaded), then
    # ensure_ciris_home_env() EXPORTS CIRIS_HOME, and every later caller —
    # is_first_run(), env_utils — got a list without it. A system install whose
    # only config is /etc/ciris/.env therefore booted configured and then failed
    # its own first-run check, which deletes the "stale" CIRIS_CONFIGURED it had
    # just loaded and runs the wizard on a configured machine. One home, one
    # answer, at every point in the boot.
    if ciris_home == Path.home() / "ciris":
        system_config = Path("/etc/ciris/.env")
        if system_config.parent.exists():
            paths.append(system_config)

    return paths


def load_boot_env() -> list[Path]:
    """Load the home's .env into os.environ before anything reads it.

    Called by main.py before any ciris_engine import that resolves a path.
    The real environment wins over the file (override=False), so an operator's
    explicit `CIRIS_DB_PATH=… ciris-agent` still beats what setup wrote.

    Returns the files that were loaded, in order, so the boot banner can say
    which config this run is on.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # dotenv is optional; the environment alone must do
        return []

    loaded: list[Path] = []
    for config_path in get_config_paths():
        try:
            present = config_path.exists()
        except OSError:
            present = False
        if present:
            load_dotenv(config_path, override=False)
            loaded.append(config_path)
    return loaded


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

    # SAY IT ONCE. CIRISAgent#1073.
    #
    # This function is called on nearly every request. In a user's log covering
    # 3m40s it ran 66 times and emitted FIVE INFO lines each — 330 lines, 12% of
    # the entire file — to report an answer that had not changed since boot and
    # could not change without a restart.
    #
    # The first pass through logs at INFO exactly as before, so the boot-time
    # reasoning is fully preserved. Every repeat drops to DEBUG: still there when
    # someone is debugging this specific decision, invisible when they are
    # looking for the 401 buried underneath it.
    _lvl = logging.INFO if not _FIRST_RUN_LOGGED else logging.DEBUG
    logger.log(_lvl, "Checking first-run status...")

    # Managed mode: NEVER first-run (manager handles configuration)
    if is_managed():
        logger.info("Running in MANAGED mode - not first run (manager handles configuration)")
        return False

    # Log mode detection
    from ciris_engine.logic.utils.path_resolution import is_development_mode

    dev_mode = is_development_mode()
    logger.log(_lvl, f"Running in {'DEVELOPMENT' if dev_mode else 'INSTALLED'} mode (git repo: {dev_mode})")

    # FORCE first-run mode for testing (e.g., QA runner setup tests)
    force_first_run = os.environ.get("CIRIS_FORCE_FIRST_RUN")
    logger.log(_lvl, f"CIRIS_FORCE_FIRST_RUN env var: {force_first_run}")
    if force_first_run:
        logger.info("CIRIS_FORCE_FIRST_RUN is set - forcing first-run mode")
        return True

    # Check config files — a file must exist AND contain CIRIS_CONFIGURED="true"
    # File existence alone is not sufficient (file may be a stub after failed wipe)
    config_paths = get_config_paths()
    logger.log(_lvl, f"Checking config paths: {[str(p) for p in config_paths]}")
    for path in config_paths:
        if path.exists() and path.is_file():
            try:
                content = path.read_text()
                if "CIRIS_CONFIGURED" in content and "true" in content.lower():
                    logger.log(_lvl, f"Found configured .env at {path} - NOT first run")
                    _mark_first_run_logged()
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

    # Default: CIRIS_HOME/.env if set, otherwise ~/ciris/.env (XDG default).
    # Previously this branch hardcoded ~/ciris/.env on desktop/dev. That
    # broke multi-process test harnesses (qa_runner desktop module): the
    # FIRST backend run with CIRIS_HOME=<project_root> still wrote the
    # setup wizard's .env to ~/ciris/.env, and that .env carried
    # CIRIS_DB_PATH=~/ciris/data/... — which then overrode CIRIS_HOME on
    # the SECOND backend run, putting the auth WAs in /home/emoore/ciris/
    # while the rest of the agent state lived in <project_root>/data.
    # Honoring CIRIS_HOME here means an operator's explicit "this is where
    # the agent data lives" knob applies to .env too. ~/.ciris/ remains
    # for secrets/keys only; ~/ciris/.env is still the fallback when
    # CIRIS_HOME is unset (XDG-friendly desktop default).
    from ciris_engine.logic.utils.path_resolution import get_ciris_home

    ciris_home_dir = get_ciris_home()
    ciris_home_dir.mkdir(parents=True, exist_ok=True)
    return ciris_home_dir / ".env"
