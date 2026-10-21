"""Type definitions for attestation module."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PythonHashesWrapper:
    """Wrapper for Python module hashes loaded from startup file.

    CIRISVerify v0.9.7+ expects an object with attributes, not a dict.
    This class provides attribute access for the hash data.
    """

    total_hash: str = ""
    module_hashes: Dict[str, str] = field(default_factory=dict)
    module_count: int = 0
    agent_version: str = ""
    computed_at: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PythonHashesWrapper":
        """Create from dictionary loaded from JSON."""
        return cls(
            total_hash=data.get("total_hash", ""),
            module_hashes=data.get("module_hashes", {}),
            module_count=data.get("modules_hashed", 0),
            agent_version=data.get("agent_version", ""),
            computed_at=data.get("computed_at", 0.0),
        )


@dataclass
class VerifyThreadResult:
    """Result container for verification thread.

    Used to pass results back from the verification thread.
    """

    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if verification succeeded."""
        return self.error is None and self.result is not None
