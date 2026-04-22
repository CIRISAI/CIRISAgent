from __future__ import annotations

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


def get_env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a variable with environment variable overriding .env values."""
    if not _ENV_LOADED:
        load_env_file()
    val = os.getenv(name)
    if val is not None:
        return val
    if name in _ENV_VALUES:
        return _ENV_VALUES[name]
    return default
