"""
Tests for covenant verification.

Tests signature verification against trusted authorities.
"""

import time
from unittest.mock import MagicMock, patch

import pytest


class TestTrustedAuthority:
    """Tests for TrustedAuthority class."""

    def test_authority_creation(self):
        """Should create authority with correct hash."""
        from ciris_engine.logic.covenant.verifier import TrustedAuthority

        auth = TrustedAuthority(
            wa_id="wa-2025-06-14-ROOT00",
            public_key=b"x" * 32,
            role="ROOT",
        )
        assert auth.wa_id == "wa-2025-06-14-ROOT00"
        assert len(auth.wa_id_hash) == 8
        assert auth.role == "ROOT"

    def test_authority_hash_deterministic(self):
        """Same WA ID should produce same hash."""
        from ciris_engine.logic.covenant.verifier import TrustedAuthority

        auth1 = TrustedAuthority("wa-test", b"x" * 32)
        auth2 = TrustedAuthority("wa-test", b"y" * 32)
        assert auth1.wa_id_hash == auth2.wa_id_hash


class TestVerifyCovenant:
    """Tests for verify_covenant function."""

    def test_verify_valid_covenant(self):
        """Should verify valid covenant."""
        from ciris_engine.logic.covenant.verifier import TrustedAuthority, verify_covenant
        from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
        from tools.security.covenant_keygen import derive_covenant_keypair

        # Generate keypair
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, public_bytes, _ = derive_covenant_keypair(mnemonic)

        # Create payload
        payload = create_covenant_payload(
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-test-001",
            private_key_bytes=private_bytes,
        )

        # Create authority
        authority = TrustedAuthority(
            wa_id="wa-test-001",
            public_key=public_bytes,
            role="ROOT",
        )

        result = verify_covenant(payload, [authority])
        assert result.valid
        assert result.wa_id == "wa-test-001"
        assert result.wa_role == "ROOT"

    def test_verify_expired_timestamp(self):
        """Should reject expired timestamp."""
        from ciris_engine.logic.covenant.verifier import TrustedAuthority, verify_covenant
        from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
        from tools.security.covenant_keygen import derive_covenant_keypair

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, public_bytes, _ = derive_covenant_keypair(mnemonic)

        # Create payload with old timestamp (outside 24-hour window)
        old_timestamp = int(time.time()) - 90000  # 25 hours ago
        payload = create_covenant_payload(
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-test-001",
            private_key_bytes=private_bytes,
            timestamp=old_timestamp,
        )

        authority = TrustedAuthority("wa-test-001", public_bytes, "ROOT")

        result = verify_covenant(payload, [authority])
        assert not result.valid
        assert "Timestamp" in result.rejection_reason

    def test_verify_wrong_signature(self):
        """Should reject wrong signature."""
        from ciris_engine.logic.covenant.verifier import TrustedAuthority, verify_covenant
        from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
        from tools.security.covenant_keygen import derive_covenant_keypair

        # Two different keypairs
        mnemonic1 = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        mnemonic2 = "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong"
        private1, _, _ = derive_covenant_keypair(mnemonic1)
        _, public2, _ = derive_covenant_keypair(mnemonic2)

        # Sign with key1
        payload = create_covenant_payload(
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-test-001",
            private_key_bytes=private1,
        )

        # Verify with key2
        authority = TrustedAuthority("wa-test-001", public2, "ROOT")

        result = verify_covenant(payload, [authority])
        assert not result.valid
        assert "No matching" in result.rejection_reason

    def test_verify_no_matching_authority(self):
        """Should reject if no matching WA ID."""
        from ciris_engine.logic.covenant.verifier import TrustedAuthority, verify_covenant
        from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
        from tools.security.covenant_keygen import derive_covenant_keypair

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, public_bytes, _ = derive_covenant_keypair(mnemonic)

        # Payload for wa-test-001
        payload = create_covenant_payload(
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-test-001",
            private_key_bytes=private_bytes,
        )

        # Authority for different WA ID
        authority = TrustedAuthority("wa-test-002", public_bytes, "ROOT")

        result = verify_covenant(payload, [authority])
        assert not result.valid

    def test_verify_multiple_authorities(self):
        """Should check multiple authorities."""
        from ciris_engine.logic.covenant.verifier import TrustedAuthority, verify_covenant
        from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
        from tools.security.covenant_keygen import derive_covenant_keypair

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, public_bytes, _ = derive_covenant_keypair(mnemonic)

        payload = create_covenant_payload(
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-test-002",
            private_key_bytes=private_bytes,
        )

        # Multiple authorities, one matching
        authorities = [
            TrustedAuthority("wa-test-001", b"x" * 32, "ROOT"),
            TrustedAuthority("wa-test-002", public_bytes, "ROOT"),  # Match
            TrustedAuthority("wa-test-003", b"y" * 32, "ROOT"),
        ]

        result = verify_covenant(payload, authorities)
        assert result.valid
        assert result.wa_id == "wa-test-002"


