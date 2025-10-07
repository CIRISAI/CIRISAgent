"""Unit tests for WA Authentication Service."""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.authority.wise_authority import WAUpdate
from ciris_engine.schemas.services.authority_core import JWTSubType, WACertificate, WARole
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus


@pytest.fixture
def time_service():
    """Create a time service for testing."""
    return TimeService()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


@pytest_asyncio.fixture
async def auth_service(temp_db, time_service):
    """Create a WA authentication service for testing."""
    service = AuthenticationService(db_path=temp_db, time_service=time_service, key_dir=None)  # Will use default
    await service.start()
    yield service
    await service.stop()


@pytest.mark.asyncio
async def test_auth_service_lifecycle(auth_service):
    """Test AuthenticationService start/stop lifecycle."""
    # Service should already be started from fixture
    assert await auth_service.is_healthy()
    # Service will be stopped by fixture


@pytest.mark.asyncio
async def test_wa_certificate_creation(auth_service):
    """Test creating WA certificates."""
    # Create a test WA
    private_key, public_key = auth_service.generate_keypair()

    wa = WACertificate(
        wa_id="wa-2025-06-24-TEST01",  # Matches required pattern
        name="Test WA",
        role=WARole.AUTHORITY,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="test-kid",
        scopes_json='["read:any", "write:message"]',
        created_at=datetime.now(timezone.utc),
    )

    # Store the certificate
    await auth_service._store_wa_certificate(wa)

    # Retrieve it
    retrieved = await auth_service.get_wa("wa-2025-06-24-TEST01")
    assert retrieved is not None
    assert retrieved.name == "Test WA"
    assert retrieved.role == WARole.AUTHORITY


@pytest.mark.asyncio
async def test_adapter_observer_creation(auth_service):
    """Test creating adapter observer WAs."""
    adapter_id = "cli:testuser@testhost"
    name = "CLI Observer"

    # Create observer
    observer = await auth_service._create_adapter_observer(adapter_id, name)

    assert observer.role == WARole.OBSERVER
    assert observer.adapter_id == adapter_id
    assert observer.name == name
    # TokenType is not a field on WACertificate
    # No need to check active - it's handled by database


@pytest.mark.asyncio
async def test_wa_certificate_persists_adapter_metadata(auth_service):
    """Ensure adapter metadata fields persist when storing observers."""
    timestamp = datetime.now(timezone.utc)
    metadata = {"bot_id": "123456", "shard": "west"}

    # Create a keypair for the WA
    private_key, public_key = auth_service.generate_keypair()

    wa = WACertificate(
        wa_id="wa-2025-06-24-META01",
        name="Metadata Observer",
        role=WARole.OBSERVER,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="metadata-kid",
        scopes_json='["read:any"]',
        adapter_id="discord:metadata",
        adapter_name="Discord",
        adapter_metadata_json=json.dumps(metadata),
        created_at=timestamp,
        last_auth=timestamp,
    )

    await auth_service._store_wa_certificate(wa)

    retrieved = await auth_service.get_wa("wa-2025-06-24-META01")
    assert retrieved is not None
    assert retrieved.adapter_name == "Discord"
    assert retrieved.adapter_metadata_json is not None
    assert json.loads(retrieved.adapter_metadata_json) == metadata


@pytest.mark.asyncio
async def test_channel_token_creation(auth_service):
    """Test channel token creation and verification."""
    # Create observer WA first
    adapter_id = "test:adapter"
    observer = await auth_service._create_adapter_observer(adapter_id, "Test Observer")

    # Create channel token
    token = await auth_service.create_channel_token(wa_id=observer.wa_id, channel_id="test-channel", ttl=3600)

    assert token is not None
    assert len(token) > 0

    # Verify token
    result = await auth_service._verify_jwt_and_get_context(token)
    assert result is not None
    context, expiration = result
    assert context.wa_id == observer.wa_id
    assert context.role == WARole.OBSERVER


