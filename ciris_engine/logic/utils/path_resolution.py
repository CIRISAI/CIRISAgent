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

import os
from pathlib import Path
from typing import Optional


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
        True if current directory is a git repository
    """
    return (Path.cwd() / ".git").exists()


def get_ciris_home() -> Path:
    """Get the CIRIS home directory.

    Returns:
        Path to CIRIS home directory:
        - /app/ if managed by CIRIS Manager (highest priority)
        - Current directory if in git repo (development)
        - CIRIS_HOME env var if set
        - ~/ciris/ otherwise (installed mode)
    """
    # Priority 1: CIRIS Manager mode - use /app/
    if is_managed():
        return Path("/app")

    # Priority 2: Development mode - use current directory
    if is_development_mode():
        return Path.cwd()

    # Priority 3: CIRIS_HOME environment variable
    env_home = os.getenv("CIRIS_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()

    # Priority 4: Default installed mode - ~/ciris/
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


def get_package_root() -> Path:
    """Get the installed package root directory.

    Returns:
        Path to ciris_engine package directory
    """
    import ciris_engine

    return Path(ciris_engine.__file__).parent


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

    # 2. Development mode: check CWD
    if is_development_mode():
        search_paths.append(Path.cwd() / "ciris_templates" / template_name)

    # 3. CIRIS_HOME if set (custom location)
    env_home = os.getenv("CIRIS_HOME")
    if env_home:
        search_paths.append(Path(env_home).expanduser() / "ciris_templates" / template_name)

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

    # Development mode
    if is_development_mode():
        dev_templates = Path.cwd() / "ciris_templates"
        if dev_templates.exists():
            return dev_templates

    # CIRIS_HOME
    env_home = os.getenv("CIRIS_HOME")
    if env_home:
        env_templates = Path(env_home).expanduser() / "ciris_templates"
        if env_templates.exists():
            return env_templates

    # User home
    user_templates = Path.home() / "ciris" / "ciris_templates"
    if user_templates.exists():
        return user_templates

    # Package bundled templates
    return get_package_root() / "ciris_templates"
