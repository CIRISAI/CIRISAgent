#!/usr/bin/env python3
"""
Standalone CIRISManager API runner for production.
Runs only the API without container management or watchdog.
"""
import asyncio
import uvicorn
from fastapi import FastAPI
import sys
import os

# Add parent directory to path to import ciris_manager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ciris_manager.api.routes import create_routes
from ciris_manager.manager import CIRISManager

# Create a minimal manager instance for the API
# Load config from environment variable if set
config_path = os.environ.get('CIRIS_MANAGER_CONFIG')
if config_path:
    from ciris_manager.config.settings import CIRISManagerConfig
    config = CIRISManagerConfig.from_file(config_path)
    manager = CIRISManager(config)
else:
    manager = CIRISManager()

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