@pytest.mark.asyncio
async def test_gateway_token_creation(auth_service):
    """Test gateway token creation."""
    # Create a regular WA
    private_key, public_key = auth_service.generate_keypair()

    wa = WACertificate(
        wa_id="wa-2025-06-24-GATE01",
        name="Gateway Test WA",
        role=WARole.AUTHORITY,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="gateway-kid",
        scopes_json='["read:self", "write:self"]',
        created_at=datetime.now(timezone.utc),
    )

    await auth_service._store_wa_certificate(wa)

    # Create gateway token
    token = auth_service.create_gateway_token(wa, expires_hours=8)

    assert token is not None

    # Verify token
    result = await auth_service._verify_jwt_and_get_context(token)
    assert result is not None
    context, expiration = result
    assert context.wa_id == wa.wa_id
    assert context.sub_type == JWTSubType.USER or context.sub_type == JWTSubType.OAUTH
    # Verify expiration is extracted
    assert expiration is not None


@pytest.mark.asyncio
async def test_wa_update(auth_service):
    """Test updating WA certificates."""
    # Create a WA
    private_key, public_key = auth_service.generate_keypair()

    wa = WACertificate(
        wa_id="wa-2025-06-24-UPDT01",
        name="Original Name",
        role=WARole.AUTHORITY,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="update-kid",
        scopes_json='["read:self"]',
        created_at=datetime.now(timezone.utc),
    )

    await auth_service._store_wa_certificate(wa)

    # Update the WA
    update = WAUpdate(name="Updated Name", permissions=["read:self", "write:self"])

    updated = await auth_service.update_wa("wa-2025-06-24-UPDT01", updates=update)

    assert updated is not None
    assert updated.name == "Updated Name"
    assert "write:self" in updated.scopes


@pytest.mark.asyncio
async def test_wa_revocation(auth_service):
    """Test revoking WA certificates."""
    # Create a WA
    private_key, public_key = auth_service.generate_keypair()

    wa = WACertificate(
        wa_id="wa-2025-06-24-REVK01",
        name="To Be Revoked",
        role=WARole.AUTHORITY,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="revoke-kid",
        scopes_json='["read:self"]',
        created_at=datetime.now(timezone.utc),
    )

    await auth_service._store_wa_certificate(wa)

    # Revoke it
    revoked = await auth_service.revoke_wa("wa-2025-06-24-REVK01", "Test revocation")
    assert revoked is True

    # Check it's inactive (get_wa only returns active WAs)
    retrieved = await auth_service.get_wa("wa-2025-06-24-REVK01")
    assert retrieved is None  # Should not be found since it's inactive


@pytest.mark.asyncio
async def test_wa_cert_schema_migration_adds_missing_columns(temp_db, time_service):
    """Existing databases should receive new WA certificate columns."""

    # Create an old-style table without the new columns
    with sqlite3.connect(temp_db) as conn:
        conn.executescript(
            """
            CREATE TABLE wa_cert (
                wa_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT,
                pubkey TEXT NOT NULL,
                jwt_kid TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                api_key_hash TEXT,
                oauth_provider TEXT,
                oauth_external_id TEXT,
                auto_minted INTEGER DEFAULT 0,
                parent_wa_id TEXT,
                parent_signature TEXT,
                scopes_json TEXT NOT NULL,
                adapter_id TEXT,
                token_type TEXT DEFAULT 'standard',
                created TEXT NOT NULL,
                last_login TEXT,
                active INTEGER DEFAULT 1
            );
            """
        )

    # Initialize the service which should add missing columns
    service = AuthenticationService(db_path=temp_db, time_service=time_service, key_dir=None)
    await service.start()
    await service.stop()

    # Check that the new columns were added
    with sqlite3.connect(temp_db) as conn:
        cursor = conn.execute("PRAGMA table_info(wa_cert)")
        columns = {row[1] for row in cursor.fetchall()}

    assert "custom_permissions_json" in columns
    assert "adapter_name" in columns
    assert "adapter_metadata_json" in columns


