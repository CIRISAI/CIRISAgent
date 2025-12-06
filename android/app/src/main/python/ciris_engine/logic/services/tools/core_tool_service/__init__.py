"""Core Tool Service Module - Provides core system tools (secrets, tickets, guidance)."""

from .service import CoreToolService

# Backwards compatibility alias
SecretsToolService = CoreToolService

__all__ = ["CoreToolService", "SecretsToolService"]
