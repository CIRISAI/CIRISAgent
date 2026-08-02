"""
CIRIS Agent Secrets Management System

Provides secure detection, storage, and access control for sensitive information.
Detection, encryption-at-rest, decapsulation, and audit are all owned by
persist's `secrets_*` substrate (2.9.7 DRY purge, wave 2 — the Python
`SecretsFilter` duplicate was deleted; seed the substrate filter catalog
via `SecretsService.update_filter_config`).

Key components:
- SecretsService: Typed facade driving persist's secrets substrate
"""

from ciris_engine.schemas.secrets.core import DetectedSecret, SecretAccessLog, SecretPattern, SecretRecord

from .service import SecretsService

__all__ = [
    "SecretPattern",
    "DetectedSecret",
    "SecretRecord",
    "SecretAccessLog",
    "SecretsService",
]
