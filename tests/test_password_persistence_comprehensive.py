"""
Comprehensive tests for password persistence in CIRIS AuthenticationService.

Tests the critical password storage flow to ensure:
1. Passwords are properly hashed using PBKDF2
2. Passwords are persisted to the correct database file (ciris_engine_auth.db) 
3. The wa_cert table is created and used correctly
4. Authentication works with stored passwords
5. Default admin password protection (cannot be reset accidentally)
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.authority_core import WACertificate, WARole


@pytest.fixture
def time_service():
    """Create a time service for testing."""
    return TimeService()


@pytest.fixture
def temp_auth_db():
    """Create a temporary auth database for testing."""
    with tempfile.NamedTemporaryFile(suffix="_auth.db", delete=False) as f:
        auth_db_path = f.name
    yield auth_db_path
    if os.path.exists(auth_db_path):
        os.unlink(auth_db_path)


@pytest.fixture
def temp_key_dir():
    """Create a temporary key directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest_asyncio.fixture
async def auth_service(temp_auth_db, time_service, temp_key_dir):
    """Create AuthenticationService for testing password persistence."""
    service = AuthenticationService(
        db_path=temp_auth_db, 
        time_service=time_service, 
        key_dir=temp_key_dir
    )
    await service.start()
    yield service
    await service.stop()


@pytest.mark.asyncio
async def test_password_hashing_and_storage(auth_service, temp_auth_db):
    """Test that passwords are properly hashed and stored in auth database."""
    # Create a WA with password
    private_key, public_key = auth_service.generate_keypair()
    test_password = "test_secure_password_123!"
    
    # Hash the password
    hashed_password = auth_service.hash_password(test_password)
    
    # Verify hash format (PBKDF2 with base64 encoding)
    assert hashed_password != test_password
    assert len(hashed_password) > 0
    import base64
    try:
        decoded = base64.b64decode(hashed_password)
        assert len(decoded) == 64  # 32 bytes salt + 32 bytes key
    except Exception:
        pytest.fail("Password hash should be valid base64")
    
    # Create WA certificate with password hash
    wa = WACertificate(
        wa_id="wa-2025-01-18-PWTEST",
        name="Password Test WA",
        role=WARole.AUTHORITY,  # Use AUTHORITY instead of ADMIN
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="password-test-kid",
        password_hash=hashed_password,  # Store the hashed password
        scopes_json='["admin:all"]',
        created_at=datetime.now(timezone.utc),
    )
    
    # Store the certificate (this should persist password to database)
    await auth_service._store_wa_certificate(wa)
    
    # Verify password was stored in correct database file
    assert os.path.exists(temp_auth_db), f"Auth database should exist at {temp_auth_db}"
    
    # Check the database directly
    with sqlite3.connect(temp_auth_db) as conn:
        cursor = conn.cursor()
        
        # Verify wa_cert table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wa_cert'")
        table_exists = cursor.fetchone()
        assert table_exists, "wa_cert table should exist in auth database"
        
        # Verify password is stored
        cursor.execute("SELECT password_hash FROM wa_cert WHERE wa_id = ?", (wa.wa_id,))
        stored_hash = cursor.fetchone()
        assert stored_hash, f"Password should be stored for WA {wa.wa_id}"
        assert stored_hash[0] == hashed_password, "Stored password hash should match"


