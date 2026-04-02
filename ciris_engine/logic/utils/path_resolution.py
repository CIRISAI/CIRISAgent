"""
CIRIS Path Resolution Utility.

Resolves paths for data, logs, templates, and configuration files.
Supports development mode, installed mode, and CIRIS Manager mode.

Path Resolution Strategy:
1. CIRIS Manager Mode (managed deployment):
   - Detected via CIRIS_MANAGED=true or volume mounts at /app/data
   - Use /app/ for all paths
   - Templates: /app/ciris_templates/
   - Data: /app/data/
   - Logs: /app/logs/

2. Development Mode (git repo detected):
   - Use current working directory for everything
   - Templates: ./ciris_templates/
   - Data: ./data/
   - Logs: ./logs/

3. Installed Mode (pip install):
   - Use CIRIS_HOME env var if set, otherwise ~/ciris/
   - Templates: Check multiple locations (user overrides, then bundled)
   - Data: CIRIS_HOME/data/ or ~/ciris/data/
   - Logs: CIRIS_HOME/logs/ or ~/ciris/logs/

4. Template Search Order:
   a. Current working directory (if in git repo)
   b. CIRIS_HOME/ciris_templates/ (if CIRIS_HOME set)
   c. ~/ciris/ciris_templates/ (user custom templates)
   d. <package_root>/ciris_templates/ (bundled templates)
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Directories that should never be written to (security measure)
# These are system-critical directories that could be abused
FORBIDDEN_PATH_PREFIXES = frozenset(
    {
        "/bin",
        "/sbin",
        "/usr/bin",
        "/usr/sbin",
        "/etc",
        "/root",
        "/var/run",
        "/var/lock",
        "/boot",
        "/dev",
        "/proc",
        "/sys",
    }
)

# Exceptions to forbidden paths (safe user-accessible locations)
ALLOWED_PATH_EXCEPTIONS = frozenset(
    {
        "/dev/shm",  # tmpfs - safe for user data
    }
)

# Context string for CIRIS_HOME validation errors
CIRIS_HOME_ENV_CONTEXT = "CIRIS_HOME environment variable"

# Allowlist of valid ISO 639-1 language codes supported by CIRIS
# This is the ONLY source of truth for valid language codes - user input MUST match
SUPPORTED_LANGUAGE_CODES = frozenset(
    {
        "am",  # Amharic
        "ar",  # Arabic
        "de",  # German
        "en",  # English
        "es",  # Spanish
        "fr",  # French
        "hi",  # Hindi
        "it",  # Italian
        "ja",  # Japanese
        "ko",  # Korean
        "pt",  # Portuguese
        "ru",  # Russian
        "sw",  # Swahili
        "tr",  # Turkish
        "ur",  # Urdu
        "zh",  # Chinese
    }
)


def validate_path_safety(path: Path, context: str = "path") -> Path:
    """Validate that a path is safe to use for file operations.

    Security checks performed:
    1. Path must be absolute after resolution (no relative path tricks)
    2. Path must not be in system-critical directories
    3. Path must not contain null bytes or other dangerous characters

    Args:
        path: The path to validate
        context: Description of where this path came from (for logging)

    Returns:
        The validated, resolved path

    Raises:
        ValueError: If the path fails validation
    """
    # Resolve to absolute path (handles symlinks and ..)
    # Note: Path.resolve() raises ValueError for null bytes, which is correct
    try:
        resolved = path.resolve()
    except ValueError as e:
        # Re-raise with context (null bytes, invalid characters, etc.)
        raise ValueError(f"Invalid {context}: {e}") from e

    resolved_str = str(resolved)

    # Check against forbidden prefixes
    for forbidden in FORBIDDEN_PATH_PREFIXES:
        if resolved_str == forbidden or resolved_str.startswith(f"{forbidden}/"):
            # Check if this path is in an allowed exception
            is_allowed = any(
                resolved_str == allowed or resolved_str.startswith(f"{allowed}/") for allowed in ALLOWED_PATH_EXCEPTIONS
            )
            if not is_allowed:
                raise ValueError(f"Invalid {context}: path '{resolved}' is in forbidden system directory '{forbidden}'")

    return resolved


def is_android() -> bool:
    """Detect if running on Android platform.

    Checks multiple indicators:
    - 'ANDROID_ROOT' environment variable (set by Android system)
    - 'ANDROID_DATA' environment variable
    - sys.platform contains 'linux' and /data/data exists
    - Running under Chaquopy (Python on Android)

    Returns:
        True if running on Android
    """
    # Check for Android-specific environment variables
    if os.getenv("ANDROID_ROOT") or os.getenv("ANDROID_DATA"):
        return True

    # Check for Chaquopy marker (Python on Android)
    if hasattr(sys, "getandroidapilevel"):
        return True

    # Check for Android data directory structure
    if sys.platform == "linux" and Path("/data/data").exists():
        return True

    return False


def is_ios() -> bool:
    """Detect if running on iOS platform.

    Checks multiple indicators:
    - sys.platform == 'ios' (set by BeeWare/Briefcase)
    - Running under BeeWare with iOS-specific paths

    Returns:
        True if running on iOS
    """
    # BeeWare/Briefcase sets sys.platform to 'ios'
    if sys.platform == "ios":
        return True

    # Check for iOS-specific paths
    if sys.platform == "darwin":
        # Check for iOS Simulator or device paths
        home = str(Path.home())
        if "CoreSimulator/Devices" in home or "/var/mobile" in home:
            return True

    return False


def is_managed() -> bool:
    """Detect if running under CIRIS Manager using multiple signals.

    Returns True if majority of indicators suggest managed environment.

    Checks:
    - CIRIS_MANAGED environment variable
    - Volume mounts at /app/data and /app/logs
    - Service token presence
    - Docker environment with /app structure
    """
    indicators = []

    # 1. Check for explicit manager flag
    indicators.append(os.getenv("CIRIS_MANAGED", "").lower() == "true")

    # 2. Check for volume mounts (most reliable for Docker deployments)
    indicators.append(os.path.ismount("/app/data"))
    indicators.append(os.path.ismount("/app/logs"))

    # 3. Check for service token (only set by manager)
    indicators.append(bool(os.getenv("CIRIS_SERVICE_TOKEN")))

    # 4. Check for Docker environment with /app structure
    indicators.append(Path("/.dockerenv").exists() and Path("/app/data").exists() and Path("/app/logs").exists())

    # Return True if majority indicate managed (at least 2 out of 5)
    return sum(indicators) >= 2


def is_development_mode() -> bool:
    """Check if running in development mode (git repository).

    Returns:
        True if current directory is a git repository AND not on Android.
        On Android, .git may exist in the bundled code but we're not in dev mode.
    """
    # Never dev mode on Android - even if .git exists in bundled code
    if is_android():
        return False

    return (Path.cwd() / ".git").exists()


def _validate_ciris_home_env(platform_suffix: str = "") -> Optional[Path]:
    """Validate CIRIS_HOME environment variable and return validated path.

    Args:
        platform_suffix: Optional suffix for context (e.g., " (Android)", " (iOS)")

    Returns:
        Validated Path if CIRIS_HOME is set and valid, None otherwise
    """
    env_home = os.getenv("CIRIS_HOME")
    if not env_home:
        return None

    context = f"{CIRIS_HOME_ENV_CONTEXT}{platform_suffix}"
    try:
        # Use expanduser for desktop, raw path for mobile
        path = Path(env_home).expanduser() if not platform_suffix else Path(env_home)
        return validate_path_safety(path, context=context)
    except ValueError as e:
        logger.warning(f"Ignoring invalid CIRIS_HOME{platform_suffix}: {e}")
        return None


# Known Android package names for CIRIS mobile app
_ANDROID_PACKAGE_NAMES = [
    "ai.ciris.mobile.debug",  # Debug build
    "ai.ciris.mobile",  # Release build
]


def _get_android_ciris_home() -> Path:
    """Get CIRIS home directory on Android with robust path detection.

    Uses multiple strategies to find the correct path:
    1. CIRIS_HOME environment variable (if set and valid)
    2. Detect from existing ciris directories in known Android app locations
    3. Use Path.home() / "ciris" (Chaquopy sets HOME to app files dir)

    Returns:
        Path to CIRIS home directory on Android
    """
    # Strategy 1: Check CIRIS_HOME env var first
    validated = _validate_ciris_home_env(" (Android)")
    if validated:
        logger.debug(f"Android CIRIS_HOME from env: {validated}")
        return validated

    # Strategy 2: Check known Android app data locations for existing ciris dirs
    # This handles both /data/data/ and /data/user/0/ paths
    for pkg in _ANDROID_PACKAGE_NAMES:
        for base in ["/data/data", "/data/user/0"]:
            candidate = Path(base) / pkg / "files" / "ciris"
            if candidate.exists() and candidate.is_dir():
                logger.info(f"Android: found existing CIRIS dir at {candidate}")
                return candidate
            # Also check if parent files dir exists (for first-run before ciris dir created)
            files_dir = Path(base) / pkg / "files"
            if files_dir.exists() and files_dir.is_dir():
                ciris_dir = files_dir / "ciris"
                logger.info(f"Android: using {ciris_dir} (files dir exists)")
                return ciris_dir

    # Strategy 3: Fallback to Path.home() / "ciris"
    # Chaquopy sets HOME to /data/data/{pkg}/files, so this should work
    home_based = Path.home() / "ciris"
    logger.info(f"Android: falling back to Path.home()/ciris = {home_based}")

    # Sanity check: warn if this doesn't look like an Android path
    home_str = str(Path.home())
    if not (home_str.startswith("/data/data/") or home_str.startswith("/data/user/")):
        logger.warning(
            f"Android detected but HOME={home_str} doesn't look like Android app dir. "
            f"CIRIS_HOME should be set explicitly for reliable operation."
        )

    return home_based


def _get_ios_ciris_home() -> Path:
    """Get CIRIS home directory on iOS with robust path detection.

    Uses multiple strategies to find the correct path:
    1. CIRIS_HOME environment variable (if set and valid)
    2. Detect from existing ciris directories in iOS app sandbox
    3. Use Path.home() / "Documents" / "ciris" (iOS app sandbox)

    Returns:
        Path to CIRIS home directory on iOS
    """
    # Strategy 1: Check CIRIS_HOME env var first
    validated = _validate_ciris_home_env(" (iOS)")
    if validated:
        logger.debug(f"iOS CIRIS_HOME from env: {validated}")
        return validated

    # Strategy 2: Check common iOS app sandbox locations
    home = Path.home()

    # iOS apps typically have Documents, Library, tmp directories
    # We use Documents/ciris for user data
    documents_ciris = home / "Documents" / "ciris"
    if documents_ciris.exists() and documents_ciris.is_dir():
        logger.info(f"iOS: found existing CIRIS dir at {documents_ciris}")
        return documents_ciris

    # Check if Documents dir exists (for first-run)
    documents_dir = home / "Documents"
    if documents_dir.exists() and documents_dir.is_dir():
        logger.info(f"iOS: using {documents_ciris} (Documents dir exists)")
        return documents_ciris

    # Strategy 3: Fallback - just use Documents/ciris
    logger.info(f"iOS: falling back to {documents_ciris}")

    # Sanity check: warn if this doesn't look like an iOS path
    home_str = str(home)
    if not ("/var/mobile" in home_str or "CoreSimulator" in home_str):
        logger.warning(
            f"iOS detected but HOME={home_str} doesn't look like iOS app sandbox. "
            f"CIRIS_HOME should be set explicitly for reliable operation."
        )

    return documents_ciris


def get_ciris_home() -> Path:
    """Get the CIRIS home directory.

    Returns:
        Path to CIRIS home directory:
        - /app/ if managed by CIRIS Manager (highest priority)
        - Android app files/ciris/ if on Android
        - iOS Documents/ciris/ if on iOS
        - Current directory if in git repo (development)
        - CIRIS_HOME env var if set
        - ~/ciris/ otherwise (installed mode)
    """
    # Priority 1: CIRIS Manager mode - use /app/
    if is_managed():
        return Path("/app")

    # Priority 2: Android mode - use robust Android path detection
    if is_android():
        return _get_android_ciris_home()

    # Priority 2b: iOS mode - use robust iOS path detection
    if is_ios():
        return _get_ios_ciris_home()

    # Priority 3: Development mode - use current directory
    if is_development_mode():
        return Path.cwd()

    # Priority 4: CIRIS_HOME environment variable
    validated = _validate_ciris_home_env()
    if validated:
        return validated

    # Priority 5: Default installed mode - ~/ciris/
    return Path.home() / "ciris"


def get_data_dir() -> Path:
    """Get the data directory path.

    Returns:
        Path to data directory (CIRIS_HOME/data/)
    """
    return get_ciris_home() / "data"


def get_logs_dir() -> Path:
    """Get the logs directory path.

    Returns:
        Path to logs directory (CIRIS_HOME/logs/)
    """
    return get_ciris_home() / "logs"


def get_config_dir() -> Path:
    """Get the config directory path.

    Returns:
        Path to config directory (CIRIS_HOME/config/)
    """
    return get_ciris_home() / "config"


def get_secrets_home() -> Path:
    """Get the secrets/keys directory.

    On desktop: ~/ciris/secrets/
    On Android: CIRIS_HOME/secrets/ (within app sandbox)
    On iOS: CIRIS_HOME/secrets/ (within Documents/)

    Returns:
        Path to secrets directory for keys, oauth config, etc.
    """
    if is_android() or is_ios():
        # On mobile, use secrets dir within CIRIS_HOME (which is in app sandbox)
        return get_ciris_home() / "secrets"

    # Desktop: use ~/ciris/secrets/
    return Path.home() / "ciris" / "secrets"


def get_package_root() -> Path:
    """Get the installed package root directory.

    Returns:
        Path to ciris_engine package directory
    """
    import ciris_engine

    return Path(ciris_engine.__file__).parent


def ensure_ciris_home_env() -> Path:
    """Ensure CIRIS_HOME environment variable is set for all platforms.

    This function MUST be called early in application startup, before any
    code that depends on CIRIS_HOME (especially CIRISVerify/verifier_singleton).

    Platform support:
    - Linux (desktop, server, WSL)
    - macOS (x64, arm64)
    - Windows (x64)
    - Android (via Chaquopy)
    - iOS (via BeeWare/PythonKit)
    - Docker/managed deployments

    The function:
    1. Computes the correct CIRIS_HOME using get_ciris_home()
    2. Sets the CIRIS_HOME environment variable
    3. Sets CIRIS_DATA_DIR for CIRISVerify compatibility
    4. Creates the directory if it doesn't exist
    5. Returns the resolved path

    Returns:
        Path to CIRIS home directory

    Example:
        # In main.py, call this FIRST before any imports that use CIRISVerify
        from ciris_engine.logic.utils.path_resolution import ensure_ciris_home_env
        ciris_home = ensure_ciris_home_env()
    """
    # Compute the correct home directory for this platform
    ciris_home = get_ciris_home()

    # Resolve to absolute path
    ciris_home = ciris_home.resolve()

    # Set CIRIS_HOME environment variable (use setdefault to not override explicit user setting)
    # But if CIRIS_HOME is already set, validate it matches our computed path in dev mode
    existing_home = os.environ.get("CIRIS_HOME")
    if existing_home:
        existing_path = Path(existing_home).resolve()
        if existing_path != ciris_home:
            # In development mode, trust the computed path over env var
            # In other modes, trust the explicit env var
            if is_development_mode():
                logger.warning(
                    f"[path_resolution] CIRIS_HOME env ({existing_path}) differs from "
                    f"computed path ({ciris_home}) in dev mode - using computed path"
                )
                os.environ["CIRIS_HOME"] = str(ciris_home)
            else:
                # Trust the explicit env var in non-dev modes
                ciris_home = existing_path
                logger.info(f"[path_resolution] Using explicit CIRIS_HOME: {ciris_home}")
    else:
        os.environ["CIRIS_HOME"] = str(ciris_home)

    # Set CIRIS_DATA_DIR for CIRISVerify compatibility
    # CIRISVerify reads this for key storage path
    data_dir = ciris_home / "data"
    os.environ.setdefault("CIRIS_DATA_DIR", str(data_dir))

    # Create home directory if it doesn't exist (with appropriate permissions)
    try:
        ciris_home.mkdir(parents=True, exist_ok=True)
        # Ensure data directory exists too
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning(f"[path_resolution] Could not create CIRIS_HOME directory: {e}")

    # Log the configuration for debugging
    platform_info = []
    if is_android():
        platform_info.append("Android")
    if is_ios():
        platform_info.append("iOS")
    if is_managed():
        platform_info.append("Managed/Docker")
    if is_development_mode():
        platform_info.append("Development")
    if not platform_info:
        platform_info.append("Installed")

    logger.info(
        f"[path_resolution] CIRIS_HOME configured: {ciris_home} "
        f"(platform: {', '.join(platform_info)}, "
        f"os: {sys.platform})"
    )

    return ciris_home


def find_template_file(template_name: str) -> Optional[Path]:
    """Find a template file by searching multiple locations.

    Search order:
    1. /app/ciris_templates/ (managed mode only)
    2. CWD/ciris_templates/ (development mode only)
    3. CIRIS_HOME/ciris_templates/ (if CIRIS_HOME is set)
    4. ~/ciris/ciris_templates/ (user custom templates)
    5. <package_root>/ciris_templates/ (bundled templates)

    Args:
        template_name: Name of template (with or without .yaml extension)

    Returns:
        Path to template file if found, None otherwise
    """
    # Ensure .yaml extension
    if not template_name.endswith(".yaml"):
        template_name = f"{template_name}.yaml"

    search_paths = []

    # 1. Managed mode: check /app/ciris_templates/ first
    if is_managed():
        search_paths.append(Path("/app") / "ciris_templates" / template_name)

    # 2. Development mode: check CWD and ciris_engine subdirectory
    if is_development_mode():
        search_paths.append(Path.cwd() / "ciris_templates" / template_name)
        search_paths.append(Path.cwd() / "ciris_engine" / "ciris_templates" / template_name)

    # 3. CIRIS_HOME if set (custom location)
    # Security: Validate user-provided path before use
    env_home = os.getenv("CIRIS_HOME")
    if env_home:
        try:
            validated_path = validate_path_safety(Path(env_home).expanduser(), context=CIRIS_HOME_ENV_CONTEXT)
            search_paths.append(validated_path / "ciris_templates" / template_name)
        except ValueError:
            pass  # Skip invalid CIRIS_HOME, fall through to other locations

    # 4. User home directory (~/ciris/ciris_templates/)
    search_paths.append(Path.home() / "ciris" / "ciris_templates" / template_name)

    # 5. Installed package location (bundled)
    search_paths.append(get_package_root() / "ciris_templates" / template_name)

    # Return first existing path
    for path in search_paths:
        if path.exists() and path.is_file():
            return path

    return None


def get_template_directory() -> Path:
    """Get the template directory path.

    Returns the first existing template directory from:
    1. /app/ciris_templates/ (managed mode)
    2. CWD/ciris_templates/ (development)
    3. CIRIS_HOME/ciris_templates/ (if set)
    4. ~/ciris/ciris_templates/ (user)
    5. <package_root>/ciris_templates/ (bundled)

    Returns:
        Path to template directory
    """
    # Managed mode
    if is_managed():
        managed_templates = Path("/app") / "ciris_templates"
        if managed_templates.exists():
            return managed_templates

    # Development mode - check both repo root and ciris_engine subdirectory
    if is_development_mode():
        # First check repo root (for backwards compatibility)
        dev_templates = Path.cwd() / "ciris_templates"
        if dev_templates.exists():
            return dev_templates
        # Also check ciris_engine subdirectory (actual location in source tree)
        dev_engine_templates = Path.cwd() / "ciris_engine" / "ciris_templates"
        if dev_engine_templates.exists():
            return dev_engine_templates

    # CIRIS_HOME
    # Security: Validate user-provided path before use
    env_home = os.getenv("CIRIS_HOME")
    if env_home:
        try:
            validated_path = validate_path_safety(Path(env_home).expanduser(), context=CIRIS_HOME_ENV_CONTEXT)
            env_templates = validated_path / "ciris_templates"
            if env_templates.exists():
                return env_templates
        except ValueError:
            pass  # Skip invalid CIRIS_HOME, fall through to other locations

    # User home
    user_templates = Path.home() / "ciris" / "ciris_templates"
    if user_templates.exists():
        return user_templates

    # Package bundled templates
    return get_package_root() / "ciris_templates"


# Hardcoded env filename - never user-controlled
_ENV_FILENAME = ".env"


def _get_allowed_env_directories() -> list[Path]:
    """Get explicit list of directories where .env files may exist.

    This function returns a hardcoded list of allowed directories,
    preventing path traversal attacks by not using user-controlled paths
    directly in file operations.

    Returns:
        List of allowed directories (resolved to absolute paths)
    """
    allowed: list[Path] = []

    # Managed mode: /app/ is the only allowed location
    if is_managed():
        allowed.append(Path("/app").resolve())
        return allowed

    # Development mode: CWD (verified to be a git repo)
    if is_development_mode():
        cwd = Path.cwd().resolve()
        # Only allow if it's a git repo (development mode check)
        if (cwd / ".git").exists():
            allowed.append(cwd)

    # User home directory based locations
    home = Path.home().resolve()
    allowed.append(home / "ciris")

    # CIRIS_HOME if set and validated
    ciris_home_env = os.environ.get("CIRIS_HOME")
    if ciris_home_env:
        try:
            ciris_home = validate_path_safety(Path(ciris_home_env), CIRIS_HOME_ENV_CONTEXT)
            allowed.append(ciris_home)
        except ValueError:
            pass  # Invalid CIRIS_HOME, skip it

    return allowed


def _is_path_in_allowed_env_dirs(path: Path) -> bool:
    """Check if a path's parent directory is in the allowed list.

    Args:
        path: Path to check (should end in .env)

    Returns:
        True if the path's parent is in allowed directories
    """
    try:
        resolved = path.resolve()
        parent = resolved.parent
    except (ValueError, OSError):
        return False

    for allowed_dir in _get_allowed_env_directories():
        if parent == allowed_dir:
            return True
    return False


def get_env_file_path() -> Optional[Path]:
    """Get the path to the .env file.

    Platform-aware resolution:
    - Managed: /app/.env
    - Development: CWD/.env
    - Android/iOS: None (no .env file on mobile, use graph only)
    - Installed: CIRIS_HOME/.env or ~/ciris/.env

    Returns:
        Path to .env file, or None if not applicable (mobile platforms)
    """
    # Mobile platforms don't use .env files
    if is_android() or is_ios():
        return None

    # Managed mode - hardcoded path
    if is_managed():
        env_path = Path("/app") / _ENV_FILENAME
        return env_path if env_path.exists() else None

    # Development mode - construct from CWD + hardcoded filename
    if is_development_mode():
        env_path = Path.cwd() / _ENV_FILENAME
        return env_path if env_path.exists() else None

    # Installed mode - check CIRIS_HOME then ~/ciris/
    ciris_home = get_ciris_home()
    env_path = ciris_home / _ENV_FILENAME
    if env_path.exists():
        return env_path

    return None


def _sanitize_env_value(value: str) -> str:
    """Sanitize a value for safe inclusion in .env file.

    Prevents injection attacks by escaping/removing dangerous characters.

    Args:
        value: Raw value to sanitize

    Returns:
        Sanitized value safe for .env file
    """
    # Remove newlines and carriage returns (prevent multi-line injection)
    sanitized = value.replace("\n", "").replace("\r", "")
    # Escape double quotes
    sanitized = sanitized.replace('"', '\\"')
    # Escape backslashes (must come after quote escaping)
    sanitized = sanitized.replace("\\\\", "\\")
    return sanitized


def _parse_and_sanitize_env_content(content: str) -> dict[str, str]:
    """Parse .env file content and return sanitized key-value pairs.

    This function validates each line of the .env file to ensure:
    1. Only valid environment variable names are accepted
    2. Values are sanitized to prevent injection

    This breaks the taint chain by reconstructing the content from
    validated components rather than passing through raw user-controllable data.

    Args:
        content: Raw content read from .env file

    Returns:
        Dictionary of validated var_name -> sanitized_value pairs
    """
    import re

    result: dict[str, str] = {}

    for line in content.split("\n"):
        # Skip empty lines and comments
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Parse VAR=value or VAR="value" format
        # Use \w for word characters (alphanumeric + underscore)
        match = re.match(r"^([A-Za-z_]\w*)=(.*)$", line)
        if not match:
            # Skip malformed lines (potential injection attempts)
            continue

        var_name = match.group(1)
        raw_value = match.group(2)

        # Validate variable name
        if not _validate_env_var_name(var_name):
            continue

        # Strip quotes if present (single or double)
        if (raw_value.startswith('"') and raw_value.endswith('"')) or (
            raw_value.startswith("'") and raw_value.endswith("'")
        ):
            raw_value = raw_value[1:-1]

        # Sanitize the value
        sanitized_value = _sanitize_env_value(raw_value)
        result[var_name] = sanitized_value

    return result


def _reconstruct_env_content(env_vars: dict[str, str]) -> str:
    """Reconstruct .env file content from validated key-value pairs.

    Args:
        env_vars: Dictionary of var_name -> value pairs (already sanitized)

    Returns:
        Safe .env file content
    """
    lines = [f'{name}="{value}"' for name, value in sorted(env_vars.items())]
    return "\n".join(lines) + "\n" if lines else ""


def _validate_env_var_name(var_name: str) -> bool:
    """Validate that var_name is a safe environment variable name.

    Args:
        var_name: Variable name to validate

    Returns:
        True if valid, False otherwise
    """
    import re

    # Env var names: start with letter/underscore, contain only word characters (\w)
    return bool(re.match(r"^[A-Za-z_]\w*$", var_name))


def sanitize_for_log(value: str, max_length: int = 20) -> str:
    """Sanitize a value for safe inclusion in log messages.

    Prevents log injection by removing dangerous characters and truncating.

    Args:
        value: Value to sanitize
        max_length: Maximum length of output (default 20)

    Returns:
        Sanitized value safe for logging
    """
    import re

    # Remove newlines, carriage returns, and control characters
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", value)
    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."
    return sanitized


def sync_env_var(var_name: str, value: str, persist_to_file: bool = True) -> bool:
    """Sync an environment variable to both os.environ and .env file.

    Platform-aware:
    - Desktop/server: Updates both os.environ and .env file
    - Mobile (Android/iOS): Updates only os.environ (no .env file)
    - Managed: Updates os.environ, optionally .env file

    Args:
        var_name: Environment variable name (e.g., 'CIRIS_PREFERRED_LANGUAGE')
        value: Value to set
        persist_to_file: Whether to persist to .env file (default True)

    Returns:
        True if successful, False if .env file update failed (os.environ still updated)

    Raises:
        ValueError: If var_name contains invalid characters
    """
    import re

    # Validate var_name to prevent injection
    if not _validate_env_var_name(var_name):
        raise ValueError(f"Invalid environment variable name: {var_name}")

    # Always update os.environ (os.environ handles its own safety)
    os.environ[var_name] = value
    logger.debug(f"[env_sync] Set os.environ[{var_name}]")

    # Skip file persistence on mobile or if not requested
    if not persist_to_file:
        return True

    # Get env file path - returns None on mobile or if .env doesn't exist
    env_path_candidate = get_env_file_path()
    if not env_path_candidate:
        logger.debug(f"[env_sync] No .env file available (mobile or missing), skipped file persistence for {var_name}")
        return True  # Not an error - mobile doesn't use .env

    # Security: Verify the path is in an allowed directory and uses hardcoded filename.
    # This prevents path traversal by ensuring we only write to known-safe locations.
    try:
        env_path = validate_path_safety(env_path_candidate, context=".env file path")
    except ValueError as e:
        logger.warning(f"[env_sync] Invalid .env path: {e}")
        return False

    # Additional check: verify path is in explicit allowlist (defense in depth)
    if not _is_path_in_allowed_env_dirs(env_path):
        logger.warning(f"[env_sync] .env path not in allowed directories: {env_path}")
        return False

    # Verify filename is exactly ".env" (hardcoded, not user-controlled)
    if env_path.name != _ENV_FILENAME:
        logger.warning(f"[env_sync] Invalid .env filename: {env_path.name}")
        return False

    try:
        # Read current contents - path is now verified safe
        raw_content = env_path.read_text()

        # SECURITY: Parse and sanitize existing content to break taint chain.
        # This ensures we don't pass through any malicious content from the file.
        env_vars = _parse_and_sanitize_env_content(raw_content)

        # Sanitize the new value and add/update it
        safe_value = _sanitize_env_value(value)
        env_vars[var_name] = safe_value

        # Reconstruct clean content from validated components
        clean_content = _reconstruct_env_content(env_vars)

        # Write back - content is now fully sanitized
        env_path.write_text(clean_content)
        logger.info(f"[env_sync] Persisted {var_name} to .env file")
        return True

    except Exception as e:
        logger.warning(f"[env_sync] Failed to persist {var_name} to .env: {e}")
        return False


def _validate_language_code(language_code: str) -> str:
    """Validate and normalize a language code against the allowlist.

    This is a SECURITY function that prevents arbitrary user input from
    flowing into file operations. Only codes in SUPPORTED_LANGUAGE_CODES
    are allowed.

    Args:
        language_code: User-provided language code

    Returns:
        The validated, normalized language code (lowercase)

    Raises:
        ValueError: If language_code is not in the allowlist
    """
    if not isinstance(language_code, str):
        raise ValueError(f"Language code must be a string, got {type(language_code).__name__}")

    # Normalize to lowercase for comparison
    normalized = language_code.lower().strip()

    # Validate against allowlist - this breaks the taint chain
    if normalized not in SUPPORTED_LANGUAGE_CODES:
        raise ValueError(
            f"Invalid language code '{sanitize_for_log(language_code)}'. "
            f"Supported codes: {', '.join(sorted(SUPPORTED_LANGUAGE_CODES))}"
        )

    # Return the validated code from the allowlist (not user input)
    # This ensures the returned value is known-safe
    return normalized


def sync_language_preference(language_code: str) -> bool:
    """Sync language preference to environment and DMA prompt loader.

    This ensures the language is available to:
    1. os.environ['CIRIS_PREFERRED_LANGUAGE']
    2. .env file (on desktop/server)
    3. DMA prompt loader (for localized prompts)

    Args:
        language_code: ISO 639-1 language code (e.g., 'en', 'am', 'es')

    Returns:
        True if successful

    Raises:
        ValueError: If language_code is not a supported code
    """
    # SECURITY: Validate language code against allowlist before any file operations.
    # This sanitizes user input and breaks the taint chain from HTTP request to file write.
    validated_code = _validate_language_code(language_code)

    # Sync to environment and .env file - using validated code only
    sync_env_var("CIRIS_PREFERRED_LANGUAGE", validated_code)

    # Update the DMA prompt loader
    try:
        from ciris_engine.logic.dma.prompt_loader import set_prompt_language

        set_prompt_language(language_code)
        logger.info(f"[env_sync] Synced language preference to DMA prompt loader: {sanitize_for_log(language_code)}")
    except ImportError:
        logger.debug("[env_sync] DMA prompt_loader not available, skipping prompt language update")
    except Exception as e:
        logger.warning(f"[env_sync] Failed to update DMA prompt loader: {e}")

    return True


def load_language_preference_from_graph() -> Optional[str]:
    """Load language preference from the graph (user profile).

    This is called at startup to restore the user's language preference.

    Returns:
        Language code if found, None otherwise
    """
    # This is a sync function, so we can't easily query the graph here
    # Instead, return the env var if set (which should be synced from graph)
    return os.environ.get("CIRIS_PREFERRED_LANGUAGE")
