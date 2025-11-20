"""
CIRIS Path Resolution Utility.

Resolves paths for data, logs, templates, and configuration files.
Supports both development mode (git repo) and installed mode (pip install).

Path Resolution Strategy:
1. Development Mode (git repo detected):
   - Use current working directory for everything
   - Templates: ./ciris_templates/
   - Data: ./data/
   - Logs: ./logs/

2. Installed Mode (pip install):
   - Use CIRIS_HOME env var if set, otherwise ~/ciris/
   - Templates: Check multiple locations (user overrides, then bundled)
   - Data: CIRIS_HOME/data/ or ~/ciris/data/
   - Logs: CIRIS_HOME/logs/ or ~/ciris/logs/

3. Template Search Order:
   a. Current working directory (if in git repo)
   b. CIRIS_HOME/ciris_templates/ (if CIRIS_HOME set)
   c. ~/ciris/ciris_templates/ (user custom templates)
   d. <package_root>/ciris_templates/ (bundled templates)
"""

import os
from pathlib import Path
from typing import Optional


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
        - Current directory if in git repo (development)
        - CIRIS_HOME env var if set
        - ~/ciris/ otherwise (installed mode)
    """
    # Development mode: use current directory
    if is_development_mode():
        return Path.cwd()

    # Check CIRIS_HOME environment variable
    env_home = os.getenv("CIRIS_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()

    # Default: ~/ciris/ for pip-installed package
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
    1. CWD/ciris_templates/ (development mode only)
    2. CIRIS_HOME/ciris_templates/ (if CIRIS_HOME is set)
    3. ~/ciris/ciris_templates/ (user custom templates)
    4. <package_root>/ciris_templates/ (bundled templates)

    Args:
        template_name: Name of template (with or without .yaml extension)

    Returns:
        Path to template file if found, None otherwise
    """
    # Ensure .yaml extension
    if not template_name.endswith(".yaml"):
        template_name = f"{template_name}.yaml"

    search_paths = []

    # 1. Development mode: check CWD first
    if is_development_mode():
        search_paths.append(Path.cwd() / "ciris_templates" / template_name)

    # 2. CIRIS_HOME if set (custom location)
    env_home = os.getenv("CIRIS_HOME")
    if env_home:
        search_paths.append(Path(env_home).expanduser() / "ciris_templates" / template_name)

    # 3. User home directory (~/ciris/ciris_templates/)
    search_paths.append(Path.home() / "ciris" / "ciris_templates" / template_name)

    # 4. Installed package location
    search_paths.append(get_package_root() / "ciris_templates" / template_name)

    # Return first existing path
    for path in search_paths:
        if path.exists() and path.is_file():
            return path

    return None


def get_template_directory() -> Path:
    """Get the template directory path.

    Returns the first existing template directory from:
    1. CWD/ciris_templates/ (development)
    2. CIRIS_HOME/ciris_templates/ (if set)
    3. ~/ciris/ciris_templates/ (user)
    4. <package_root>/ciris_templates/ (bundled)

    Returns:
        Path to template directory
    """
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
