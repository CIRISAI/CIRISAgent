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


@pytest.mark.asyncio
async def test_oauth_identity_creates_identity_mapping(temp_db, time_service):
    """Test that linking OAuth identity creates identity graph mapping for DSAR."""
    from unittest.mock import AsyncMock, Mock

    from ciris_engine.logic.utils.identity_resolution import get_all_identifiers
    from ciris_engine.protocols.services.graph.memory import MemoryServiceProtocol

    # Create mock memory service
    mock_memory_service = AsyncMock(spec=MemoryServiceProtocol)
    created_nodes = {}
    created_edges = []

    async def mock_recall(node_type, scope, filters):
        """Mock recall that returns stored nodes."""
        node_id = filters.get("id")
        if node_id and node_id in created_nodes:
            return [created_nodes[node_id]]
        return []

    async def mock_memorize(node):
        """Mock memorize that stores nodes."""
        from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus

        created_nodes[node.id] = node
        return MemoryOpResult(status=MemoryOpStatus.OK, data=node)

    async def mock_create_edge(edge):
        """Mock create_edge that stores edges."""
        from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus

        created_edges.append(edge)
        return MemoryOpResult(status=MemoryOpStatus.OK, data=edge)

    async def mock_get_node_edges(node_id, direction=None, edge_type=None):
        """Mock get_node_edges that returns stored edges."""
        return [e for e in created_edges if e.source == node_id or e.target == node_id]

    mock_memory_service.recall = mock_recall
    mock_memory_service.memorize = mock_memorize
    mock_memory_service.create_edge = mock_create_edge
    mock_memory_service.get_node_edges = mock_get_node_edges

    # Create auth service with memory bus
    auth_service = AuthenticationService(db_path=temp_db, time_service=time_service, key_dir=None)
    auth_service._memory_bus = mock_memory_service
    await auth_service.start()

    try:
        # Create WA
        private_key, public_key = auth_service.generate_keypair()
        wa = WACertificate(
            wa_id="wa-2025-06-24-IDMAP1",
            name="Identity Mapping Test",
            role=WARole.AUTHORITY,
            pubkey=auth_service._encode_public_key(public_key),
            jwt_kid="idmap-kid",
            scopes_json='["read:any"]',
            created_at=datetime.now(timezone.utc),
        )
        await auth_service._store_wa_certificate(wa)

        # Link OAuth identity - should create identity mapping
        linked = await auth_service.link_oauth_identity(
            wa_id=wa.wa_id,
            provider="google",
            external_id="google-user-789",
            account_name="Test User",
        )

        assert linked is not None
        assert any(link.provider == "google" for link in linked.oauth_links)

        # Verify identity mapping was created
        # Should have 2 nodes (wa_id and google_id) and 1 edge connecting them
        assert len(created_nodes) >= 2, f"Expected at least 2 nodes, got {len(created_nodes)}"
        assert len(created_edges) >= 1, f"Expected at least 1 edge, got {len(created_edges)}"

        # Verify nodes were created with correct IDs
        wa_node_id = f"user_identity:wa_id:{wa.wa_id}"
        google_node_id = "user_identity:google_id:google-user-789"
        assert wa_node_id in created_nodes, f"WA node not found. Created: {list(created_nodes.keys())}"
        assert google_node_id in created_nodes, f"Google node not found. Created: {list(created_nodes.keys())}"

        # Verify edge connects the two identities
        edge = created_edges[0]
        assert edge.relationship == "same_as"
        assert {edge.source, edge.target} == {wa_node_id, google_node_id}

        # Verify edge has correct confidence (source=oauth means confidence=1.0)
        assert edge.weight == 1.0
        assert "oauth" in edge.attributes.context

    finally:
        await auth_service.stop()


@pytest.mark.asyncio
async def test_oauth_linking_without_memory_bus_still_works(auth_service):
    """Test that OAuth linking works even if memory bus is unavailable (non-blocking)."""
    # Ensure auth_service has no memory_bus
    if hasattr(auth_service, "_memory_bus"):
        delattr(auth_service, "_memory_bus")

    # Create WA
    private_key, public_key = auth_service.generate_keypair()
    wa = WACertificate(
        wa_id="wa-2025-06-24-NOMEM1",
        name="No Memory Bus Test",
        role=WARole.AUTHORITY,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="nomem-kid",
        scopes_json='["read:any"]',
        created_at=datetime.now(timezone.utc),
    )
    await auth_service._store_wa_certificate(wa)

    # Link OAuth identity - should succeed despite no memory bus
    linked = await auth_service.link_oauth_identity(
        wa_id=wa.wa_id,
        provider="discord",
        external_id="discord-user-999",
        account_name="No Mem Test",
    )

    # OAuth link should still work
    assert linked is not None
    assert any(link.provider == "discord" for link in linked.oauth_links)
    assert linked.oauth_provider == "discord"


