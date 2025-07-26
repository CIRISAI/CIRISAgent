"""
OAuth authentication for CIRISManager.

This module maintains backward compatibility while using the new
service-based implementation.
"""

import logging
from pathlib import Path
import os

from .auth_routes import create_auth_routes, init_auth_service, get_current_user_dependency
from .auth_service import TokenResponse

logger = logging.getLogger(__name__)

# Backward compatibility - load OAuth config
def load_oauth_config():
    """Load OAuth configuration from file."""
    oauth_path = Path.home() / "shared/oauth/google_oauth_manager.json"
    
    if oauth_path.exists():
        try:
            import json
            with open(oauth_path) as f:
                config = json.load(f)
                
            # Initialize auth service with config
            init_auth_service(
                google_client_id=config.get("client_id"),
                google_client_secret=config.get("client_secret")
            )
            
            logger.info("Loaded Google OAuth configuration for manager")
            return True
        except Exception as e:
            logger.error(f"Failed to load OAuth config: {e}")
    
    # Try environment variables
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    if client_id and client_secret:
        init_auth_service(
            google_client_id=client_id,
            google_client_secret=client_secret
        )
        return True
    
    return False

# Re-export for backward compatibility
__all__ = [
    "create_auth_routes",
    "load_oauth_config", 
    "get_current_user_dependency",
    "TokenResponse"
]