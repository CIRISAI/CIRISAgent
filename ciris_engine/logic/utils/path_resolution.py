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

    # Priority 2: Android mode - use app's files directory
    if is_android():
        validated = _validate_ciris_home_env(" (Android)")
        if validated:
            return validated
        # Fallback: use Path.home()/ciris (Android Chaquopy sets HOME to /data/data/{pkg}/files)
        # So this becomes /data/data/{pkg}/files/ciris
        return Path.home() / "ciris"

    # Priority 2b: iOS mode - use app's Documents directory
    if is_ios():
        validated = _validate_ciris_home_env(" (iOS)")
        if validated:
            return validated
        # Fallback: use Documents/ciris (iOS app sandbox structure)
        return Path.home() / "Documents" / "ciris"

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

    # Managed mode
    if is_managed():
        env_path = Path("/app/.env")
        return env_path if env_path.exists() else None

    # Development mode
    if is_development_mode():
        env_path = Path.cwd() / ".env"
        return env_path if env_path.exists() else None

    # Installed mode - check CIRIS_HOME then ~/ciris/
    ciris_home = get_ciris_home()
    env_path = ciris_home / ".env"
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


def _validate_env_var_name(var_name: str) -> bool:
    """Validate that var_name is a safe environment variable name.

    Args:
        var_name: Variable name to validate

    Returns:
        True if valid, False otherwise
    """
    import re
    # Env var names: start with letter/underscore, contain only alphanumeric/underscore
    return bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', var_name))


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
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)
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

    env_path = get_env_file_path()
    if not env_path:
        logger.debug(f"[env_sync] No .env file available (mobile or missing), skipped file persistence for {var_name}")
        return True  # Not an error - mobile doesn't use .env

    # Security: env_path is validated by get_env_file_path() -> get_ciris_home() -> validate_path_safety()
    # which blocks system directories (/etc, /bin, etc.) and resolves symlinks/traversal.
    # The ".env" suffix is hardcoded, not user-controlled.
    # Re-validate here to satisfy static analysis tools (defense in depth).
    try:
        env_path = validate_path_safety(env_path, context=".env file path")
    except ValueError as e:
        logger.warning(f"[env_sync] Invalid .env path: {e}")
        return False

    try:
        # Read current contents
        content = env_path.read_text()

        # Sanitize value for safe .env file inclusion
        safe_value = _sanitize_env_value(value)

        # Check if variable exists
        pattern = rf'^{re.escape(var_name)}=.*$'
        if re.search(pattern, content, re.MULTILINE):
            # Update existing variable
            content = re.sub(pattern, f'{var_name}="{safe_value}"', content, flags=re.MULTILINE)
        else:
            # Add new variable
            if not content.endswith("\n"):
                content += "\n"
            content += f'{var_name}="{safe_value}"\n'

        # Write back
        env_path.write_text(content)
        logger.info(f"[env_sync] Persisted {var_name} to .env file")
        return True

    except Exception as e:
        logger.warning(f"[env_sync] Failed to persist {var_name} to .env: {e}")
        return False


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
    """
    # Sync to environment and .env file
    sync_env_var("CIRIS_PREFERRED_LANGUAGE", language_code)

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
