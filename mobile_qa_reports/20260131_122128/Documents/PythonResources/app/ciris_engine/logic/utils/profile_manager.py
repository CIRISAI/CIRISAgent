"""Legacy profile manager - DEPRECATED.

This module is deprecated and should not be used.
Agent identity is now managed through the graph-based identity system.
See ciris_engine/persistence/models/identity.py for the new approach.
"""

import logging

logger = logging.getLogger(__name__)

logger.warning(
    "profile_manager.py is deprecated. "
    "Agent identity is now managed through the graph-based identity system. "
    "See ciris_engine/persistence/models/identity.py"
)
