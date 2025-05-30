import json
import os
import asyncio
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from ..schemas.config_schemas_v1 import AppConfig

# --- Global Configuration Instance ---
# This will hold the loaded application configuration.
# It's initialized to None and populated by load_config() or get_config().
_app_config: Optional[AppConfig] = None

# --- Configuration File ---
DEFAULT_CONFIG_FILENAME = "ciris_engine_config.json"

def get_project_root_for_config() -> Path:
    """
    Determines a root directory for placing/finding the config file.
    This assumes 'config_manager.py' is in 'cirisengine/core/'.
    It will place 'ciris_engine_config.json' in the 'cirisengine/' directory.
    Adjust if your project structure or desired config location is different.
    """
    # Path(__file__) is cirisengine/core/config_manager.py
    # .parent is cirisengine/core/
    # .parent.parent would be the directory containing cirisengine/
    # For now, let's assume the config file lives alongside the cirisengine package,
    # or inside it. Let's target inside `cirisengine/` for simplicity.
    return Path(__file__).resolve().parent.parent # Should point to 'cirisengine' directory

def get_config_file_path(filename: str = DEFAULT_CONFIG_FILENAME) -> Path:
    """Returns the default path for the configuration file."""
    return get_project_root_for_config() / filename

def load_config_from_file(config_file_path: Optional[Path] = None, create_if_not_exists: bool = False) -> AppConfig:
    """
    Loads the application configuration from a JSON file.
    If config_file_path is None, uses the default path.
    If the file doesn't exist:
        - If create_if_not_exists is True, creates it with default values.
        - Otherwise, returns an AppConfig instance with default values.
    The loaded/defaulted config is stored in the global _app_config.
    """
    global _app_config

    actual_path = config_file_path or get_config_file_path()

    if actual_path.exists() and actual_path.is_file():
        try:
            with open(actual_path, 'r') as f:
                config_data = json.load(f)
            # Inject discord_channel_id from env if present
            discord_channel_id_env = os.getenv("DISCORD_CHANNEL_ID")
            if discord_channel_id_env:
                config_data["discord_channel_id"] = discord_channel_id_env
            _app_config = AppConfig(**config_data)
            # print(f"Configuration loaded from {actual_path}") # For debugging
            return _app_config
        except Exception as e:
            # print(f"Error loading configuration from {actual_path}: {e}. Using default configuration.") # For debugging
            _app_config = AppConfig() # Instantiate with defaults
            return _app_config
    else:
        _app_config = AppConfig()
        # Inject discord_channel_id from env if present
        discord_channel_id_env = os.getenv("DISCORD_CHANNEL_ID")
        if discord_channel_id_env:
            _app_config.discord_channel_id = discord_channel_id_env
        if create_if_not_exists:
            # print(f"Configuration file not found at {actual_path}. Creating with default values.") # For debugging
            try:
                save_config_to_json(_app_config, actual_path)
            except Exception as e:
                # print(f"Error creating default configuration file at {actual_path}: {e}") # For debugging
                pass # Continue with in-memory default config
        # else:
            # print(f"Configuration file not found at {actual_path}. Using default configuration.") # For debugging
        return _app_config

def get_config() -> AppConfig:
    """
    Returns the current application configuration.
    Loads it with default settings (or from file if exists) if it hasn't been loaded yet.
    """
    if _app_config is None:
        return load_config_from_file() # Uses default path, does not create file by default
    return _app_config

def get_config_as_json_str(indent: Optional[int] = 2) -> str:
    """
    Returns the current application configuration as a JSON formatted string.
    """
    config = get_config()
    return config.model_dump_json(indent=indent)

def save_config_to_json(config: AppConfig, config_file_path: Optional[Path] = None) -> None:
    """
    Saves the given AppConfig instance to a JSON file.
    Uses default path if config_file_path is None.
    """
    actual_path = config_file_path or get_config_file_path()
    try:
        actual_path.parent.mkdir(parents=True, exist_ok=True)
        with open(actual_path, 'w') as f:
            # Use model_dump for Pydantic v2, or .dict() for v1
            # json.dump(config.model_dump(mode='json'), f, indent=2) # Pydantic v2
            f.write(config.model_dump_json(indent=2)) # Simpler, works for both if indent is desired
        # print(f"Configuration saved to {actual_path}") # For debugging
    except Exception as e:
        # print(f"Error saving configuration to {actual_path}: {e}") # For debugging
        raise # Re-raise the exception as saving might be critical


async def load_config_from_file_async(config_file_path: Optional[Path] = None, create_if_not_exists: bool = False) -> AppConfig:
    """Asynchronous wrapper around ``load_config_from_file`` using ``asyncio.to_thread``."""
    return await asyncio.to_thread(load_config_from_file, config_file_path, create_if_not_exists)


async def get_config_async() -> AppConfig:
    """Asynchronously retrieve the current application configuration."""
    return await asyncio.to_thread(get_config)


async def save_config_to_json_async(config: AppConfig, config_file_path: Optional[Path] = None) -> None:
    """Asynchronous wrapper around ``save_config_to_json``."""
    await asyncio.to_thread(save_config_to_json, config, config_file_path)

# --- Utility for Database Path Construction ---
def get_sqlite_db_full_path() -> str:
    """
    Constructs the full, absolute path to the SQLite database file
    based on the current configuration.
    """
    config = get_config()
    project_root = get_project_root_for_config() # Assumes 'cirisengine' is the reference
    # Use config.database instead of config.db
    db_path = project_root / config.database.data_directory / config.database.db_filename
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path.resolve())

def get_graph_memory_full_path() -> str:
    """
    Constructs the full, absolute path to the graph memory pickle file
    based on the current configuration.
    """
    config = get_config()
    project_root = get_project_root_for_config()
    graph_path = project_root / config.database.data_directory / config.database.graph_memory_filename
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    return str(graph_path.resolve())

# Example of how to initialize and potentially create a default config file at startup.
# This line could be called explicitly in the main application entry point.
# load_config(create_if_not_exists=True)
