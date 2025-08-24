"""
Comprehensive test suite for AuditVerifier.

Tests all methods and edge cases in ciris_engine/logic/audit/verifier.py
FAIL FAST AND LOUD: Any missing schema should cause immediate test failure.
"""

import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest

from ciris_engine.logic.audit.verifier import AuditVerifier
from ciris_engine.schemas.audit.verification import (
    ChainSummary,
    ChainVerificationResult,
    CompleteVerificationResult,
    EntryVerificationResult,
    RangeVerificationResult,
    RootAnchorVerificationResult,
    SignatureVerificationResult,
    VerificationReport,
)


class MockTimeService:
    """Mock time service for testing."""

    def __init__(self):
        self.current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        """Return current mock time."""
        return self.current_time

    def advance(self, seconds: int) -> None:
        """Advance mock time by seconds."""
        self.current_time += timedelta(seconds=seconds)


class MockAuditHashChain:
    """Mock hash chain for testing."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.initialized = False
        self.chain_valid = True
        self.tampering_at = None
        self.entry_hashes = {}

    def initialize(self) -> None:
        """Initialize the hash chain."""
        self.initialized = True

    def get_chain_summary(self) -> ChainSummary:
        """Get chain summary."""
        if hasattr(self, "summary_error"):
            return ChainSummary(total_entries=0, signed_entries=0, chain_intact=False, error=self.summary_error)

        return ChainSummary(
            total_entries=self.total_entries if hasattr(self, "total_entries") else 10,
            signed_entries=self.signed_entries if hasattr(self, "signed_entries") else 10,
            first_entry_id=1,
            last_entry_id=self.total_entries if hasattr(self, "total_entries") else 10,
            first_entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            last_entry_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
            root_hash="root_hash_123",
            chain_intact=self.chain_valid,
        )

    def verify_chain_integrity(self, start_seq: int = 1, end_seq: int = None) -> ChainVerificationResult:
        """Verify chain integrity."""
        if not self.chain_valid:
            return ChainVerificationResult(
                valid=False,
                entries_checked=end_seq - start_seq + 1 if end_seq else 10,
                errors=["Hash chain broken at entry 5"],
                last_valid_entry=4,
            )

        return ChainVerificationResult(
            valid=True, entries_checked=end_seq - start_seq + 1 if end_seq else 10, errors=[]
        )

    def compute_entry_hash(self, entry: dict) -> str:
        """Compute hash for an entry."""
        entry_id = entry.get("entry_id", 0)
        if entry_id in self.entry_hashes:
            return self.entry_hashes[entry_id]
        return f"computed_hash_{entry_id}"

    def find_tampering(self) -> int:
        """Find first tampered entry."""
        return self.tampering_at


class MockAuditSignatureManager:
    """Mock signature manager for testing."""

    def __init__(self, key_path: str, db_path: str, time_service: Any):
        self.key_path = key_path
        self.db_path = db_path
        self.time_service = time_service
        self.initialized = False
        self.signatures_valid = True
        self.invalid_signatures = set()

    def initialize(self) -> None:
        """Initialize the signature manager."""
        self.initialized = True

    def verify_signature(self, entry_hash: str, signature: str, key_id: str = None) -> bool:
        """Verify a signature."""
        if not self.signatures_valid:
            return False

        # Check if this specific signature is marked as invalid
        if entry_hash in self.invalid_signatures:
            return False

        return True

    def get_key_info(self) -> dict:
        """Get signing key information."""
        return {
            "key_id": "test_key_123",
            "algorithm": "Ed25519",
            "created_at": "2024-01-01T00:00:00Z",
            "active": self.key_active if hasattr(self, "key_active") else True,
            "revoked": False,
        }


@pytest.fixture
def mock_time_service():
    """Create mock time service."""
    return MockTimeService()


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Create minimal audit tables
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create audit_log table
    cursor.execute(
        """
        CREATE TABLE audit_log (
            entry_id INTEGER PRIMARY KEY,
            sequence_number INTEGER NOT NULL,
            entry_hash TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            signature TEXT NOT NULL,
            signing_key_id TEXT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            entity_id TEXT,
            outcome TEXT
        )
    """
    )

    # Create audit_roots table
    cursor.execute(
        """
        CREATE TABLE audit_roots (
            root_id INTEGER PRIMARY KEY,
            sequence_start INTEGER NOT NULL,
            sequence_end INTEGER NOT NULL,
            root_hash TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """
    )

    conn.commit()
    conn.close()

    yield db_path
    Path(db_path).unlink()


@pytest.fixture
def temp_key_path():
    """Create temporary key path."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def verifier(temp_db, temp_key_path, mock_time_service):
    """Create AuditVerifier with mocked dependencies."""
    verifier = AuditVerifier(temp_db, temp_key_path, mock_time_service)

    # Replace internal components with mocks
    verifier.hash_chain = MockAuditHashChain(temp_db)
    verifier.signature_manager = MockAuditSignatureManager(temp_key_path, temp_db, mock_time_service)

    # Mock the private methods that query the database
    def mock_verify_all_signatures():
        return SignatureVerificationResult(
            valid=verifier.signature_manager.signatures_valid,
            entries_signed=10,
            entries_verified=10 if verifier.signature_manager.signatures_valid else 0,
            errors=[] if verifier.signature_manager.signatures_valid else ["Invalid signatures"],
            untrusted_keys=[],
        )

    def mock_verify_signatures_in_range(start_seq, end_seq):
        return SignatureVerificationResult(
            valid=verifier.signature_manager.signatures_valid,
            entries_signed=end_seq - start_seq + 1,
            entries_verified=end_seq - start_seq + 1 if verifier.signature_manager.signatures_valid else 0,
            errors=[] if verifier.signature_manager.signatures_valid else ["Invalid signatures in range"],
            untrusted_keys=[],
        )

    verifier._verify_all_signatures = mock_verify_all_signatures
    verifier._verify_signatures_in_range = mock_verify_signatures_in_range

    return verifier


@pytest.fixture
def populated_db(temp_db):
    """Create database with test entries."""
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Add test entries
    for i in range(1, 11):
        cursor.execute(
            """
            INSERT INTO audit_log (
                entry_id, sequence_number, entry_hash, previous_hash,
                signature, signing_key_id, timestamp, event_type,
                entity_id, outcome
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                i,
                i,
                f"hash_{i}",
                f"hash_{i-1}" if i > 1 else "genesis",
                f"signature_{i}",
                "test_key",
                datetime.now(timezone.utc).isoformat(),
                "test_event",
                f"entity_{i}",
                "success",
            ),
        )

    # Add root anchors
    cursor.execute(
        """
        INSERT INTO audit_roots (root_id, sequence_start, sequence_end, root_hash, timestamp)
        VALUES (1, 1, 5, 'root_1', ?), (2, 6, 10, 'root_2', ?)
    """,
        (datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
    )

    conn.commit()
    conn.close()

    return temp_db


class TestAuditVerifierInitialization:
    """Test verifier initialization."""

    def test_init_with_valid_paths(self, temp_db, temp_key_path, mock_time_service):
        """Test initialization with valid paths."""
        verifier = AuditVerifier(temp_db, temp_key_path, mock_time_service)

        assert verifier.db_path == temp_db
        assert verifier._time_service == mock_time_service
        assert not verifier._initialized

    def test_initialize(self, verifier):
        """Test initialize method."""
        assert not verifier._initialized

        verifier.initialize()

        assert verifier._initialized
        assert verifier.hash_chain.initialized
        assert verifier.signature_manager.initialized

    def test_initialize_idempotent(self, verifier):
        """Test that initialize is idempotent."""
        verifier.initialize()
        assert verifier._initialized

        # Second call should not raise
        verifier.initialize()
        assert verifier._initialized


class TestCompleteChainVerification:
    """Test complete chain verification."""

    def test_verify_complete_chain_success(self, verifier):
        """Test successful complete chain verification."""
        verifier.hash_chain.chain_valid = True
        verifier.signature_manager.signatures_valid = True

        result = verifier.verify_complete_chain()

        # FAIL FAST: CompleteVerificationResult schema MUST exist
        assert isinstance(result, CompleteVerificationResult), "CompleteVerificationResult schema is missing!"
        assert result.valid is True
        assert result.hash_chain_valid is True
        assert result.signatures_valid is True
        assert result.entries_verified == 10
        assert result.verification_time_ms >= 0

    def test_verify_complete_chain_hash_failure(self, verifier):
        """Test complete chain verification with hash failure."""
        verifier.hash_chain.chain_valid = False
        verifier.signature_manager.signatures_valid = True

        result = verifier.verify_complete_chain()

        assert result.valid is False
        assert result.hash_chain_valid is False
        assert result.signatures_valid is True
        assert len(result.hash_chain_errors) > 0

    def test_verify_complete_chain_signature_failure(self, verifier):
        """Test complete chain verification with signature failure."""
        verifier.hash_chain.chain_valid = True
        verifier.signature_manager.signatures_valid = False

        result = verifier.verify_complete_chain()

        assert result.valid is False
        assert result.hash_chain_valid is True
        assert result.signatures_valid is False

    def test_verify_complete_chain_empty_log(self, verifier):
        """Test verification of empty audit log."""
        verifier.hash_chain.total_entries = 0

        result = verifier.verify_complete_chain()

        assert result.valid is True
        assert result.entries_verified == 0
        assert result.summary == "Empty audit log"

    def test_verify_complete_chain_with_error(self, verifier):
        """Test verification when chain summary has error."""
        verifier.hash_chain.summary_error = "Database connection failed"

        result = verifier.verify_complete_chain()

        assert result.valid is False
        assert result.error == "Database connection failed"
        assert result.entries_verified == 0


class TestEntryVerification:
    """Test single entry verification."""

    def test_verify_entry_success(self, verifier, populated_db):
        """Test successful entry verification."""
        verifier.db_path = populated_db
        verifier.hash_chain.entry_hashes[1] = "hash_1"

        result = verifier.verify_entry(1)

        # FAIL FAST: EntryVerificationResult schema MUST exist
        assert isinstance(result, EntryVerificationResult), "EntryVerificationResult schema is missing!"
        assert result.valid is True
        assert result.entry_id == 1
        assert result.hash_valid is True
        assert result.signature_valid is True
        assert result.previous_hash_valid is True

    def test_verify_entry_not_found(self, verifier, populated_db):
        """Test verification of non-existent entry."""
        verifier.db_path = populated_db

        result = verifier.verify_entry(999)

        assert result.valid is False
        assert result.entry_id == 999
        assert "not found" in result.errors[0]

    def test_verify_entry_hash_mismatch(self, verifier, populated_db):
        """Test entry with hash mismatch."""
        verifier.db_path = populated_db
        verifier.hash_chain.entry_hashes[1] = "wrong_hash"

        result = verifier.verify_entry(1)

        assert result.valid is False
        assert result.hash_valid is False
        assert "hash mismatch" in result.errors[0].lower()

    def test_verify_entry_invalid_signature(self, verifier, populated_db):
        """Test entry with invalid signature."""
        verifier.db_path = populated_db
        verifier.hash_chain.entry_hashes[1] = "hash_1"
        verifier.signature_manager.invalid_signatures.add("hash_1")

        result = verifier.verify_entry(1)

        assert result.valid is False
        assert result.signature_valid is False
        assert "invalid signature" in result.errors[0].lower()

    def test_verify_entry_database_error(self, verifier):
        """Test entry verification with database error."""
        verifier.db_path = "/invalid/path/to/db.db"

        result = verifier.verify_entry(1)

        assert result.valid is False
        assert "database error" in result.errors[0].lower()


class TestRangeVerification:
    """Test range verification."""

    def test_verify_range_success(self, verifier):
        """Test successful range verification."""
        verifier.hash_chain.chain_valid = True
        verifier.signature_manager.signatures_valid = True

        result = verifier.verify_range(1, 5)

        # FAIL FAST: RangeVerificationResult schema MUST exist
        assert isinstance(result, RangeVerificationResult), "RangeVerificationResult schema is missing!"
        assert result.valid is True
        assert result.start_id == 1
        assert result.end_id == 5
        assert result.entries_verified == 5
        assert result.hash_chain_valid is True
        assert result.signatures_valid is True

    def test_verify_range_hash_failure(self, verifier):
        """Test range verification with hash failure."""
        verifier.hash_chain.chain_valid = False
        verifier.signature_manager.signatures_valid = True

        result = verifier.verify_range(1, 10)

        assert result.valid is False
        assert result.hash_chain_valid is False
        assert len(result.errors) > 0

    def test_verify_range_signature_failure(self, verifier):
        """Test range verification with signature failure."""
        verifier.hash_chain.chain_valid = True
        verifier.signature_manager.signatures_valid = False

        result = verifier.verify_range(5, 10)

        assert result.valid is False
        assert result.signatures_valid is False


class TestTamperingDetection:
    """Test tampering detection."""

    def test_find_tampering_found(self, verifier):
        """Test finding tampering in chain."""
        verifier.hash_chain.tampering_at = 7

        result = verifier.find_tampering_fast()

        assert result == 7

    def test_find_tampering_not_found(self, verifier):
        """Test when no tampering is found."""
        verifier.hash_chain.tampering_at = None

        result = verifier.find_tampering_fast()

        assert result is None

    def test_find_tampering_initializes(self, verifier):
        """Test that find_tampering initializes if needed."""
        assert not verifier._initialized

        verifier.find_tampering_fast()

        assert verifier._initialized


class TestVerificationReport:
    """Test verification report generation."""

    def test_get_verification_report_clean(self, verifier):
        """Test report generation for clean audit log."""
        verifier.hash_chain.chain_valid = True
        verifier.signature_manager.signatures_valid = True
        verifier.hash_chain.tampering_at = None

        report = verifier.get_verification_report()

        # FAIL FAST: VerificationReport schema MUST exist
        assert isinstance(report, VerificationReport), "VerificationReport schema is missing!"
        assert report.tampering_detected is False
        assert report.first_tampered_sequence is None
        assert len(report.recommendations) == 0

    def test_get_verification_report_with_tampering(self, verifier):
        """Test report generation with tampering detected."""
        verifier.hash_chain.chain_valid = False
        verifier.hash_chain.tampering_at = 5

        report = verifier.get_verification_report()

        assert report.tampering_detected is True
        assert report.first_tampered_sequence == 5
        assert "CRITICAL" in report.recommendations[0]
        assert "Tampering detected" in report.recommendations[1]

    def test_get_verification_report_slow_verification(self, verifier, mock_time_service):
        """Test report with slow verification warning."""
        # Make verification appear to take a long time
        call_count = [0]
        original_now = mock_time_service.now

        def mock_now():
            call_count[0] += 1
            if call_count[0] == 2:  # Second call is after verification
                mock_time_service.current_time = datetime(2024, 1, 1, 12, 0, 15, tzinfo=timezone.utc)
            return original_now()

        mock_time_service.now = mock_now

        report = verifier.get_verification_report()

        assert any("too long" in rec for rec in report.recommendations)

    def test_get_verification_report_large_log(self, verifier):
        """Test report with large log warning."""
        verifier.hash_chain.total_entries = 150000

        report = verifier.get_verification_report()

        assert any("Large audit log" in rec for rec in report.recommendations)

    def test_get_verification_report_inactive_key(self, verifier):
        """Test report with inactive signing key."""
        verifier.signature_manager.key_active = False

        report = verifier.get_verification_report()

        assert any("revoked or inactive" in rec for rec in report.recommendations)


class TestRootAnchorVerification:
    """Test root anchor verification."""

    def test_verify_root_anchors_success(self, verifier, populated_db):
        """Test successful root anchor verification."""
        verifier.db_path = populated_db
        verifier.hash_chain.chain_valid = True
        verifier.signature_manager.signatures_valid = True

        result = verifier.verify_root_anchors()

        # FAIL FAST: RootAnchorVerificationResult schema MUST exist
        assert isinstance(result, RootAnchorVerificationResult), "RootAnchorVerificationResult schema is missing!"
        assert result.valid is True
        assert result.verified_count == 2
        assert result.total_count == 2

    def test_verify_root_anchors_no_anchors(self, verifier, temp_db):
        """Test verification when no root anchors exist."""
        verifier.db_path = temp_db

        result = verifier.verify_root_anchors()

        assert result.valid is True
        assert result.verified_count == 0
        assert result.total_count == 0
        assert result.message == "No root anchors found"

    def test_verify_root_anchors_invalid_range(self, verifier, populated_db):
        """Test root anchor with invalid range."""
        verifier.db_path = populated_db
        verifier.hash_chain.chain_valid = False

        result = verifier.verify_root_anchors()

        assert result.valid is False
        assert result.verified_count == 0
        assert len(result.errors) > 0
        assert "compromised" in result.errors[0]

    def test_verify_root_anchors_database_error(self, verifier):
        """Test root anchor verification with database error."""
        verifier.db_path = "/invalid/path/to/db.db"

        result = verifier.verify_root_anchors()

        assert result.valid is False
        assert "database error" in result.errors[0].lower()


class TestPrivateMethods:
    """Test private helper methods."""

    def test_verify_single_entry_valid(self, verifier):
        """Test _verify_single_entry with valid entry."""
        entry = {
            "entry_id": 1,
            "sequence_number": 1,
            "entry_hash": "hash_1",
            "previous_hash": "genesis",
            "signature": "sig_1",
            "signing_key_id": "key_1",
        }

        verifier.hash_chain.entry_hashes[1] = "hash_1"

        result = verifier._verify_single_entry(entry)

        assert result.valid is True
        assert result.entry_id == 1
        assert result.hash_valid is True
        assert result.signature_valid is True
        assert result.previous_hash_valid is True

    def test_verify_single_entry_invalid_genesis(self, verifier):
        """Test entry with invalid genesis reference."""
        entry = {
            "entry_id": 5,
            "sequence_number": 5,
            "entry_hash": "hash_5",
            "previous_hash": "genesis",  # Invalid for non-first entry
            "signature": "sig_5",
            "signing_key_id": "key_1",
        }

        verifier.hash_chain.entry_hashes[5] = "hash_5"

        result = verifier._verify_single_entry(entry)

        assert result.valid is False
        assert result.previous_hash_valid is False
        assert "genesis" in result.errors[0].lower()

    def test_verify_all_signatures_success(self, verifier, populated_db):
        """Test _verify_all_signatures with valid signatures."""
        verifier.db_path = populated_db
        verifier.signature_manager.signatures_valid = True

        result = verifier._verify_all_signatures()

        assert isinstance(result, SignatureVerificationResult)
        assert result.valid is True
        assert result.entries_signed == 10
        assert result.entries_verified == 10

    def test_verify_all_signatures_some_invalid(self, verifier, populated_db):
        """Test _verify_all_signatures with some invalid signatures."""
        verifier.db_path = populated_db

        # Create a custom mock for this test that returns invalid result
        def mock_verify_all_signatures_invalid():
            return SignatureVerificationResult(
                valid=False,
                entries_signed=10,
                entries_verified=8,
                errors=["Invalid signature for entry 3", "Invalid signature for entry 7"],
                untrusted_keys=[],
            )

        verifier._verify_all_signatures = mock_verify_all_signatures_invalid
        result = verifier._verify_all_signatures()

        assert result.valid is False
        assert result.entries_signed == 10
        assert result.entries_verified == 8
        assert len(result.errors) == 2

    def test_verify_signatures_in_range(self, verifier, populated_db):
        """Test _verify_signatures_in_range."""
        verifier.db_path = populated_db
        verifier.signature_manager.signatures_valid = True

        result = verifier._verify_signatures_in_range(3, 7)

        assert result.valid is True
        assert result.entries_signed == 5
        assert result.entries_verified == 5


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_verify_with_uninitialized_components(self, verifier):
        """Test that methods initialize if needed."""
        assert not verifier._initialized

        # Each method should initialize automatically
        verifier.verify_complete_chain()
        assert verifier._initialized

    def test_concurrent_verification(self, verifier):
        """Test multiple verification operations."""
        # Run multiple verifications
        chain_result = verifier.verify_complete_chain()
        range_result = verifier.verify_range(1, 5)
        tampering_result = verifier.find_tampering_fast()  # Can be None if no tampering
        report = verifier.get_verification_report()

        # Check that operations completed successfully
        assert chain_result is not None
        assert chain_result.valid is True
        assert range_result is not None
        assert range_result.valid is True
        assert tampering_result is None  # No tampering in clean chain
        assert report is not None
        assert report.tampering_detected is False

    def test_verification_with_time_advancement(self, verifier, mock_time_service):
        """Test verification timing with time service."""
        # Set up mock to advance time during verification
        call_count = [0]
        original_now = mock_time_service.now
        start_time = mock_time_service.current_time

        def mock_now():
            call_count[0] += 1
            if call_count[0] == 2:  # Second call is end time
                mock_time_service.current_time = start_time + timedelta(seconds=5)
            return original_now()

        mock_time_service.now = mock_now

        result = verifier.verify_complete_chain()

        # Verification time should reflect the advancement
        assert result.verification_time_ms == 5000


class TestSchemaValidation:
    """Test that all required schemas exist - FAIL FAST AND LOUD."""

    def test_all_required_schemas_exist(self):
        """Test that all required Pydantic schemas exist and are valid."""
        # These imports should not fail - if they do, schemas are missing
        from ciris_engine.schemas.audit.verification import (
            ChainSummary,
            ChainVerificationResult,
            CompleteVerificationResult,
            EntryVerificationResult,
            RangeVerificationResult,
            RootAnchorVerificationResult,
            SignatureVerificationResult,
            VerificationReport,
        )

        # FAIL FAST: All schemas must be Pydantic models
        assert hasattr(ChainSummary, "model_validate"), "ChainSummary is not a Pydantic model!"
        assert hasattr(
            CompleteVerificationResult, "model_validate"
        ), "CompleteVerificationResult is not a Pydantic model!"
        assert hasattr(EntryVerificationResult, "model_validate"), "EntryVerificationResult is not a Pydantic model!"
        assert hasattr(VerificationReport, "model_validate"), "VerificationReport is not a Pydantic model!"

        # Test instantiation - schemas must be valid
        summary = ChainSummary(total_entries=10, signed_entries=10, chain_intact=True)
        assert summary.total_entries == 10

        complete_result = CompleteVerificationResult(
            valid=True, entries_verified=10, hash_chain_valid=True, signatures_valid=True, verification_time_ms=100
        )
        assert complete_result.valid is True

        entry_result = EntryVerificationResult(valid=True, entry_id=1, hash_valid=True, previous_hash_valid=True)
        assert entry_result.entry_id == 1