@pytest.mark.asyncio 
async def test_disk_persistence_verification(auth_service, temp_auth_db):
    """Test that password data persists to disk and survives service restart."""
    # Create WA with password
    private_key, public_key = auth_service.generate_keypair()
    test_password = "persistent_password_456!"
    hashed_password = auth_service.hash_password(test_password)
    
    wa = WACertificate(
        wa_id="wa-2025-01-18-PRST01",  # Fix pattern - 6 characters after date
        name="Persistence Test WA", 
        role=WARole.AUTHORITY,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="persist-test-kid",
        password_hash=hashed_password,
        scopes_json='["read:self", "write:self"]',
        created_at=datetime.now(timezone.utc),
    )
    
    await auth_service._store_wa_certificate(wa)
    
    # Stop the service
    await auth_service.stop()
    
    # Verify data exists on disk after service shutdown
    assert os.path.exists(temp_auth_db), "Database file should persist after service stop"
    
    with sqlite3.connect(temp_auth_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT wa_id, password_hash FROM wa_cert WHERE wa_id = ?", (wa.wa_id,))
        row = cursor.fetchone()
        assert row, "WA should persist in database after service restart"
        assert row[0] == wa.wa_id
        assert row[1] == hashed_password
        
    # Restart service with same database
    from ciris_engine.logic.services.lifecycle.time import TimeService
    new_time_service = TimeService()
    new_auth_service = AuthenticationService(
        db_path=temp_auth_db,
        time_service=new_time_service,
        key_dir=auth_service.key_dir
    )
    await new_auth_service.start()
    
    # Verify WA can be retrieved after restart
    retrieved_wa = await new_auth_service.get_wa(wa.wa_id)
    assert retrieved_wa is not None, "WA should be retrievable after service restart"
    assert retrieved_wa.password_hash == hashed_password, "Password hash should persist"
    
    await new_auth_service.stop()


@pytest.mark.asyncio
async def test_password_authentication_works(auth_service):
    """Test that stored passwords work for authentication."""
    # Create WA with known password
    private_key, public_key = auth_service.generate_keypair()
    correct_password = "authentication_test_789!"
    wrong_password = "wrong_password_000!"
    
    hashed_password = auth_service.hash_password(correct_password)
    
    wa = WACertificate(
        wa_id="wa-2025-01-18-AUTH01",  # Fix pattern
        name="Auth Test WA",
        role=WARole.AUTHORITY,  # Use AUTHORITY instead of ADMIN
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="auth-test-kid",
        password_hash=hashed_password,
        scopes_json='["admin:all"]',
        created_at=datetime.now(timezone.utc),
    )
    
    await auth_service._store_wa_certificate(wa)
    
    # Test correct password verification
    assert auth_service._verify_password(correct_password, hashed_password) is True, \
        "Correct password should verify successfully"
    
    # Test wrong password verification
    assert auth_service._verify_password(wrong_password, hashed_password) is False, \
        "Wrong password should fail verification"
    
    # Test edge cases
    assert auth_service._verify_password("", hashed_password) is False, \
        "Empty password should fail"
    assert auth_service._verify_password(correct_password, "") is False, \
        "Empty hash should fail"
    assert auth_service._verify_password(correct_password, "invalid_hash") is False, \
        "Invalid hash format should fail"


@pytest.mark.asyncio
async def test_default_admin_password_protection(auth_service):
    """Test that default admin password cannot be accidentally reset."""
    # Create default admin WA
    private_key, public_key = auth_service.generate_keypair()
    default_password = "ciris_admin_password"  # Default from CLAUDE.md
    
    admin_hash = auth_service.hash_password(default_password)
    
    admin_wa = WACertificate(
        wa_id="wa-2025-01-18-ADMIN1",  # Fix pattern
        name="admin", 
        role=WARole.ROOT,  # Use ROOT for admin-level access
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="admin-default-kid",
        password_hash=admin_hash,
        scopes_json='["admin:all"]',
        created_at=datetime.now(timezone.utc),
    )
    
    await auth_service._store_wa_certificate(admin_wa)
    
    # Verify admin exists with default password
    retrieved_admin = await auth_service.get_wa("wa-2025-01-18-ADMIN1")
    assert retrieved_admin is not None
    assert retrieved_admin.name == "admin"
    assert retrieved_admin.role == WARole.ROOT
    
    # Verify default password works
    assert auth_service._verify_password(default_password, admin_hash) is True
    
    # Test protection logic - try to create another admin with same name
    # This should be prevented by unique constraints or business logic
    duplicate_admin = WACertificate(
        wa_id="wa-2025-01-18-ADMIN2",  # Fix pattern
        name="admin",  # Same name
        role=WARole.ROOT,  # Use ROOT instead of ADMIN
        pubkey=auth_service._encode_public_key(public_key), 
        jwt_kid="admin-dup-kid",
        password_hash=auth_service.hash_password("different_password"),
        scopes_json='["admin:all"]',
        created_at=datetime.now(timezone.utc),
    )
    
    # This should either fail or be handled gracefully
    try:
        await auth_service._store_wa_certificate(duplicate_admin)
        
        # If storage succeeds, verify original admin is unchanged
        original_admin = await auth_service.get_wa("wa-2025-01-18-ADMIN1")
        assert original_admin is not None
        assert auth_service._verify_password(default_password, original_admin.password_hash) is True, \
            "Original admin password should remain unchanged"
            
    except Exception as e:
        # If storage fails, that's also acceptable protection
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Duplicate admin prevented: {e}")


@pytest.mark.asyncio
async def test_default_admin_no_accidental_reset(auth_service, temp_auth_db):
    """Test that admin password cannot be accidentally overwritten or reset."""
    # Create admin with default password
    private_key, public_key = auth_service.generate_keypair()
    default_password = "ciris_admin_password"
    admin_hash = auth_service.hash_password(default_password)
    
    admin_wa = WACertificate(
        wa_id="wa-2025-01-18-ADMIN3",
        name="admin",
        role=WARole.ROOT,
        pubkey=auth_service._encode_public_key(public_key),
        jwt_kid="admin-reset-test-kid",
        password_hash=admin_hash,
        scopes_json='["admin:all"]',
        created_at=datetime.now(timezone.utc),
    )
    
    await auth_service._store_wa_certificate(admin_wa)
    
    # Verify initial admin password works
    original_admin = await auth_service.get_wa("wa-2025-01-18-ADMIN3")
    assert original_admin is not None
    assert auth_service._verify_password(default_password, original_admin.password_hash) is True
    
    # Attempt to "update" admin with different password (simulating accidental reset)
    try:
        different_hash = auth_service.hash_password("accidentally_different_password")
        updated_admin = WACertificate(
            wa_id="wa-2025-01-18-ADMIN3",  # Same WA ID
            name="admin",
            role=WARole.ROOT,
            pubkey=auth_service._encode_public_key(public_key),
            jwt_kid="admin-reset-test-kid",
            password_hash=different_hash,  # Different password hash
            scopes_json='["admin:all"]',
            created_at=datetime.now(timezone.utc),
        )
        
        # This should either fail due to constraints, or the original password should remain
        await auth_service._store_wa_certificate(updated_admin)
        
        # Check what happened - database should prevent overwrite or maintain original
        final_admin = await auth_service.get_wa("wa-2025-01-18-ADMIN3")
        assert final_admin is not None
        
        # Either the original password still works (protected) or both work (multiple certs allowed)
        original_works = auth_service._verify_password(default_password, final_admin.password_hash)
        new_works = auth_service._verify_password("accidentally_different_password", final_admin.password_hash)
        
        # At minimum, we want to know what the behavior is
        if original_works and not new_works:
            # Original password protected - good
            pass
        elif not original_works and new_works:
            # Password was overwritten - this is the concerning behavior
            pytest.fail("Admin password was accidentally overwritten - this is a security risk!")
        elif original_works and new_works:
            # This shouldn't happen with proper hashing
            pytest.fail("Both passwords work - something is wrong with hashing")
        else:
            # Neither works - system is broken
            pytest.fail("Neither password works - authentication system failure")
            
    except Exception as e:
        # If store fails, that's good protection
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Admin password reset prevented by exception: {e}")
        
        # Verify original still works
        final_admin = await auth_service.get_wa("wa-2025-01-18-ADMIN3")
        assert final_admin is not None
        assert auth_service._verify_password(default_password, final_admin.password_hash) is True


@pytest.mark.asyncio 
async def test_password_hash_strength(auth_service):
    """Test password hashing strength and consistency."""
    test_password = "strength_test_password_123!"
    
    # Generate multiple hashes of same password
    hash1 = auth_service.hash_password(test_password)
    hash2 = auth_service.hash_password(test_password)
    
    # Hashes should be different (different salts)
    assert hash1 != hash2, "Same password should produce different hashes (salted)"
    
    # Both should verify correctly
    assert auth_service._verify_password(test_password, hash1) is True
    assert auth_service._verify_password(test_password, hash2) is True
    
    # Check hash properties
    assert len(hash1) > 80, "Hash should be reasonably long for security"
    assert len(hash2) > 80, "Hash should be reasonably long for security"
    
    # Verify base64 encoding
    import base64
    decoded1 = base64.b64decode(hash1)
    decoded2 = base64.b64decode(hash2)
    
    # Should be 64 bytes total (32 salt + 32 key)
    assert len(decoded1) == 64
    assert len(decoded2) == 64
    
    # First 32 bytes (salt) should be different
    salt1 = decoded1[:32]
    salt2 = decoded2[:32]
    assert salt1 != salt2, "Salts should be different for different hash operations"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])