@pytest.mark.asyncio
async def test_password_hashing(auth_service):
    """Test password hashing and verification."""
    password = "test_password_123"

    # Hash password
    hashed = auth_service.hash_password(password)
    assert hashed != password
    assert len(hashed) > 0

    # Verify correct password
    assert auth_service._verify_password(password, hashed) is True

    # Verify wrong password
    assert auth_service._verify_password("wrong_password", hashed) is False


@pytest.mark.asyncio
async def test_keypair_generation(auth_service):
    """Test Ed25519 keypair generation."""
    private_key, public_key = auth_service.generate_keypair()

    assert len(private_key) == 32  # Ed25519 private key is 32 bytes
    assert len(public_key) == 32  # Ed25519 public key is 32 bytes


@pytest.mark.asyncio
async def test_data_signing(auth_service):
    """Test data signing and verification."""
    # Generate keypair
    private_key, public_key = auth_service.generate_keypair()
    encoded_pubkey = auth_service._encode_public_key(public_key)

    # Sign data
    data = b"test data to sign"
    signature = auth_service.sign_data(data, private_key)

    assert signature is not None
    assert len(signature) > 0

    # Verify signature
    is_valid = auth_service._verify_signature(data, signature, encoded_pubkey)
    assert is_valid is True

    # Verify with wrong data
    wrong_data = b"different data"
    is_valid = auth_service._verify_signature(wrong_data, signature, encoded_pubkey)
    assert is_valid is False


def test_auth_service_capabilities(auth_service):
    """Test AuthenticationService.get_capabilities() returns correct info."""
    caps = auth_service.get_capabilities()
    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "AuthenticationService"
    assert caps.version == "1.0.0"
    assert "get_wa" in caps.actions
    assert "update_wa" in caps.actions
    assert "revoke_wa" in caps.actions
    # generate_keypair is not exposed as an action, it's internal
    assert "TimeService" in caps.dependencies
    assert caps.metadata.description == "Infrastructure service for WA authentication and identity management"


def test_auth_service_status(auth_service):
    """Test AuthenticationService.get_status() returns correct status."""
    status = auth_service.get_status()
    assert isinstance(status, ServiceStatus)
    assert status.service_name == "AuthenticationService"
    assert status.service_type == "infrastructure_service"
    assert status.is_healthy is True
    assert "certificate_count" in status.metrics
    assert "cached_tokens" in status.metrics


@pytest.mark.asyncio
async def test_last_login_update(auth_service):
    """Test updating last login timestamp."""
    # Create a WA
    private_key, public_key = auth_service.generate_keypair()

    wa = WACertificate(
        wa_id="wa-2025-06-24-LOGN01",
        name="Login Test",
        role=WARole.AUTHORITY,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="login-kid",
        scopes_json='["read:self"]',
        created_at=datetime.now(timezone.utc),
        last_auth=None,
    )

    await auth_service._store_wa_certificate(wa)

    # Update last login
    await auth_service.update_last_login("wa-2025-06-24-LOGN01")

    # Check it was updated
    retrieved = await auth_service.get_wa("wa-2025-06-24-LOGN01")
    assert retrieved is not None
    assert retrieved.last_auth is not None


@pytest.mark.asyncio
async def test_list_all_was(auth_service):
    """Test listing all WA certificates."""
    # Create multiple WAs
    for i in range(3):
        private_key, public_key = auth_service.generate_keypair()
        wa = WACertificate(
            wa_id=f"wa-2025-06-24-LIST0{i}",
            name=f"List Test {i}",
            role=WARole.AUTHORITY,
            pubkey=auth_service._encode_public_key(public_key),
            jwt_kid=f"list-kid-{i}",
            scopes_json='["read:self"]',
            created_at=datetime.now(timezone.utc),
        )
        await auth_service._store_wa_certificate(wa)

    # List active only (all 3 are active)
    active_was = await auth_service._list_all_was(active_only=True)
    assert len(active_was) == 3

    # List all
    all_was = await auth_service._list_all_was(active_only=False)
    assert len(all_was) == 3


