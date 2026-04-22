"""
CIRIS Agent Secrets Management System

Provides secure detection, storage, and access control for sensitive information.
All secrets are encrypted at rest and access is audited.

Key components:
- SecretsFilter: Detects and filters secrets from content
- SecretsStore: Encrypted storage and retrieval of secrets
- SecretsService: Main service coordinating secrets management
- SecretTools: Agent tools for managing secrets
"""

from ciris_engine.schemas.secrets.core import DetectedSecret, SecretAccessLog, SecretPattern, SecretRecord

from .encryption import SecretsEncryption
from .filter import SecretsFilter
from .service import SecretsService
from .store import SecretsStore

__all__ = [
    "SecretsFilter",
    "SecretPattern",
    "DetectedSecret",
    "SecretsStore",
    "SecretsEncryption",
    "SecretRecord",
    "SecretAccessLog",
    "SecretsService",
]
