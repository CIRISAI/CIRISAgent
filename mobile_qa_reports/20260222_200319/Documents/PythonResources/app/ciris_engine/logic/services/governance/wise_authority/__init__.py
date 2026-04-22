"""
Wise Authority Service - Authorization and Guidance Module

This module handles:
- Authorization checks (what can you do?)
- Decision deferrals to humans
- Guidance for complex situations
- Permission management

Authentication (who are you?) is handled by AuthenticationService.
"""

from .service import WiseAuthorityService

__all__ = ["WiseAuthorityService"]
