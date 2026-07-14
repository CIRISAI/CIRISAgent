"""
CIRIS Agent Secrets Management System

Provides secure detection, storage, and access control for sensitive information.
All secrets are encrypted at rest (by persist's `secrets_*` substrate) and
access is audited.

Key components:
- SecretsFilter: Detects and filters secrets from content (agent-owned)
- SecretsService: Typed facade coordinating detection + persist-backed storage
"""

from ciris_engine.schemas.secrets.core import DetectedSecret, SecretAccessLog, SecretPattern, SecretRecord

from .filter import SecretsFilter
from .service import SecretsService

__all__ = [
    "SecretsFilter",
    "SecretPattern",
    "DetectedSecret",
    "SecretRecord",
    "SecretAccessLog",
    "SecretsService",
]
