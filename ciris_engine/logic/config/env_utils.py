from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Optional

from dotenv import dotenv_values

_ENV_VALUES: Dict[str, str] = {}
_ENV_LOADED = False
_ENV_PATH: Optional[Path] = None


def load_env_file(path: Path | str = Path(".env"), *, force: bool = False) -> None:
    global _ENV_LOADED, _ENV_VALUES, _ENV_PATH
    if _ENV_LOADED and not force and Path(path) == _ENV_PATH:
        return
    try:
        env_path = Path(path)
        if env_path.exists():
            _ENV_VALUES = {k: v for k, v in dotenv_values(env_path).items() if v is not None}
        else:
            _ENV_VALUES = {}
    except Exception:
        _ENV_VALUES = {}
    _ENV_LOADED = True
    _ENV_PATH = Path(path)


#: Config keys whose value names a FILESYSTEM PATH. Only these are repaired — a
#: control character cannot legally appear in one (WinError 123 is the OS saying
#: so), whereas in arbitrary config it might be intentional.
logger = logging.getLogger(__name__)

_PATH_VALUED_ENV_VARS = frozenset(
    {
        "CIRIS_DB_PATH",
        "CIRIS_SECRETS_DB_PATH",
        "CIRIS_AUDIT_DB_PATH",
        "CIRIS_DATA_DIR",
        "CIRIS_HOME",
        "CIRIS_LOG_DIR",
        "CIRIS_AGENT_ROOT",
        "CIRIS_LICENSED_PACKAGE_PATH",
        "CIRIS_MODULE_PATH",
        "CIRIS_VERIFY_BINARY_PATH",
    }
)


def get_env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a variable with environment variable overriding .env values.

    Path values are repaired on the way out. Fixing the WRITERS (2.9.19) stops
    NEW corruption and does nothing for the .env files already on disk — a user
    upgraded to that release and hit the identical WinError 123, because his file
    had been poisoned by an earlier version. Repairing here means the upgrade
    alone is enough: no manual .env surgery, no reinstall.
    """
    if not _ENV_LOADED:
        load_env_file()
    val = os.getenv(name)
    if val is None and name in _ENV_VALUES:
        val = _ENV_VALUES[name]
    if val is None:
        return default

    if name in _PATH_VALUED_ENV_VARS:
        from ciris_engine.logic.utils.env_file import repair_dotenv_escapes

        repaired = repair_dotenv_escapes(val)
        if repaired != val:
            # Name the VARIABLE, never the value — the path is user data, and
            # the corrupted form has already travelled through enough logs.
            logger.warning(
                "[ENV] %s contained a control character from .env escape processing and was "
                "repaired in memory. Re-run setup, or rewrite that line with doubled "
                "backslashes or forward slashes, to fix the file itself.",
                name,
            )
        return repaired
    return val