@pytest.mark.asyncio
async def test_jwt_expiration_extraction(auth_service):
    """Test that JWT expiration is correctly extracted from tokens."""
    # Create a test WA
    private_key, public_key = auth_service.generate_keypair()

    wa = WACertificate(
        wa_id="wa-2025-06-24-EXPTST",
        name="Expiration Test WA",
        role=WARole.AUTHORITY,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="exp-test-kid",
        scopes_json='["read", "write"]',
        created_at=datetime.now(timezone.utc),
    )

    await auth_service._store_wa_certificate(wa)

    # Create token with specific expiration
    token = auth_service.create_gateway_token(wa, expires_hours=2)

    # Decode to get expected expiration
    import jwt

    decoded = jwt.decode(token, options={"verify_signature": False})
    expected_exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)

    # Verify token and check expiration
    verification = await auth_service.verify_token(token)

    assert verification is not None
    assert verification.valid is True
    assert verification.wa_id == wa.wa_id
    assert verification.expires_at == expected_exp

    # Test token without expiration (long-lived observer token)
    observer = WACertificate(
        wa_id="wa-2025-06-24-OBSEX1",
        name="Observer No Exp",
        role=WARole.OBSERVER,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="obs-exp-kid",
        scopes_json='["observe"]',
        created_at=datetime.now(timezone.utc),
        adapter_id="test_adapter",
    )

    await auth_service._store_wa_certificate(observer)

    # Create channel token with no expiration (ttl=0)
    channel_token = await auth_service.create_channel_token(observer.wa_id, "test_channel", ttl=0)

    # Verify it handles missing expiration gracefully
    channel_verification = await auth_service.verify_token(channel_token)
    assert channel_verification is not None
    assert channel_verification.valid is True
    # When no expiration in token, should use current time as fallback
    assert channel_verification.expires_at is not None


@pytest.mark.asyncio
async def test_link_unlink_oauth_identity(auth_service):
    """Ensure multiple OAuth identities can be linked and unlinked."""

    private_key, public_key = auth_service.generate_keypair()

    wa = WACertificate(
        wa_id="wa-2025-06-24-LINK01",
        name="Link Test WA",
        role=WARole.AUTHORITY,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="link-test-kid",
        scopes_json='["read:any"]',
        created_at=datetime.now(timezone.utc),
    )

    await auth_service._store_wa_certificate(wa)

    linked = await auth_service.link_oauth_identity(
        wa_id=wa.wa_id,
        provider="google",
        external_id="google-user-123",
        account_name="Google User",
        primary=True,
    )
    assert linked is not None
    assert linked.oauth_provider == "google"
    assert any(link.provider == "google" for link in linked.oauth_links)

    linked = await auth_service.link_oauth_identity(
        wa_id=wa.wa_id,
        provider="discord",
        external_id="discord-user-456",
        account_name="Discord User",
        metadata={"discriminator": "0001"},
    )
    assert linked is not None
    assert len(linked.oauth_links) == 2

    fetched = await auth_service.get_wa_by_oauth("discord", "discord-user-456")
    assert fetched is not None
    assert fetched.wa_id == wa.wa_id

    promoted = await auth_service.link_oauth_identity(
        wa_id=wa.wa_id,
        provider="discord",
        external_id="discord-user-456",
        primary=True,
    )
    assert promoted is not None
    assert promoted.oauth_provider == "discord"
    assert promoted.oauth_external_id == "discord-user-456"
    assert any(link.is_primary for link in promoted.oauth_links if link.provider == "discord")

    updated = await auth_service.unlink_oauth_identity(wa.wa_id, "google", "google-user-123")
    assert updated is not None
    assert all(link.provider != "google" for link in updated.oauth_links)
    assert updated.oauth_provider == "discord"
