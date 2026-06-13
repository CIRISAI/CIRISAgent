"""Fixtures for accord_metrics adapter tests.

These fixtures ensure tests don't hang on cryptographic key initialization.
"""

from unittest.mock import MagicMock, patch

import pytest


class MockUnifiedKey:
    """Mock for UnifiedSigningKey that doesn't require actual crypto."""

    def __init__(self):
        self.key_id = "mock-key-id"
        self._initialized = True

    def initialize(self):
        pass

    def sign(self, data: bytes) -> bytes:
        return b"mock_signature"


@pytest.fixture(autouse=True)
def mock_unified_signing_key():
    """Mock the unified signing key to prevent blocking on CIRISVerify vault.

    _compute_instance_hash / get_metrics load the unified signing key, which
    can hang if the CIRISVerify vault isn't available. This fixture mocks it
    out; the stub has no public_key_bytes, so the service exercises the
    fallback agent_id hashing path. (Trace SIGNING moved to the lens-core
    substrate via engine.signer() in the 2.9.6 fold — CIRISAgent#866.)
    """
    with patch(
        "ciris_engine.logic.audit.signing_protocol.get_unified_signing_key",
        return_value=MockUnifiedKey(),
    ):
        yield
