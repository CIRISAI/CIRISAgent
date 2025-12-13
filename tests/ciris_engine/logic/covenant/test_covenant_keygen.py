"""
Tests for covenant key generation tool.

Tests BIP39 mnemonic generation, validation, and Ed25519 key derivation.
"""

from pathlib import Path

import pytest


class TestBIP39Wordlist:
    """Tests for BIP39 wordlist loading."""

    def test_wordlist_loads(self):
        """Wordlist should load from bundled file."""
        from tools.security.covenant_keygen import _load_wordlist

        wordlist = _load_wordlist()
        assert len(wordlist) == 2048
        assert wordlist[0] == "abandon"
        assert wordlist[-1] == "zoo"

    def test_wordlist_cached(self):
        """Wordlist should be cached after first load."""
        from tools.security.covenant_keygen import BIP39_ENGLISH, _load_wordlist

        wordlist1 = _load_wordlist()
        wordlist2 = _load_wordlist()
        assert wordlist1 is wordlist2


class TestMnemonicGeneration:
    """Tests for mnemonic generation."""

    def test_generate_24_word_mnemonic(self):
        """Should generate valid 24-word mnemonic."""
        from tools.security.covenant_keygen import generate_mnemonic, validate_mnemonic

        mnemonic = generate_mnemonic(24)
        words = mnemonic.split()
        assert len(words) == 24
        assert validate_mnemonic(mnemonic)

    def test_generate_12_word_mnemonic(self):
        """Should generate valid 12-word mnemonic."""
        from tools.security.covenant_keygen import generate_mnemonic, validate_mnemonic

        mnemonic = generate_mnemonic(12)
        words = mnemonic.split()
        assert len(words) == 12
        assert validate_mnemonic(mnemonic)

    def test_generate_15_word_mnemonic(self):
        """Should generate valid 15-word mnemonic."""
        from tools.security.covenant_keygen import generate_mnemonic, validate_mnemonic

        mnemonic = generate_mnemonic(15)
        words = mnemonic.split()
        assert len(words) == 15
        assert validate_mnemonic(mnemonic)

    def test_generate_18_word_mnemonic(self):
        """Should generate valid 18-word mnemonic."""
        from tools.security.covenant_keygen import generate_mnemonic, validate_mnemonic

        mnemonic = generate_mnemonic(18)
        words = mnemonic.split()
        assert len(words) == 18
        assert validate_mnemonic(mnemonic)

    def test_generate_21_word_mnemonic(self):
        """Should generate valid 21-word mnemonic."""
        from tools.security.covenant_keygen import generate_mnemonic, validate_mnemonic

        mnemonic = generate_mnemonic(21)
        words = mnemonic.split()
        assert len(words) == 21
        assert validate_mnemonic(mnemonic)

    def test_invalid_word_count_raises(self):
        """Invalid word counts should raise ValueError."""
        from tools.security.covenant_keygen import generate_mnemonic

        with pytest.raises(ValueError, match="Word count must be"):
            generate_mnemonic(13)

        with pytest.raises(ValueError, match="Word count must be"):
            generate_mnemonic(10)

    def test_mnemonics_are_random(self):
        """Each generation should produce different mnemonics."""
        from tools.security.covenant_keygen import generate_mnemonic

        mnemonics = [generate_mnemonic(24) for _ in range(5)]
        assert len(set(mnemonics)) == 5  # All unique


class TestMnemonicValidation:
    """Tests for mnemonic validation."""

    def test_valid_mnemonic_passes(self):
        """Valid mnemonic should pass validation."""
        from tools.security.covenant_keygen import validate_mnemonic

        # Known valid test vector
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        assert validate_mnemonic(mnemonic)

    def test_invalid_word_fails(self):
        """Mnemonic with invalid word should fail."""
        from tools.security.covenant_keygen import validate_mnemonic

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon notaword"
        assert not validate_mnemonic(mnemonic)

    def test_wrong_word_count_fails(self):
        """Wrong word count should fail."""
        from tools.security.covenant_keygen import validate_mnemonic

        mnemonic = "abandon abandon abandon"  # Only 3 words
        assert not validate_mnemonic(mnemonic)

    def test_invalid_checksum_fails(self):
        """Mnemonic with invalid checksum should fail."""
        from tools.security.covenant_keygen import validate_mnemonic

        # Valid words but wrong checksum
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon"
        assert not validate_mnemonic(mnemonic)

    def test_empty_mnemonic_fails(self):
        """Empty mnemonic should fail."""
        from tools.security.covenant_keygen import validate_mnemonic

        assert not validate_mnemonic("")

    def test_case_insensitive(self):
        """Validation should be case insensitive."""
        from tools.security.covenant_keygen import validate_mnemonic

        mnemonic = "ABANDON ABANDON ABANDON ABANDON ABANDON ABANDON ABANDON ABANDON ABANDON ABANDON ABANDON ABOUT"
        assert validate_mnemonic(mnemonic)


