"""
Comprehensive tests for WACLIBootstrapService.

Tests WA creation, minting, and approval operations for CLI-based wise authorities.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock, call, patch

import pytest

from ciris_engine.logic.infrastructure.sub_services.wa_cli_bootstrap import WACLIBootstrapService
from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.authority_core import WACertificate, WARole


@pytest.fixture
def mock_auth_service():
    """Create a mock authentication service."""
    auth_service = Mock(spec=AuthenticationService)

    # Mock key directory
    auth_service.key_dir = Path("/tmp/test_keys")

    # Mock keypair generation
    auth_service.generate_keypair = Mock(return_value=(b"private_key_bytes", b"public_key_bytes"))

    # Mock WA ID generation
    auth_service._generate_wa_id = Mock(return_value="wa-2025-01-18-ABC123")

    # Mock encoding
    auth_service._encode_public_key = Mock(return_value="encoded_public_key")

    # Mock password hashing
    auth_service.hash_password = Mock(return_value="hashed_password")

    # Mock certificate storage
    auth_service._store_wa_certificate = AsyncMock()

    # Mock WA retrieval
    auth_service.get_wa = AsyncMock()

    # Mock signing
    auth_service.sign_data = Mock(return_value="parent_signature")

    return auth_service


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    time_service = Mock(spec=TimeService)
    fixed_time = datetime(2025, 1, 18, 12, 0, 0, tzinfo=timezone.utc)
    time_service.now = Mock(return_value=fixed_time)
    return time_service


@pytest.fixture
def bootstrap_service(mock_auth_service, mock_time_service):
    """Create WACLIBootstrapService instance."""
    return WACLIBootstrapService(mock_auth_service, mock_time_service)


@pytest.fixture
def mock_prompt():
    """Mock Rich prompt for input testing."""
    with patch("ciris_engine.logic.infrastructure.sub_services.wa_cli_bootstrap.Prompt") as mock:
        yield mock


class TestWACLIBootstrapService:
    """Test suite for WACLIBootstrapService."""

    def test_initialization(self, mock_auth_service, mock_time_service):
        """Test service initialization."""
        service = WACLIBootstrapService(mock_auth_service, mock_time_service)

        assert service.auth_service == mock_auth_service
        assert service.time_service == mock_time_service
        assert service.console is not None

    @pytest.mark.asyncio
    async def test_bootstrap_new_root_success(self, bootstrap_service, mock_auth_service, mock_time_service, tmp_path):
        """Test successful root WA bootstrap."""
        # Setup key directory
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        mock_auth_service.key_dir = key_dir

        result = await bootstrap_service.bootstrap_new_root("TestRoot")

        assert result["status"] == "success"
        assert result["wa_id"] == "wa-2025-01-18-ABC123"
        assert result["name"] == "TestRoot"
        assert result["role"] == "root"
        assert "key_file" in result

        # Verify certificate creation
        mock_auth_service._store_wa_certificate.assert_called_once()
        stored_cert = mock_auth_service._store_wa_certificate.call_args[0][0]
        assert isinstance(stored_cert, WACertificate)
        assert stored_cert.wa_id == "wa-2025-01-18-ABC123"
        assert stored_cert.name == "TestRoot"
        assert stored_cert.role == WARole.ROOT
        assert stored_cert.pubkey == "encoded_public_key"
        assert stored_cert.scopes_json == '["*"]'

        # Verify key file creation
        key_file = key_dir / "wa-2025-01-18-ABC123.key"
        assert key_file.exists()
        assert key_file.read_bytes() == b"private_key_bytes"
        assert oct(key_file.stat().st_mode)[-3:] == "600"

    @pytest.mark.asyncio
    async def test_bootstrap_new_root_with_password(self, bootstrap_service, mock_auth_service, mock_prompt, tmp_path):
        """Test root WA bootstrap with password."""
        # Setup
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        mock_auth_service.key_dir = key_dir
        mock_prompt.ask.side_effect = ["password123", "password123"]  # Matching passwords

        result = await bootstrap_service.bootstrap_new_root("TestRoot", use_password=True)

        assert result["status"] == "success"

        # Verify password was hashed and stored
        mock_auth_service.hash_password.assert_called_once_with("password123")
        stored_cert = mock_auth_service._store_wa_certificate.call_args[0][0]
        assert stored_cert.password_hash == "hashed_password"

    @pytest.mark.asyncio
    async def test_bootstrap_new_root_password_mismatch(
        self, bootstrap_service, mock_auth_service, mock_prompt, tmp_path
    ):
        """Test root WA bootstrap with mismatched passwords."""
        # Setup
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        mock_auth_service.key_dir = key_dir
        mock_prompt.ask.side_effect = ["password123", "different456"]  # Mismatched passwords

        result = await bootstrap_service.bootstrap_new_root("TestRoot", use_password=True)

        assert result["status"] == "error"
        assert "Passwords do not match" in result["error"]

        # Verify certificate was not stored
        mock_auth_service._store_wa_certificate.assert_not_called()

    @pytest.mark.asyncio
    async def test_bootstrap_new_root_exception(self, bootstrap_service, mock_auth_service):
        """Test root WA bootstrap with exception."""
        mock_auth_service.generate_keypair.side_effect = Exception("Key generation failed")

        result = await bootstrap_service.bootstrap_new_root("TestRoot")

        assert result["status"] == "error"
        assert "Key generation failed" in result["error"]

    @pytest.mark.asyncio
    async def test_mint_wa_authority_success(self, bootstrap_service, mock_auth_service, tmp_path):
        """Test successful authority WA minting."""
        # Setup
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        mock_auth_service.key_dir = key_dir

        # Create parent key file
        parent_key_file = tmp_path / "parent.key"
        parent_key_file.write_bytes(b"parent_private_key")

        # Mock parent WA
        parent_wa = Mock(spec=WACertificate)
        parent_wa.wa_id = "wa-2025-01-18-PARENT"
        mock_auth_service.get_wa.return_value = parent_wa

        result = await bootstrap_service.mint_wa(
            parent_wa_id="wa-2025-01-18-PARENT",
            parent_key_file=str(parent_key_file),
            name="TestAuthority",
            role="authority",
        )

        assert result["status"] == "success"
        assert result["wa_id"] == "wa-2025-01-18-ABC123"
        assert result["name"] == "TestAuthority"
        assert result["role"] == "authority"
        assert result["parent_wa_id"] == "wa-2025-01-18-PARENT"
        assert result["scopes"] == ["wa:mint", "wa:approve", "write:task", "read:any", "write:message"]

        # Verify signature
        mock_auth_service.sign_data.assert_called_once()
        sign_call = mock_auth_service.sign_data.call_args
        assert sign_call[0][0] == b"wa-2025-01-18-ABC123:encoded_public_key:wa-2025-01-18-PARENT"
        assert sign_call[0][1] == b"parent_private_key"

        # Verify certificate
        stored_cert = mock_auth_service._store_wa_certificate.call_args[0][0]
        assert stored_cert.parent_wa_id == "wa-2025-01-18-PARENT"
        assert stored_cert.parent_signature == "parent_signature"

    @pytest.mark.asyncio
    async def test_mint_wa_observer_default_scopes(self, bootstrap_service, mock_auth_service, tmp_path):
        """Test observer WA minting with default scopes."""
        # Setup
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        mock_auth_service.key_dir = key_dir

        parent_key_file = tmp_path / "parent.key"
        parent_key_file.write_bytes(b"parent_private_key")

        parent_wa = Mock(spec=WACertificate)
        mock_auth_service.get_wa.return_value = parent_wa

        result = await bootstrap_service.mint_wa(
            parent_wa_id="wa-2025-01-18-PARENT",
            parent_key_file=str(parent_key_file),
            name="TestObserver",
            role="observer",
        )

        assert result["status"] == "success"
        assert result["role"] == "observer"
        assert result["scopes"] == ["read:any", "write:message"]

    @pytest.mark.asyncio
    async def test_mint_wa_custom_scopes(self, bootstrap_service, mock_auth_service, tmp_path):
        """Test WA minting with custom scopes."""
        # Setup
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        mock_auth_service.key_dir = key_dir

        parent_key_file = tmp_path / "parent.key"
        parent_key_file.write_bytes(b"parent_private_key")

        parent_wa = Mock(spec=WACertificate)
        mock_auth_service.get_wa.return_value = parent_wa

        custom_scopes = ["read:limited", "write:specific"]

        result = await bootstrap_service.mint_wa(
            parent_wa_id="wa-2025-01-18-PARENT",
            parent_key_file=str(parent_key_file),
            name="TestCustom",
            scopes=custom_scopes,
        )

        assert result["status"] == "success"
        assert result["scopes"] == custom_scopes

        # Verify scopes in certificate
        stored_cert = mock_auth_service._store_wa_certificate.call_args[0][0]
        assert stored_cert.scopes_json == json.dumps(custom_scopes)

    @pytest.mark.asyncio
    async def test_mint_wa_with_password(self, bootstrap_service, mock_auth_service, mock_prompt, tmp_path):
        """Test WA minting with password."""
        # Setup
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        mock_auth_service.key_dir = key_dir

        parent_key_file = tmp_path / "parent.key"
        parent_key_file.write_bytes(b"parent_private_key")

        parent_wa = Mock(spec=WACertificate)
        mock_auth_service.get_wa.return_value = parent_wa

        mock_prompt.ask.side_effect = ["secure_pass", "secure_pass"]

        result = await bootstrap_service.mint_wa(
            parent_wa_id="wa-2025-01-18-PARENT",
            parent_key_file=str(parent_key_file),
            name="TestSecure",
            use_password=True,
        )

        assert result["status"] == "success"

        # Verify password handling
        mock_auth_service.hash_password.assert_called_once_with("secure_pass")
        stored_cert = mock_auth_service._store_wa_certificate.call_args[0][0]
        assert stored_cert.password_hash == "hashed_password"

    @pytest.mark.asyncio
    async def test_mint_wa_parent_not_found(self, bootstrap_service, mock_auth_service):
        """Test WA minting when parent WA not found."""
        mock_auth_service.get_wa.return_value = None

        result = await bootstrap_service.mint_wa(
            parent_wa_id="wa-2025-01-18-NOEXST", parent_key_file="/path/to/key", name="TestChild"
        )

        assert result["status"] == "error"
        assert "Parent WA wa-2025-01-18-NOEXST not found" in result["error"]

    @pytest.mark.asyncio
    async def test_mint_wa_parent_key_not_found(self, bootstrap_service, mock_auth_service):
        """Test WA minting when parent key file not found."""
        parent_wa = Mock(spec=WACertificate)
        mock_auth_service.get_wa.return_value = parent_wa

        result = await bootstrap_service.mint_wa(
            parent_wa_id="wa-2025-01-18-PARENT", parent_key_file="/nonexistent/key.file", name="TestChild"
        )

        assert result["status"] == "error"
        assert "Parent key file not found" in result["error"]

    @pytest.mark.asyncio
    async def test_mint_wa_exception(self, bootstrap_service, mock_auth_service, tmp_path):
        """Test WA minting with exception."""
        parent_wa = Mock(spec=WACertificate)
        mock_auth_service.get_wa.return_value = parent_wa

        parent_key_file = tmp_path / "parent.key"
        parent_key_file.write_bytes(b"parent_private_key")

        # Cause exception during keypair generation
        mock_auth_service.generate_keypair.side_effect = Exception("Crypto error")

        result = await bootstrap_service.mint_wa(
            parent_wa_id="wa-2025-01-18-PARENT", parent_key_file=str(parent_key_file), name="TestChild"
        )

        assert result["status"] == "error"
        assert "Crypto error" in result["error"]

    def test_generate_mint_request_success(self, bootstrap_service, mock_auth_service, mock_time_service, tmp_path):
        """Test successful mint request generation."""
        # Setup
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        mock_auth_service.key_dir = key_dir

        with patch(
            "ciris_engine.logic.infrastructure.sub_services.wa_cli_bootstrap.secrets.token_urlsafe"
        ) as mock_token:
            mock_token.return_value = "test_code_123"

            result = bootstrap_service.generate_mint_request(name="TestRequest", requested_role="authority")

        assert result["status"] == "success"
        assert result["code"] == "test_code_123"
        assert result["request"]["name"] == "TestRequest"
        assert result["request"]["role"] == "authority"
        assert result["request"]["scopes"] == ["read:any", "write:message"]
        assert result["request"]["pubkey"] == "encoded_public_key"

        # Verify temporary key file
        temp_key_file = key_dir / "pending_test_code_123.key"
        assert temp_key_file.exists()
        assert temp_key_file.read_bytes() == b"private_key_bytes"
        assert oct(temp_key_file.stat().st_mode)[-3:] == "600"

    def test_generate_mint_request_custom_scopes(self, bootstrap_service, tmp_path):
        """Test mint request generation with custom scopes."""
        bootstrap_service.auth_service.key_dir = tmp_path / "keys"
        bootstrap_service.auth_service.key_dir.mkdir()

        with patch(
            "ciris_engine.logic.infrastructure.sub_services.wa_cli_bootstrap.secrets.token_urlsafe"
        ) as mock_token:
            mock_token.return_value = "test_code"

            custom_scopes = ["custom:scope1", "custom:scope2"]
            result = bootstrap_service.generate_mint_request(name="TestRequest", requested_scopes=custom_scopes)

        assert result["status"] == "success"
        assert result["request"]["scopes"] == custom_scopes

    def test_generate_mint_request_expiry(self, bootstrap_service, mock_time_service, tmp_path):
        """Test mint request has correct expiry time."""
        bootstrap_service.auth_service.key_dir = tmp_path / "keys"
        bootstrap_service.auth_service.key_dir.mkdir()

        base_time = datetime(2025, 1, 18, 12, 0, 0, tzinfo=timezone.utc)
        mock_time_service.now.return_value = base_time

        with patch(
            "ciris_engine.logic.infrastructure.sub_services.wa_cli_bootstrap.secrets.token_urlsafe"
        ) as mock_token:
            mock_token.return_value = "test_code"

            result = bootstrap_service.generate_mint_request(name="TestRequest")

        assert result["status"] == "success"

        # Check expiry is 10 minutes from creation
        created_time = datetime.fromisoformat(result["request"]["created"])
        expires_time = datetime.fromisoformat(result["request"]["expires"])
        assert expires_time == created_time + timedelta(minutes=10)

    def test_generate_mint_request_exception(self, bootstrap_service, mock_auth_service):
        """Test mint request generation with exception."""
        mock_auth_service.generate_keypair.side_effect = Exception("Key error")

        result = bootstrap_service.generate_mint_request(name="TestRequest")

        assert result["status"] == "error"
        assert "Key error" in result["error"]

    def test_approve_mint_request_mock_success(self, bootstrap_service):
        """Test mint request approval (mock implementation)."""
        result = bootstrap_service.approve_mint_request(
            code="test_code", approver_wa_id="wa-2025-01-18-APRVR1", _approver_key_file="/path/to/key"
        )

        assert result["status"] == "success"
        assert "mock implementation" in result["message"]

    @pytest.mark.asyncio
    async def test_bootstrap_key_permissions(self, bootstrap_service, mock_auth_service, tmp_path):
        """Test that created keys have correct permissions."""
        # Setup
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        mock_auth_service.key_dir = key_dir

        await bootstrap_service.bootstrap_new_root("TestRoot")

        # Check key file permissions
        key_file = key_dir / "wa-2025-01-18-ABC123.key"
        assert key_file.exists()

        # Get octal permission string (last 3 digits)
        mode = oct(key_file.stat().st_mode)[-3:]
        assert mode == "600", f"Expected 600 permissions, got {mode}"

    @pytest.mark.asyncio
    async def test_mint_wa_jwt_kid_generation(self, bootstrap_service, mock_auth_service, tmp_path):
        """Test JWT kid generation for minted WA."""
        # Setup
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        mock_auth_service.key_dir = key_dir

        parent_key_file = tmp_path / "parent.key"
        parent_key_file.write_bytes(b"parent_private_key")

        parent_wa = Mock(spec=WACertificate)
        mock_auth_service.get_wa.return_value = parent_wa

        # Set specific WA ID to test kid generation
        mock_auth_service._generate_wa_id.return_value = "wa-2025-01-18-XYZ789"

        await bootstrap_service.mint_wa(
            parent_wa_id="wa-2025-01-18-PARENT", parent_key_file=str(parent_key_file), name="TestChild"
        )

        # Verify JWT kid format
        stored_cert = mock_auth_service._store_wa_certificate.call_args[0][0]
        assert stored_cert.jwt_kid == "wa-jwt-xyz789"  # Last 6 chars, lowercase

    @pytest.mark.asyncio
    async def test_bootstrap_root_jwt_kid_generation(self, bootstrap_service, mock_auth_service, tmp_path):
        """Test JWT kid generation for root WA."""
        # Setup
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        mock_auth_service.key_dir = key_dir

        # Set specific WA ID
        mock_auth_service._generate_wa_id.return_value = "wa-2025-01-18-ROOT99"

        await bootstrap_service.bootstrap_new_root("TestRoot")

        # Verify JWT kid format
        stored_cert = mock_auth_service._store_wa_certificate.call_args[0][0]
        assert stored_cert.jwt_kid == "wa-jwt-root99"

    def test_generate_mint_request_observer_role(self, bootstrap_service, tmp_path):
        """Test mint request generation for observer role."""
        bootstrap_service.auth_service.key_dir = tmp_path / "keys"
        bootstrap_service.auth_service.key_dir.mkdir()

        with patch(
            "ciris_engine.logic.infrastructure.sub_services.wa_cli_bootstrap.secrets.token_urlsafe"
        ) as mock_token:
            mock_token.return_value = "observer_code"

            result = bootstrap_service.generate_mint_request(name="TestObserver", requested_role="observer")

        assert result["status"] == "success"
        assert result["request"]["role"] == "observer"
        # Default scopes for non-observer when not specified
        assert result["request"]["scopes"] == ["read:any", "write:message"]
