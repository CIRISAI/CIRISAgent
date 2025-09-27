"""
Shutdown Service Module.

Manages graceful shutdown coordination across the system.
"""

from .service import ShutdownService

__all__ = ["ShutdownService"]