# =============================================================================
# CIRISVerify Named Key Tests - WA Signing Capability
# =============================================================================


class MockCIRISVerify:
    """Mock CIRISVerify for testing named key operations."""

    def __init__(self):
        self._keys: dict[str, bytes] = {}  # key_id -> private_key (seed)

    def store_named_key(self, key_id: str, seed: bytes) -> bool:
        """Store a named key."""
        self._keys[key_id] = seed
        return True

    def has_named_key(self, key_id: str) -> bool:
        """Check if a named key exists."""
        return key_id in self._keys

    def sign_with_named_key(self, key_id: str, data: bytes) -> bytes:
        """Sign data with a named key."""
        from cryptography.hazmat.primitives.asymmetric import ed25519

        if key_id not in self._keys:
            raise ValueError(f"Key {key_id} not found")
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(self._keys[key_id])
        return private_key.sign(data)

    def get_named_key_public(self, key_id: str) -> bytes:
        """Get public key for a named key."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519

        if key_id not in self._keys:
            raise ValueError(f"Key {key_id} not found")
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(self._keys[key_id])
        return private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def delete_named_key(self, key_id: str) -> bool:
        """Delete a named key."""
        if key_id in self._keys:
            del self._keys[key_id]
            return True
        return False

    def list_named_keys(self) -> list:
        """List all named key IDs."""
        return list(self._keys.keys())


@pytest.fixture
def mock_verifier():
    """Create a mock CIRISVerify instance."""
    return MockCIRISVerify()


@pytest.mark.asyncio
async def test_create_wa_stores_key_in_verifier(temp_db, time_service, mock_verifier, monkeypatch):
    """Test that create_wa() stores the private key in CIRISVerify."""
    from ciris_engine.logic.services.infrastructure.authentication import service as auth_module

    # Mock the verifier singleton functions
    monkeypatch.setattr(auth_module, "has_verifier", lambda: True)
    monkeypatch.setattr(auth_module, "get_verifier", lambda: mock_verifier)

    service = AuthenticationService(db_path=temp_db, time_service=time_service)
    await service.start()

    try:
        # Create a new WA
        wa = await service.create_wa(
            name="test_user",
            email="test@example.com",
            scopes=["read:any"],
            role=WARole.OBSERVER,
        )

        # Verify key was stored in CIRISVerify
        assert mock_verifier.has_named_key(wa.wa_id), "WA key should be stored in CIRISVerify"
        assert wa.wa_id in mock_verifier.list_named_keys()

    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_sign_as_wa_uses_verifier(temp_db, time_service, mock_verifier, monkeypatch):
    """Test that sign_as_wa() uses CIRISVerify named keys."""
    import base64

    from ciris_engine.logic.services.infrastructure.authentication import service as auth_module

    # Mock the verifier singleton functions
    monkeypatch.setattr(auth_module, "has_verifier", lambda: True)
    monkeypatch.setattr(auth_module, "get_verifier", lambda: mock_verifier)

    service = AuthenticationService(db_path=temp_db, time_service=time_service)
    await service.start()

    try:
        # Create a WA (this stores the key in mock verifier)
        wa = await service.create_wa(
            name="signer_test",
            email="signer@example.com",
            scopes=["*"],
            role=WARole.AUTHORITY,
        )

        # Sign some data
        test_data = b"test data to sign"
        signature = await service.sign_as_wa(wa.wa_id, test_data)

        # Verify signature is valid base64
        sig_bytes = base64.b64decode(signature)
        assert len(sig_bytes) == 64, "Ed25519 signature should be 64 bytes"

        # Verify signature using the public key
        from cryptography.hazmat.primitives.asymmetric import ed25519

        pubkey_bytes = mock_verifier.get_named_key_public(wa.wa_id)
        pubkey = ed25519.Ed25519PublicKey.from_public_bytes(pubkey_bytes)
        # This will raise if signature is invalid
        pubkey.verify(sig_bytes, test_data)

    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_sign_as_wa_fails_for_unknown_wa(temp_db, time_service, mock_verifier, monkeypatch):
    """Test that sign_as_wa() fails for non-existent WA."""
    from ciris_engine.logic.services.infrastructure.authentication import service as auth_module

    monkeypatch.setattr(auth_module, "has_verifier", lambda: True)
    monkeypatch.setattr(auth_module, "get_verifier", lambda: mock_verifier)

    service = AuthenticationService(db_path=temp_db, time_service=time_service)
    await service.start()

    try:
        with pytest.raises(ValueError, match="not found"):
            await service.sign_as_wa("wa-nonexistent", b"data")
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_sign_as_wa_fails_without_key(temp_db, time_service, mock_verifier, monkeypatch):
    """Test that sign_as_wa() fails for WA without signing key in CIRISVerify."""
    from ciris_engine.logic.services.infrastructure.authentication import service as auth_module

    # Start with verifier disabled so key isn't stored during create_wa
    monkeypatch.setattr(auth_module, "has_verifier", lambda: False)

    service = AuthenticationService(db_path=temp_db, time_service=time_service)
    await service.start()

    try:
        # Create WA without verifier (key not stored)
        wa = await service.create_wa(
            name="no_key_test",
            email="nokey@example.com",
            scopes=["read:any"],
            role=WARole.OBSERVER,
        )

        # Now enable verifier but key wasn't stored
        monkeypatch.setattr(auth_module, "has_verifier", lambda: True)
        monkeypatch.setattr(auth_module, "get_verifier", lambda: mock_verifier)

        # Should fail because key doesn't exist
        with pytest.raises(ValueError, match="No signing key available"):
            await service.sign_as_wa(wa.wa_id, b"data")

    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_migrate_wa_keys_auto_rotates_user_was(temp_db, time_service, mock_verifier, monkeypatch):
    """Test that migration auto-rotates keys for user WAs without keys in CIRISVerify."""
    from ciris_engine.logic.services.infrastructure.authentication import service as auth_module

    # Start without verifier to simulate pre-migration state
    monkeypatch.setattr(auth_module, "has_verifier", lambda: False)

    service = AuthenticationService(db_path=temp_db, time_service=time_service)
    await service.start()

    try:
        # Create a user WA without verifier (simulating old behavior where keys were discarded)
        wa = await service.create_wa(
            name="legacy_user",
            email="legacy@example.com",
            scopes=["*"],
            role=WARole.AUTHORITY,
        )
        original_pubkey = wa.pubkey

        # Verify key is NOT in verifier
        assert not mock_verifier.has_named_key(wa.wa_id)

        # Now enable verifier and run migration
        monkeypatch.setattr(auth_module, "has_verifier", lambda: True)
        monkeypatch.setattr(auth_module, "get_verifier", lambda: mock_verifier)

        await service._migrate_wa_keys_to_verify()

        # Verify key was auto-rotated and stored in CIRISVerify
        assert mock_verifier.has_named_key(wa.wa_id), "User WA key should be auto-rotated into CIRISVerify"

        # Verify pubkey was updated in database
        updated_wa = await service.get_wa(wa.wa_id)
        assert updated_wa.pubkey != original_pubkey, "Public key should be updated after rotation"

        # Verify new pubkey matches the key in CIRISVerify
        verify_pubkey = mock_verifier.get_named_key_public(wa.wa_id)
        assert updated_wa.pubkey == service._encode_public_key(verify_pubkey)

    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_migrate_skips_was_with_existing_keys(temp_db, time_service, mock_verifier, monkeypatch):
    """Test that migration doesn't re-rotate WAs that already have keys in CIRISVerify."""
    from ciris_engine.logic.services.infrastructure.authentication import service as auth_module

    # Start with verifier enabled
    monkeypatch.setattr(auth_module, "has_verifier", lambda: True)
    monkeypatch.setattr(auth_module, "get_verifier", lambda: mock_verifier)

    service = AuthenticationService(db_path=temp_db, time_service=time_service)
    await service.start()

    try:
        # Create WA with verifier (key stored properly)
        wa = await service.create_wa(
            name="modern_user",
            email="modern@example.com",
            scopes=["*"],
            role=WARole.AUTHORITY,
        )
        original_pubkey = wa.pubkey

        # Verify key is in verifier
        assert mock_verifier.has_named_key(wa.wa_id)

        # Run migration again
        await service._migrate_wa_keys_to_verify()

        # Verify pubkey was NOT changed (no rotation needed)
        updated_wa = await service.get_wa(wa.wa_id)
        assert updated_wa.pubkey == original_pubkey, "Public key should NOT change for WAs with existing keys"

    finally:
        await service.stop()
