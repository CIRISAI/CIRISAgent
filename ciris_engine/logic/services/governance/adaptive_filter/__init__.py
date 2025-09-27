"""
CIRIS Adaptive Filter Service Module

Provides intelligent message filtering with graph memory persistence,
user trust tracking, self-configuration capabilities, and privacy-preserving
moderation for anonymous users.

This module implements universal message filtering across all CIRIS adapters
(Discord, CLI, API) with attention economy management and ethical AI principles.
"""

from .service import AdaptiveFilterService

__all__ = ["AdaptiveFilterService"]