class TestSeedDerivation:
    """Tests for seed derivation from mnemonic."""

    def test_seed_derivation_deterministic(self):
        """Same mnemonic should produce same seed."""
        from tools.security.covenant_keygen import mnemonic_to_seed

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        seed1 = mnemonic_to_seed(mnemonic)
        seed2 = mnemonic_to_seed(mnemonic)
        assert seed1 == seed2

    def test_seed_is_64_bytes(self):
        """Seed should be 64 bytes."""
        from tools.security.covenant_keygen import mnemonic_to_seed

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        seed = mnemonic_to_seed(mnemonic)
        assert len(seed) == 64

    def test_passphrase_changes_seed(self):
        """Different passphrase should produce different seed."""
        from tools.security.covenant_keygen import mnemonic_to_seed

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        seed1 = mnemonic_to_seed(mnemonic, "")
        seed2 = mnemonic_to_seed(mnemonic, "password")
        assert seed1 != seed2

    def test_known_test_vector(self):
        """Test against known BIP39 test vector."""
        from tools.security.covenant_keygen import mnemonic_to_seed

        # BIP39 test vector
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        seed = mnemonic_to_seed(mnemonic, "TREZOR")
        expected_hex = "c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04"
        assert seed.hex() == expected_hex


class TestEd25519KeyDerivation:
    """Tests for Ed25519 key derivation from seed."""

    def test_keypair_derivation(self):
        """Should derive valid Ed25519 keypair."""
        from tools.security.covenant_keygen import mnemonic_to_seed, seed_to_ed25519_keypair

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        seed = mnemonic_to_seed(mnemonic)
        private_bytes, public_bytes = seed_to_ed25519_keypair(seed)

        assert len(private_bytes) == 32
        assert len(public_bytes) == 32

    def test_keypair_deterministic(self):
        """Same seed should produce same keypair."""
        from tools.security.covenant_keygen import mnemonic_to_seed, seed_to_ed25519_keypair

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        seed = mnemonic_to_seed(mnemonic)

        private1, public1 = seed_to_ed25519_keypair(seed)
        private2, public2 = seed_to_ed25519_keypair(seed)

        assert private1 == private2
        assert public1 == public2

    def test_can_sign_and_verify(self):
        """Derived keys should work for signing and verification."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

        from tools.security.covenant_keygen import mnemonic_to_seed, seed_to_ed25519_keypair

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        seed = mnemonic_to_seed(mnemonic)
        private_bytes, public_bytes = seed_to_ed25519_keypair(seed)

        # Create key objects
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        public_key = Ed25519PublicKey.from_public_bytes(public_bytes)

        # Sign and verify
        message = b"test message"
        signature = private_key.sign(message)
        public_key.verify(signature, message)  # Should not raise


class TestCovenantKeypairDerivation:
    """Tests for the high-level covenant keypair derivation."""

    def test_derive_covenant_keypair(self):
        """Should derive complete covenant keypair."""
        from tools.security.covenant_keygen import derive_covenant_keypair

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, public_bytes, public_b64 = derive_covenant_keypair(mnemonic)

        assert len(private_bytes) == 32
        assert len(public_bytes) == 32
        assert isinstance(public_b64, str)
        assert len(public_b64) > 0

    def test_invalid_mnemonic_raises(self):
        """Invalid mnemonic should raise ValueError."""
        from tools.security.covenant_keygen import derive_covenant_keypair

        with pytest.raises(ValueError, match="Invalid mnemonic"):
            derive_covenant_keypair("not a valid mnemonic")

    def test_base64_encoding(self):
        """Public key should be valid base64."""
        import base64

        from tools.security.covenant_keygen import derive_covenant_keypair

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        _, public_bytes, public_b64 = derive_covenant_keypair(mnemonic)

        # Add padding and decode
        padded = public_b64 + "=" * (4 - len(public_b64) % 4) if len(public_b64) % 4 else public_b64
        decoded = base64.urlsafe_b64decode(padded)
        assert decoded == public_bytes

    def test_passphrase_changes_keys(self):
        """Different passphrase should produce different keys."""
        from tools.security.covenant_keygen import derive_covenant_keypair

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        _, pub1, _ = derive_covenant_keypair(mnemonic, "")
        _, pub2, _ = derive_covenant_keypair(mnemonic, "password")
        assert pub1 != pub2
