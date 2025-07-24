#!/usr/bin/env python3
"""
Local CIRISManager API runner that uses local config.
"""
import asyncio
import uvicorn
from fastapi import FastAPI
import sys
import os
from pathlib import Path

# Add parent directory to path to import ciris_manager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ciris_manager.api.routes import create_routes
from ciris_manager.manager import CIRISManager
from ciris_manager.config.settings import CIRISManagerConfig

# Load config from local path
config_path = os.path.expanduser("~/.config/ciris-manager/config.yml")
config = CIRISManagerConfig.from_file(config_path)

# Create manager with our config
manager = CIRISManager(config=config)

app = FastAPI(title="CIRISManager API", version="1.0.0")
router = create_routes(manager)
app.include_router(router, prefix="/manager/v1")

if __name__ == "__main__":
    # Run the API server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8888,
        log_level="info"
    )