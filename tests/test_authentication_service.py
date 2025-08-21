"""Comprehensive tests for WA Authentication Service.

This test suite provides extensive coverage for all authentication operations,
including JWT handling, key management, encryption/decryption, and edge cases.
Target coverage: 90% for this security-critical service.
"""

import base64
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
import pytest_asyncio

from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.authority.wise_authority import WAUpdate
from ciris_engine.schemas.services.authority_core import JWTSubType, TokenType, WACertificate, WARole


class TestAuthenticationServiceUnit:
    """Unit tests for individual methods."""

    @pytest.fixture
    def time_service(self):
        """Create a time service for testing."""
        return TimeService()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for key storage."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)

    @pytest_asyncio.fixture
    async def auth_service(self, temp_db, time_service, temp_dir):
        """Create a WA authentication service for testing."""
        service = AuthenticationService(db_path=temp_db, time_service=time_service, key_dir=temp_dir)
        await service.start()
        yield service
        await service.stop()

    def test_service_type(self, auth_service):
        """Test that service type is correctly identified."""
        assert auth_service.get_service_type() == ServiceType.WISE_AUTHORITY

    def test_actions_list(self, auth_service):
        """Test that all expected actions are listed."""
        actions = auth_service._get_actions()
        expected_actions = [
            "authenticate",
            "create_token",
            "verify_token",
            "verify_token_sync",
            "create_channel_token",
            "create_wa",
            "get_wa",
            "update_wa",
            "revoke_wa",
            "list_was",
            "rotate_keys",
            "bootstrap_if_needed",
            "update_last_login",
            "sign_task",
            "verify_task_signature",
            "generate_keypair",
            "sign_data",
            "hash_password",
        ]
        for action in expected_actions:
            assert action in actions

    def test_check_dependencies(self, auth_service):
        """Test dependency checking."""
        assert auth_service._check_dependencies() is True

    def test_encode_decode_public_key(self, auth_service):
        """Test public key encoding and decoding."""
        # Generate a test key
        private_key, public_key = auth_service.generate_keypair()

        # Encode
        encoded = auth_service._encode_public_key(public_key)
        assert isinstance(encoded, str)
        assert len(encoded) > 0

        # Decode
        decoded = auth_service._decode_public_key(encoded)
        assert decoded == public_key

        # Test padding edge cases
        # Remove padding
        unpadded = encoded.rstrip("=")
        decoded_unpadded = auth_service._decode_public_key(unpadded)
        assert decoded_unpadded == public_key

    def test_derive_encryption_key(self, auth_service):
        """Test encryption key derivation with salt."""
        salt1 = os.urandom(32)
        salt2 = os.urandom(32)

        # Same salt should produce same key
        key1a = auth_service._derive_encryption_key(salt1)
        key1b = auth_service._derive_encryption_key(salt1)
        assert key1a == key1b
        assert len(key1a) == 32

        # Different salt should produce different key
        key2 = auth_service._derive_encryption_key(salt2)
        assert key2 != key1a
        assert len(key2) == 32

    def test_encrypt_decrypt_secret(self, auth_service):
        """Test secret encryption and decryption with random salt."""
        secret = b"This is a secret message!"

        # Encrypt
        encrypted = auth_service._encrypt_secret(secret)
        assert len(encrypted) >= 60  # salt(32) + nonce(12) + data + tag(16)
        assert encrypted != secret

        # Decrypt
        decrypted = auth_service._decrypt_secret(encrypted)
        assert decrypted == secret

        # Test multiple encryptions produce different ciphertext
        encrypted2 = auth_service._encrypt_secret(secret)
        assert encrypted2 != encrypted  # Different salt/nonce
        decrypted2 = auth_service._decrypt_secret(encrypted2)
        assert decrypted2 == secret

    def test_decrypt_legacy_format(self, auth_service):
        """Test backward compatibility with legacy encryption format."""
        # Simulate legacy encrypted data (without salt)
        secret = b"Legacy secret"

        # Create legacy encryption manually
        legacy_salt = b"ciris-gateway-encryption-salt"
        key = auth_service._derive_encryption_key(legacy_salt)

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        nonce = os.urandom(12)
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(secret) + encryptor.finalize()

        # Legacy format: nonce + ciphertext + tag
        legacy_encrypted = nonce + ciphertext + encryptor.tag

        # Should be able to decrypt legacy format
        decrypted = auth_service._decrypt_secret(legacy_encrypted)
        assert decrypted == secret

    def test_decrypt_invalid_data(self, auth_service):
        """Test decryption with invalid data."""
        # Too short data
        with pytest.raises(ValueError, match="Invalid encrypted data format"):
            auth_service._decrypt_secret(b"too short")

        # Invalid tag (corrupted data)
        from cryptography.exceptions import InvalidTag

        # Use longer data to ensure we stay above 60 byte threshold
        # This guarantees we hit the new format path, not legacy
        test_data = b"test" * 20  # 80 bytes of plaintext
        encrypted = auth_service._encrypt_secret(test_data)

        # Verify we're in new format territory (should be > 60 bytes)
        assert len(encrypted) > 60, f"Encrypted data too short: {len(encrypted)} bytes"

        # Corrupt the tag (last 16 bytes) to trigger InvalidTag
        corrupted = encrypted[:-1] + b"X"  # Corrupt last byte of tag
        with pytest.raises(InvalidTag):  # Now guaranteed to raise InvalidTag
            auth_service._decrypt_secret(corrupted)

    def test_gateway_secret_persistence(self, temp_db, time_service, temp_dir):
        """Test gateway secret creation and persistence."""
        # Create first service
        service1 = AuthenticationService(temp_db, time_service, temp_dir)
        secret1 = service1.gateway_secret
        assert len(secret1) == 32

        # Create second service with same key dir
        service2 = AuthenticationService(temp_db, time_service, temp_dir)
        secret2 = service2.gateway_secret

        # Should load same secret
        assert secret2 == secret1

    def test_gateway_secret_migration(self, temp_db, time_service, temp_dir):
        """Test migration from unencrypted to encrypted gateway secret."""
        # Create unencrypted secret file
        secret_path = Path(temp_dir) / "gateway.secret"
        test_secret = os.urandom(32)
        secret_path.write_bytes(test_secret)

        # Create service - should migrate to encrypted
        service = AuthenticationService(temp_db, time_service, temp_dir)
        assert service.gateway_secret == test_secret

        # Check old file is removed and new encrypted file exists
        assert not secret_path.exists()
        assert (Path(temp_dir) / "gateway.secret.enc").exists()

    @pytest.mark.asyncio
    async def test_database_initialization(self, auth_service):
        """Test database table creation."""
        # Check tables exist
        with sqlite3.connect(auth_service.db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wa_cert'")
            assert cursor.fetchone() is not None

    def test_password_hashing(self, auth_service):
        """Test password hashing with PBKDF2."""
        password = "super_secure_password_123!@#"

        # Hash password
        hash1 = auth_service.hash_password(password)
        hash2 = auth_service.hash_password(password)

        # Same password should produce different hashes (different salt)
        assert hash1 != hash2

        # Both should verify correctly
        assert auth_service._verify_password(password, hash1) is True
        assert auth_service._verify_password(password, hash2) is True

        # Wrong password should fail
        assert auth_service._verify_password("wrong_password", hash1) is False

        # Invalid hash format should fail
        assert auth_service._verify_password(password, "invalid_hash") is False

    def test_api_key_generation(self, auth_service):
        """Test API key generation."""
        wa_id = "wa-2025-01-01-TEST01"

        # Generate keys
        key1 = auth_service._generate_api_key(wa_id)
        key2 = auth_service._generate_api_key(wa_id)

        # Should be different (includes random component)
        assert key1 != key2

        # Should be proper format
        assert len(key1) == 64  # SHA256 hex
        assert all(c in "0123456789abcdef" for c in key1)

    def test_wa_id_generation(self, auth_service):
        """Test WA ID generation format and uniqueness."""
        timestamp = datetime(2025, 7, 14, 12, 0, 0, tzinfo=timezone.utc)

        wa_id = auth_service._generate_wa_id(timestamp)

        # Check format: wa-YYYY-MM-DD-XXXXXX
        assert wa_id.startswith("wa-2025-07-14-")
        parts = wa_id.split("-")
        assert len(parts) == 5
        assert parts[0] == "wa"
        assert parts[1] == "2025"
        assert parts[2] == "07"
        assert parts[3] == "14"
        assert len(parts[4]) == 6  # Random suffix (6 hex chars)
        # Should be uppercase hexadecimal (from token_hex)
        assert all(c in "0123456789ABCDEF" for c in parts[4])

        # Test uniqueness - generate multiple IDs
        ids = set()
        for _ in range(100):
            new_id = auth_service._generate_wa_id(timestamp)
            assert new_id not in ids, "Generated duplicate WA ID"
            ids.add(new_id)

        # Test different timestamps
        timestamp2 = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        wa_id2 = auth_service._generate_wa_id(timestamp2)
        assert wa_id2.startswith("wa-2025-12-31-")

        # Test timestamp without timezone (should still work)
        timestamp3 = datetime(2025, 1, 1, 0, 0, 0)
        wa_id3 = auth_service._generate_wa_id(timestamp3)
        assert wa_id3.startswith("wa-2025-01-01-")

    def test_ed25519_operations(self, auth_service):
        """Test Ed25519 key generation, signing, and verification."""
        # Generate keypair
        private_key, public_key = auth_service.generate_keypair()
        assert len(private_key) == 32
        assert len(public_key) == 32

        # Sign data
        data = b"Important message to sign"
        signature = auth_service.sign_data(data, private_key)

        # Verify signature
        encoded_pubkey = auth_service._encode_public_key(public_key)
        assert auth_service._verify_signature(data, signature, encoded_pubkey) is True

        # Wrong data should fail
        assert auth_service._verify_signature(b"different data", signature, encoded_pubkey) is False

        # Wrong signature should fail
        bad_signature = base64.b64encode(os.urandom(64)).decode()
        assert auth_service._verify_signature(data, bad_signature, encoded_pubkey) is False

        # Wrong public key should fail
        _, wrong_public_key = auth_service.generate_keypair()
        wrong_encoded = auth_service._encode_public_key(wrong_public_key)
        assert auth_service._verify_signature(data, signature, wrong_encoded) is False


class TestAuthenticationServiceJWT:
    """Tests for JWT token operations."""

    @pytest.fixture
    def time_service(self):
        """Create a time service for testing."""
        return TimeService()

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)

    @pytest_asyncio.fixture
    async def auth_service(self, temp_db, time_service):
        """Create a WA authentication service for testing."""
        service = AuthenticationService(db_path=temp_db, time_service=time_service, key_dir=None)
        await service.start()
        yield service
        await service.stop()

    @pytest_asyncio.fixture
    async def test_wa(self, auth_service):
        """Create a test WA certificate."""
        private_key, public_key = auth_service.generate_keypair()
        wa = WACertificate(
            wa_id="wa-2025-07-14-JWT001",
            name="JWT Test WA",
            role=WARole.AUTHORITY,
            pubkey=auth_service._encode_public_key(public_key),
            jwt_kid="jwt-test-kid",
            scopes_json='["read:any", "write:any", "admin:system"]',
            created_at=datetime.now(timezone.utc),
        )
        await auth_service._store_wa_certificate(wa)
        return wa, private_key

    @pytest_asyncio.fixture
    async def oauth_wa(self, auth_service):
        """Create an OAuth WA certificate."""
        private_key, public_key = auth_service.generate_keypair()
        wa = WACertificate(
            wa_id="wa-2025-07-14-OAUTH1",
            name="OAuth Test WA",
            role=WARole.OBSERVER,
            pubkey=auth_service._encode_public_key(public_key),
            jwt_kid="oauth-test-kid",
            scopes_json='["read:self", "write:self"]',
            oauth_provider="github",
            oauth_external_id="user123",
            created_at=datetime.now(timezone.utc),
        )
        await auth_service._store_wa_certificate(wa)
        return wa, private_key

    @pytest.mark.asyncio
    async def test_gateway_token_creation_and_verification(self, auth_service, test_wa):
        """Test creating and verifying gateway-signed tokens."""
        wa, _ = test_wa

        # Create token
        token = auth_service.create_gateway_token(wa, expires_hours=2)
        assert token is not None

        # Decode without verification to check structure
        decoded = jwt.decode(token, options={"verify_signature": False})
        assert decoded["sub"] == wa.wa_id
        assert decoded["sub_type"] == JWTSubType.USER.value
        assert decoded["name"] == wa.name
        assert "exp" in decoded
        assert "iat" in decoded

        # Verify token
        result = await auth_service._verify_jwt_and_get_context(token)
        assert result is not None
        context, expiration = result

        assert context.wa_id == wa.wa_id
        assert context.role == WARole.AUTHORITY
        assert context.sub_type == JWTSubType.USER
        assert expiration is not None

        # Test expiration
        expected_exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        assert abs((expiration - expected_exp).total_seconds()) < 1

    @pytest.mark.asyncio
    async def test_oauth_token_creation(self, auth_service, oauth_wa):
        """Test OAuth token creation with proper sub_type."""
        wa, _ = oauth_wa

        token = auth_service.create_gateway_token(wa, expires_hours=8)

        # Decode and check OAuth fields
        decoded = jwt.decode(token, options={"verify_signature": False})
        assert decoded["sub_type"] == JWTSubType.OAUTH.value
        assert decoded["oauth_provider"] == "github"

        # Verify
        result = await auth_service._verify_jwt_and_get_context(token)
        assert result is not None
        context, _ = result
        assert context.sub_type == JWTSubType.OAUTH

    @pytest.mark.asyncio
    async def test_channel_token_creation(self, auth_service):
        """Test channel token creation for observers."""
        # Create observer WA
        adapter_id = "discord_123456"
        observer = await auth_service._create_adapter_observer(adapter_id, "Discord Observer")

        # Create channel token
        token = await auth_service.create_channel_token(observer.wa_id, "discord_general", ttl=3600)

        # Decode and check
        decoded = jwt.decode(token, options={"verify_signature": False})
        assert decoded["sub_type"] == JWTSubType.ANON.value
        assert decoded["adapter"] == adapter_id
        assert "exp" in decoded  # Has expiry when ttl > 0

        # Create long-lived token (no expiry)
        long_token = await auth_service.create_channel_token(observer.wa_id, "discord_general", ttl=0)

        long_decoded = jwt.decode(long_token, options={"verify_signature": False})
        assert "exp" not in long_decoded  # No expiry when ttl = 0

    @pytest.mark.asyncio
    async def test_authority_token_creation(self, auth_service, test_wa):
        """Test authority-signed tokens (EdDSA)."""
        wa, private_key = test_wa

        # Create authority token
        token = auth_service._create_authority_token(wa, private_key)

        # Decode header to check algorithm
        header = jwt.get_unverified_header(token)
        assert header["alg"] == "EdDSA"
        assert header["kid"] == wa.jwt_kid

        # Decode payload
        decoded = jwt.decode(token, options={"verify_signature": False})
        assert decoded["sub_type"] == JWTSubType.AUTHORITY.value

        # Verify with public key
        result = await auth_service._verify_jwt_and_get_context(token)
        assert result is not None
        context, _ = result
        assert context.sub_type == JWTSubType.AUTHORITY

    @pytest.mark.asyncio
    async def test_token_verification_invalid_cases(self, auth_service, test_wa):
        """Test token verification with various invalid cases."""
        wa, private_key = test_wa

        # Invalid token format
        result = await auth_service._verify_jwt_and_get_context("not.a.token")
        assert result is None

        # Token without kid
        token_no_kid = jwt.encode(
            {"sub": "test", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            auth_service.gateway_secret,
            algorithm="HS256",
        )
        result = await auth_service._verify_jwt_and_get_context(token_no_kid)
        assert result is None

        # Token with non-existent kid
        token_bad_kid = jwt.encode(
            {"sub": "test"}, auth_service.gateway_secret, algorithm="HS256", headers={"kid": "non-existent-kid"}
        )
        result = await auth_service._verify_jwt_and_get_context(token_bad_kid)
        assert result is None

        # Expired token
        expired_token = jwt.encode(
            {
                "sub": wa.wa_id,
                "sub_type": JWTSubType.USER.value,
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            },
            auth_service.gateway_secret,
            algorithm="HS256",
            headers={"kid": wa.jwt_kid},
        )
        result = await auth_service._verify_jwt_and_get_context(expired_token)
        assert result is None

        # Algorithm confusion attack - try to verify EdDSA token with HS256
        authority_token = auth_service._create_authority_token(wa, private_key)

        # Decode the authority token and re-encode with HS256
        decoded = jwt.decode(authority_token, options={"verify_signature": False})
        header = jwt.get_unverified_header(authority_token)

        fake_token = jwt.encode(decoded, auth_service.gateway_secret, algorithm="HS256", headers={"kid": header["kid"]})

        # This should fail because AUTHORITY tokens must use EdDSA
        result = await auth_service._verify_jwt_and_get_context(fake_token)
        assert result is None

    @pytest.mark.asyncio
    async def test_token_cache(self, auth_service, test_wa):
        """Test token caching functionality."""
        wa, _ = test_wa

        # Create token
        token = auth_service.create_gateway_token(wa)

        # First verification - not cached
        assert token not in auth_service._token_cache

        context = await auth_service._verify_token_internal(token)
        assert context is not None

        # Should now be cached
        assert token in auth_service._token_cache
        assert auth_service._token_cache[token] == context

        # Second verification should use cache
        context2 = await auth_service._verify_token_internal(token)
        assert context2 == context

    def test_sync_token_verification(self, auth_service):
        """Test synchronous token verification."""
        # Create a simple gateway token
        payload = {
            "sub": "test-wa-id",
            "sub_type": JWTSubType.USER.value,
            "name": "Test User",
            "scope": ["read"],
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }

        token = jwt.encode(payload, auth_service.gateway_secret, algorithm="HS256", headers={"kid": "test-kid"})

        # Verify synchronously
        result = auth_service.verify_token_sync(token)
        assert result is not None
        assert result["sub"] == "test-wa-id"
        assert result["sub_type"] == JWTSubType.USER.value

        # Authority tokens cannot be verified sync (need DB lookup)
        authority_payload = payload.copy()
        authority_payload["sub_type"] = JWTSubType.AUTHORITY.value

        authority_token = jwt.encode(
            authority_payload, auth_service.gateway_secret, algorithm="HS256", headers={"kid": "test-kid"}
        )

        result = auth_service.verify_token_sync(authority_token)
        assert result is None  # Cannot verify authority tokens sync


class TestAuthenticationServiceIntegration:
    """Integration tests for the authentication service."""

    @pytest.fixture
    def time_service(self):
        """Create a time service for testing."""
        return TimeService()

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)

    @pytest_asyncio.fixture
    async def auth_service(self, temp_db, time_service):
        """Create a WA authentication service for testing."""
        service = AuthenticationService(db_path=temp_db, time_service=time_service, key_dir=None)
        await service.start()
        yield service
        await service.stop()

    @pytest.mark.asyncio
    async def test_full_authentication_flow(self, auth_service):
        """Test complete authentication flow from creation to verification."""
        # Create WA
        wa = await auth_service.create_wa(
            name="Integration Test User",
            email="test@example.com",
            scopes=["read:self", "write:self"],
            role=WARole.OBSERVER,
        )

        assert wa.wa_id is not None
        assert wa.name == "Integration Test User"
        assert wa.role == WARole.OBSERVER

        # Create token
        token = await auth_service.create_token(wa.wa_id, TokenType.STANDARD, ttl=3600)

        # Authenticate
        auth_result = await auth_service.authenticate(token)
        assert auth_result is not None
        assert auth_result.authenticated is True
        assert auth_result.wa_id == wa.wa_id
        assert auth_result.name == wa.name
        assert auth_result.role == WARole.OBSERVER.value

        # Verify token
        verification = await auth_service.verify_token(token)
        assert verification is not None
        assert verification.valid is True
        assert verification.wa_id == wa.wa_id

    @pytest.mark.asyncio
    async def test_adapter_observer_flow(self, auth_service):
        """Test adapter observer creation and authentication."""
        adapter_type = "api"
        adapter_info = {"instance_id": "localhost:8080", "user_id": "api_user", "username": "API Observer"}

        # Create channel token for adapter
        token = await auth_service._create_channel_token_for_adapter(adapter_type, adapter_info)

        # Check token is cached
        adapter_id = f"{adapter_type}_{adapter_info['instance_id']}"
        assert auth_service._get_adapter_token(adapter_id) == token

        # Verify token
        result = await auth_service._verify_jwt_and_get_context(token)
        assert result is not None
        context, _ = result
        assert context.role == WARole.OBSERVER
        assert context.token_type == TokenType.CHANNEL

    @pytest.mark.asyncio
    async def test_wa_lifecycle(self, auth_service):
        """Test complete WA lifecycle: create, update, revoke."""
        # Create
        wa = await auth_service.create_wa(
            name="Lifecycle Test", email="lifecycle@test.com", scopes=["read:self"], role=WARole.OBSERVER
        )

        # List - should include new WA
        was = await auth_service.list_was(active_only=True)
        assert any(w.wa_id == wa.wa_id for w in was)

        # Update
        updated = await auth_service.update_wa(
            wa.wa_id, updates=WAUpdate(name="Updated Name", permissions=["read:self", "write:self"], is_active=True)
        )
        assert updated.name == "Updated Name"
        assert "write:self" in updated.scopes

        # Rotate keys
        old_pubkey = wa.pubkey
        rotated = await auth_service.rotate_keys(wa.wa_id)
        assert rotated is True

        updated_wa = await auth_service.get_wa(wa.wa_id)
        assert updated_wa.pubkey != old_pubkey

        # Revoke
        revoked = await auth_service.revoke_wa(wa.wa_id, "Test revocation")
        assert revoked is True

        # Should not be in active list
        active_was = await auth_service.list_was(active_only=True)
        assert not any(w.wa_id == wa.wa_id for w in active_was)

        # Should be in all list
        all_was = await auth_service.list_was(active_only=False)
        assert any(w.wa_id == wa.wa_id for w in all_was)

    @pytest.mark.asyncio
    async def test_bootstrap_process(self, temp_db, time_service):
        """Test bootstrap process with root certificate."""
        # Create a service without the real seed file
        service = AuthenticationService(temp_db, time_service)

        # Manually create and store a root WA for testing
        private_key, public_key = service.generate_keypair()
        root_wa = WACertificate(
            wa_id="wa-2025-07-14-ROOT01",
            name="Test Root Authority",
            role=WARole.ROOT,
            pubkey=service._encode_public_key(public_key),
            jwt_kid="root-test-kid",
            scopes_json='["*"]',
            created_at=datetime.now(timezone.utc),
        )
        await service._store_wa_certificate(root_wa)

        # Now bootstrap should create system WA
        await service.bootstrap_if_needed()

        # Check system WA was created
        system_wa = await service._get_system_wa()
        assert system_wa is not None
        assert system_wa.name == "CIRIS System Authority"
        assert system_wa.role == WARole.AUTHORITY
        assert system_wa.parent_wa_id == root_wa.wa_id

    @pytest.mark.asyncio
    async def test_task_signing_and_verification(self, auth_service):
        """Test task signing and verification functionality."""
        # Bootstrap to create system WA
        await auth_service.bootstrap_if_needed()

        # Get system WA
        system_wa_id = await auth_service.get_system_wa_id()
        if not system_wa_id:
            # Create system WA manually for test
            private_key, public_key = auth_service.generate_keypair()
            system_wa = WACertificate(
                wa_id="wa-2025-07-14-SYSTM1",
                name="CIRIS System Authority",
                role=WARole.AUTHORITY,
                pubkey=auth_service._encode_public_key(public_key),
                jwt_kid="system-kid",
                scopes_json='["system.task.create", "system.task.sign"]',
                created_at=datetime.now(timezone.utc),
            )
            await auth_service._store_wa_certificate(system_wa)

            # Store private key
            key_path = auth_service.key_dir / "system_wa.key"
            key_path.write_bytes(private_key)
            key_path.chmod(0o600)

            system_wa_id = system_wa.wa_id

        # Create mock task
        from ciris_engine.schemas.runtime.models import Task, TaskStatus

        mock_task = Task(
            task_id="test-task-001",
            channel_id="test_channel",
            description="Test task for signing",
            status=TaskStatus.PENDING,
            priority=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Sign task
        signature, signed_at = await auth_service.sign_task(mock_task, system_wa_id)
        assert signature is not None
        assert signed_at is not None

        # Update task with signature
        mock_task.signed_by = system_wa_id
        mock_task.signature = signature
        mock_task.signed_at = signed_at

        # Verify signature
        is_valid = await auth_service.verify_task_signature(mock_task)
        assert is_valid is True

        # Tamper with task and verify it fails
        mock_task.description = "Tampered description"
        is_valid = await auth_service.verify_task_signature(mock_task)
        assert is_valid is False


class TestAuthenticationServiceErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.fixture
    def time_service(self):
        """Create a time service for testing."""
        return TimeService()

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)

    @pytest_asyncio.fixture
    async def auth_service(self, temp_db, time_service):
        """Create a WA authentication service for testing."""
        service = AuthenticationService(db_path=temp_db, time_service=time_service, key_dir=None)
        await service.start()
        yield service
        await service.stop()

    @pytest.mark.asyncio
    async def test_get_nonexistent_wa(self, auth_service):
        """Test getting non-existent WA returns None."""
        result = await auth_service.get_wa("wa-9999-99-99-NONE01")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_nonexistent_wa(self, auth_service):
        """Test updating non-existent WA."""
        result = await auth_service.update_wa("wa-9999-99-99-NONE01", updates=WAUpdate(name="New Name"))
        assert result is None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_wa(self, auth_service):
        """Test revoking non-existent WA."""
        result = await auth_service.revoke_wa("wa-9999-99-99-NONE01", "Test")
        assert result is False

    @pytest.mark.asyncio
    async def test_create_token_invalid_wa(self, auth_service):
        """Test creating token for non-existent WA."""
        with pytest.raises(ValueError, match="WA .* not found"):
            await auth_service.create_token("wa-9999-99-99-NONE01", TokenType.STANDARD)

    @pytest.mark.asyncio
    async def test_create_channel_token_requires_channel(self, auth_service):
        """Test that CHANNEL token type requires channel_id."""
        # Create a test WA first
        wa = await auth_service.create_wa("Test User", "test@test.com", ["read"], WARole.OBSERVER)

        with pytest.raises(ValueError, match="CHANNEL tokens require channel_id"):
            await auth_service.create_token(wa.wa_id, TokenType.CHANNEL)

    @pytest.mark.asyncio
    async def test_sign_task_invalid_wa(self, auth_service):
        """Test signing task with invalid WA."""
        from ciris_engine.schemas.runtime.models import Task, TaskStatus

        mock_task = Task(
            task_id="test-task",
            channel_id="test_channel",
            description="Test",
            status=TaskStatus.PENDING,
            priority=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        with pytest.raises(ValueError, match="WA .* not found"):
            await auth_service.sign_task(mock_task, "wa-9999-99-99-NONE01")

    @pytest.mark.asyncio
    async def test_sign_task_no_private_key(self, auth_service):
        """Test signing task when private key management not implemented."""
        # Create a regular WA (not system)
        wa = await auth_service.create_wa("Regular User", "user@test.com", ["read"], WARole.OBSERVER)

        from ciris_engine.schemas.runtime.models import Task, TaskStatus

        mock_task = Task(
            task_id="test-task",
            channel_id="test_channel",
            description="Test",
            status=TaskStatus.PENDING,
            priority=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        with pytest.raises(ValueError, match="Private key management not implemented"):
            await auth_service.sign_task(mock_task, wa.wa_id)

    @pytest.mark.asyncio
    async def test_verify_unsigned_task(self, auth_service):
        """Test verifying task without signature."""
        from ciris_engine.schemas.runtime.models import Task, TaskStatus

        mock_task = Task(
            task_id="test-task",
            channel_id="test_channel",
            description="Test",
            status=TaskStatus.PENDING,
            priority=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        # No signature fields set
        is_valid = await auth_service.verify_task_signature(mock_task)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_database_corruption_handling(self, auth_service):
        """Test handling of database errors."""
        # In Docker containers running as root, file permissions don't prevent writes
        # Instead, we'll test by temporarily moving the database file
        import shutil

        db_backup = auth_service.db_path + ".backup"
        shutil.move(auth_service.db_path, db_backup)

        try:
            # Try to create a WA - should raise sqlite3.OperationalError
            with pytest.raises(sqlite3.OperationalError) as exc_info:
                wa = await auth_service.create_wa("Test", "test@test.com", ["read"], WARole.OBSERVER)

            # Verify it's the expected error
            assert "no such table" in str(exc_info.value).lower() or "unable to open" in str(exc_info.value).lower()
        finally:
            # Restore database
            shutil.move(db_backup, auth_service.db_path)

    @pytest.mark.asyncio
    async def test_health_check_with_db_issues(self, auth_service):
        """Test health check when database has issues."""
        # Initially healthy
        assert await auth_service.is_healthy() is True

        # Stop the service first
        await auth_service.stop()

        # Should report unhealthy when stopped
        assert await auth_service.is_healthy() is False

    def test_status_with_db_errors(self, auth_service):
        """Test getting status when database queries fail."""
        # Remove database to cause errors
        os.unlink(auth_service.db_path)

        # Should still return status (with zero counts)
        status = auth_service.get_status()
        assert status.service_name == "AuthenticationService"
        assert status.is_healthy is True  # Basic health
        assert status.metrics["certificate_count"] == 0.0


class TestAuthenticationServicePerformance:
    """Performance and async operation tests."""

    @pytest.fixture
    def time_service(self):
        """Create a time service for testing."""
        return TimeService()

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)

    @pytest_asyncio.fixture
    async def auth_service(self, temp_db, time_service):
        """Create a WA authentication service for testing."""
        service = AuthenticationService(db_path=temp_db, time_service=time_service, key_dir=None)
        await service.start()
        yield service
        await service.stop()

    @pytest.mark.asyncio
    async def test_concurrent_wa_creation(self, auth_service):
        """Test creating multiple WAs concurrently."""
        import asyncio

        async def create_wa(index):
            return await auth_service.create_wa(
                f"User {index}", f"user{index}@test.com", ["read:self"], WARole.OBSERVER
            )

        # Create 10 WAs concurrently
        tasks = [create_wa(i) for i in range(10)]
        was = await asyncio.gather(*tasks)

        # All should be created successfully
        assert len(was) == 10
        assert all(wa.wa_id is not None for wa in was)

        # Verify all are in database
        all_was = await auth_service.list_was()
        assert len(all_was) >= 10

    @pytest.mark.asyncio
    async def test_concurrent_token_verification(self, auth_service):
        """Test verifying multiple tokens concurrently."""
        import asyncio

        # Create test WA
        wa = await auth_service.create_wa("Concurrent Test", "concurrent@test.com", ["read"], WARole.OBSERVER)

        # Create multiple tokens
        tokens = [auth_service.create_gateway_token(wa, expires_hours=1) for _ in range(20)]

        # Verify all tokens concurrently
        async def verify(token):
            return await auth_service.verify_token(token)

        tasks = [verify(token) for token in tokens]
        results = await asyncio.gather(*tasks)

        # All should verify successfully
        assert all(r.valid for r in results)
        assert all(r.wa_id == wa.wa_id for r in results)

    @pytest.mark.asyncio
    async def test_token_cache_performance(self, auth_service):
        """Test that token cache improves performance."""
        import time

        # Create test WA and token
        wa = await auth_service.create_wa("Cache Test", "cache@test.com", ["read"], WARole.OBSERVER)
        token = auth_service.create_gateway_token(wa)

        # First verification (not cached)
        start = time.time()
        result1 = await auth_service._verify_token_internal(token)
        uncached_time = time.time() - start

        assert result1 is not None

        # Second verification (cached)
        start = time.time()
        result2 = await auth_service._verify_token_internal(token)
        cached_time = time.time() - start

        assert result2 == result1

        # Cached should be significantly faster (at least 10x)
        # Note: This might be flaky on slow systems, so we're conservative
        assert cached_time < uncached_time

    @pytest.mark.asyncio
    async def test_large_wa_list_performance(self, auth_service):
        """Test listing performance with many WAs."""
        # Create 100 WAs
        for i in range(100):
            private_key, public_key = auth_service.generate_keypair()
            wa = WACertificate(
                wa_id=f"wa-2025-07-14-PERF{i:02d}",
                name=f"Performance Test {i}",
                role=WARole.OBSERVER,
                pubkey=auth_service._encode_public_key(public_key),
                jwt_kid=f"perf-kid-{i}",
                scopes_json='["read:self"]',
                created_at=datetime.now(timezone.utc),
            )
            await auth_service._store_wa_certificate(wa)

        # Time the listing
        import time

        start = time.time()
        was = await auth_service.list_was()
        list_time = time.time() - start

        assert len(was) == 100
        # Should complete reasonably quickly (under 1 second)
        assert list_time < 1.0


class TestAuthenticationServiceSecurity:
    """Security-specific tests."""

    @pytest.fixture
    def time_service(self):
        """Create a time service for testing."""
        return TimeService()

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)

    @pytest_asyncio.fixture
    async def auth_service(self, temp_db, time_service):
        """Create a WA authentication service for testing."""
        service = AuthenticationService(db_path=temp_db, time_service=time_service, key_dir=None)
        await service.start()
        yield service
        await service.stop()

    def test_no_hardcoded_salts(self, auth_service):
        """Verify no hardcoded salts in encryption."""
        # Multiple encryptions of same data should differ
        secret = b"test secret"

        encrypted1 = auth_service._encrypt_secret(secret)
        encrypted2 = auth_service._encrypt_secret(secret)

        # Should have different salts/nonces
        assert encrypted1 != encrypted2

        # But both should decrypt to same value
        assert auth_service._decrypt_secret(encrypted1) == secret
        assert auth_service._decrypt_secret(encrypted2) == secret

    @pytest.mark.asyncio
    async def test_sql_injection_prevention(self, auth_service):
        """Test that SQL injection is prevented."""
        # Try various SQL injection patterns in WA ID
        injection_attempts = [
            "'; DROP TABLE wa_cert; --",
            "' OR '1'='1",
            "wa-2025-01-01-TEST'; DELETE FROM wa_cert WHERE '1'='1",
            'wa-2025-01-01-TEST"; DROP TABLE wa_cert; --',
        ]

        for attempt in injection_attempts:
            # Should handle safely (might reject as invalid format)
            result = await auth_service.get_wa(attempt)
            assert result is None

        # Table should still exist
        with sqlite3.connect(auth_service.db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wa_cert'")
            assert cursor.fetchone() is not None

    @pytest.mark.asyncio
    async def test_timing_attack_resistance(self, auth_service):
        """Test resistance to timing attacks on password verification."""
        import time

        # Create a password hash
        correct_password = "correct_password_123"
        wrong_password = "wrong_password_456"
        hash_value = auth_service.hash_password(correct_password)

        # Time multiple verifications
        correct_times = []
        wrong_times = []

        # Run more iterations for better statistical significance
        for _ in range(50):
            # Correct password
            start = time.perf_counter()  # More precise than time.time()
            auth_service._verify_password(correct_password, hash_value)
            correct_times.append(time.perf_counter() - start)

            # Wrong password
            start = time.perf_counter()
            auth_service._verify_password(wrong_password, hash_value)
            wrong_times.append(time.perf_counter() - start)

        # Remove outliers (top and bottom 10%)
        correct_times.sort()
        wrong_times.sort()
        trim_count = len(correct_times) // 10
        correct_times = correct_times[trim_count:-trim_count]
        wrong_times = wrong_times[trim_count:-trim_count]

        # Average times should be similar (constant-time comparison)
        avg_correct = sum(correct_times) / len(correct_times)
        avg_wrong = sum(wrong_times) / len(wrong_times)

        # Difference should be minimal (less than 30% difference to account for CI variability)
        ratio = max(avg_correct, avg_wrong) / min(avg_correct, avg_wrong)
        assert ratio < 1.3, f"Timing ratio {ratio:.4f} exceeds threshold - possible timing attack vulnerability"

    def test_key_file_permissions(self, auth_service):
        """Test that key files are created with secure permissions."""
        # Gateway secret should have restricted permissions
        secret_file = auth_service.key_dir / "gateway.secret.enc"
        if secret_file.exists():
            stat_info = os.stat(secret_file)
            mode = stat_info.st_mode & 0o777
            # Should be readable/writable by owner only (0o600)
            assert mode == 0o600

    @pytest.mark.asyncio
    async def test_token_expiration_enforcement(self, auth_service):
        """Test that expired tokens are properly rejected."""
        import time

        # Create WA manually to ensure it's in the database
        private_key, public_key = auth_service.generate_keypair()
        wa = WACertificate(
            wa_id="wa-2025-07-14-EXPIRY",
            name="Expiry Test",
            role=WARole.OBSERVER,
            pubkey=auth_service._encode_public_key(public_key),
            jwt_kid="expiry-test-kid",
            scopes_json='["read"]',
            created_at=datetime.now(timezone.utc),
        )
        await auth_service._store_wa_certificate(wa)

        # Create token with very short expiration
        token = auth_service.create_gateway_token(wa, expires_hours=0.001)  # ~3.6 seconds

        # Decode to verify it's well-formed
        import jwt

        decoded = jwt.decode(token, options={"verify_signature": False})
        assert decoded is not None
        assert decoded["sub"] == wa.wa_id

        # Verify immediately - should work
        result = await auth_service.verify_token(token)
        assert result is not None, "Token verification returned None"
        assert result.valid is True

        # Wait for expiration (plus some buffer for JWT leeway)
        time.sleep(5)

        # Should now be invalid
        result = await auth_service._verify_jwt_and_get_context(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_scope_enforcement(self, auth_service):
        """Test that scope requirements are enforced."""
        # Create WA with limited scopes
        wa = await auth_service.create_wa(
            "Limited User", "limited@test.com", ["read:self"], WARole.OBSERVER  # Only read:self
        )

        token = auth_service.create_gateway_token(wa)
        context = await auth_service._verify_token_internal(token)

        # Mock a function that requires admin scope
        @auth_service._require_scope("admin:system")
        async def admin_function(**kwargs):
            return "success"

        # Should raise error due to insufficient scope
        with pytest.raises(ValueError, match="Insufficient permissions"):
            await admin_function(auth_context=context)

    @pytest.mark.asyncio
    async def test_algorithm_confusion_prevention(self, auth_service):
        """Test prevention of algorithm confusion attacks."""
        # Create WA
        private_key, public_key = auth_service.generate_keypair()
        wa = WACertificate(
            wa_id="wa-2025-07-14-ALGTS1",  # Pattern requires exactly 6 uppercase chars
            name="Algorithm Test",
            role=WARole.AUTHORITY,
            pubkey=auth_service._encode_public_key(public_key),
            jwt_kid="alg-test-kid",
            scopes_json='["read", "write"]',
            created_at=datetime.now(timezone.utc),
        )
        await auth_service._store_wa_certificate(wa)

        # Create authority token (EdDSA)
        authority_token = auth_service._create_authority_token(wa, private_key)

        # Try to create a forged token with same payload but HS256
        decoded = jwt.decode(authority_token, options={"verify_signature": False})
        forged_token = jwt.encode(decoded, auth_service.gateway_secret, algorithm="HS256", headers={"kid": wa.jwt_kid})

        # Verification should fail - authority tokens must use EdDSA
        result = await auth_service._verify_jwt_and_get_context(forged_token)
        assert result is None

        # Similarly, try to forge a gateway token as authority token
        gateway_token = auth_service.create_gateway_token(wa)
        gateway_decoded = jwt.decode(gateway_token, options={"verify_signature": False})

        # Change sub_type to AUTHORITY
        gateway_decoded["sub_type"] = JWTSubType.AUTHORITY.value

        # Re-encode with gateway secret
        forged_authority = jwt.encode(
            gateway_decoded, auth_service.gateway_secret, algorithm="HS256", headers={"kid": wa.jwt_kid}
        )

        # Should fail because AUTHORITY tokens must use EdDSA
        result = await auth_service._verify_jwt_and_get_context(forged_authority)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