class TestLoadSeedKey:
    """Tests for seed key loading."""

    def test_load_seed_key_from_file(self):
        """Should load seed key from seed/root_pub.json."""
        from ciris_engine.logic.covenant.verifier import load_seed_key

        result = load_seed_key()
        # If the seed file exists in the repo
        if result:
            wa_id, pubkey, role = result
            assert "wa-" in wa_id
            assert len(pubkey) > 0
            assert role.upper() in ["ROOT", "AUTHORITY"]


class TestCovenantVerifierClass:
    """Tests for CovenantVerifier class."""

    def test_verifier_auto_loads_authorities(self):
        """Should auto-load authorities on init."""
        # Mock SIGKILL to prevent test from dying if no authorities
        with patch("os.kill"):
            from ciris_engine.logic.covenant.verifier import CovenantVerifier

            verifier = CovenantVerifier(auto_load_seed=True)
            # Should have at least the hardcoded authority
            assert verifier.authority_count >= 1

    def test_verifier_add_authority(self):
        """Should add authority."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant.verifier import CovenantVerifier

            verifier = CovenantVerifier(auto_load_seed=False)
            # Manually add to avoid SIGKILL
            verifier._authorities = []

            result = verifier.add_authority(
                wa_id="wa-test-001",
                public_key="7Bp-e4M4M-eLzwiwuoMLb4aoKZJuXDsQ8NamVJzveAk",
                role="ROOT",
            )
            assert result
            assert verifier.authority_count == 1

    def test_verifier_add_authority_hex(self):
        """Should accept hex public key."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant.verifier import CovenantVerifier

            verifier = CovenantVerifier(auto_load_seed=False)
            verifier._authorities = []

            hex_key = "ec1a7e7b833833e78bcf08b0ba830b6f86a829926e5c3b10f0d6a6549cef7809"
            result = verifier.add_authority("wa-test", hex_key, "ROOT")
            assert result

    def test_verifier_remove_authority(self):
        """Should remove authority."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant.verifier import CovenantVerifier

            verifier = CovenantVerifier(auto_load_seed=False)
            verifier._authorities = []

            verifier.add_authority("wa-test-001", b"x" * 32, "ROOT")
            assert verifier.authority_count == 1

            result = verifier.remove_authority("wa-test-001")
            assert result
            assert verifier.authority_count == 0

    def test_verifier_remove_nonexistent(self):
        """Should return False for nonexistent authority."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant.verifier import CovenantVerifier

            verifier = CovenantVerifier(auto_load_seed=False)
            verifier._authorities = []

            result = verifier.remove_authority("wa-nonexistent")
            assert not result

    def test_verifier_update_existing(self):
        """Should update existing authority."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant.verifier import CovenantVerifier

            verifier = CovenantVerifier(auto_load_seed=False)
            verifier._authorities = []

            verifier.add_authority("wa-test", b"x" * 32, "AUTHORITY")
            verifier.add_authority("wa-test", b"y" * 32, "ROOT")

            assert verifier.authority_count == 1
            assert verifier._authorities[0].role == "ROOT"

    def test_verifier_load_from_config(self):
        """Should load from legacy config format."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant.verifier import CovenantVerifier

            verifier = CovenantVerifier(auto_load_seed=False)
            verifier._authorities = []

            keys = [
                "7Bp-e4M4M-eLzwiwuoMLb4aoKZJuXDsQ8NamVJzveAk",
            ]
            loaded = verifier.load_from_config(keys)
            assert loaded == 1

    def test_verifier_counts(self):
        """Should track verification counts."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant.verifier import CovenantVerifier
            from ciris_engine.schemas.covenant import (
                CovenantCommandType,
                CovenantMessage,
                CovenantPayload,
                create_covenant_payload,
            )
            from tools.security.covenant_keygen import derive_covenant_keypair

            verifier = CovenantVerifier(auto_load_seed=False)
            verifier._authorities = []

            # Add authority
            mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
            private_bytes, public_bytes, _ = derive_covenant_keypair(mnemonic)
            verifier.add_authority("wa-test", public_bytes, "ROOT")

            # Create valid covenant
            payload = create_covenant_payload(
                command=CovenantCommandType.SHUTDOWN_NOW,
                wa_id="wa-test",
                private_key_bytes=private_bytes,
            )
            message = CovenantMessage(
                source_text="test",
                source_channel="test",
                payload=payload,
                extraction_confidence=1.0,
                timestamp_valid=True,
            )

            # Verify
            result = verifier.verify(message)
            assert result.valid
            assert verifier.verification_count == 1
            assert verifier.valid_count == 1

    def test_verifier_list_authorities(self):
        """Should list authorities without exposing keys."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant.verifier import CovenantVerifier

            verifier = CovenantVerifier(auto_load_seed=False)
            verifier._authorities = []

            verifier.add_authority("wa-test-001", b"x" * 32, "ROOT")
            verifier.add_authority("wa-test-002", b"y" * 32, "AUTHORITY")

            authorities = verifier.list_authorities()
            assert len(authorities) == 2
            assert authorities[0]["wa_id"] == "wa-test-001"
            assert "public_key" not in authorities[0]  # Key not exposed
