import pytest
from pydantic import ValidationError
from datetime import datetime, timezone

# We will test the schemas that we expect to exist in ciris_engine.schemas.dsar
# Since the file doesn't exist yet, we can't import them directly.
# But we can define the tests based on what we *expect* to import.

def test_datasource_export_schema_structure():
    """Test that DataSourceExport schema has required fields including signature."""
    # This import will fail until we implement the file
    try:
        from ciris_engine.schemas.dsar import DataSourceExport
    except ImportError:
        pytest.fail("Could not import DataSourceExport from ciris_engine.schemas.dsar")

    now = datetime.now(timezone.utc).isoformat()
    
    # Valid instantiation
    export = DataSourceExport(
        source_id="sql_db_1",
        source_type="sql",
        source_name="Production DB",
        export_timestamp=now,
        signature="mock_signature_ed25519"  # This is the new requirement
    )
    
    assert export.source_id == "sql_db_1"
    assert export.signature == "mock_signature_ed25519"

def test_datasource_deletion_schema_structure():
    """Test that DataSourceDeletion schema has required fields including signature."""
    try:
        from ciris_engine.schemas.dsar import DataSourceDeletion
    except ImportError:
        pytest.fail("Could not import DataSourceDeletion from ciris_engine.schemas.dsar")
        
    now = datetime.now(timezone.utc).isoformat()
    
    # Valid instantiation
    deletion = DataSourceDeletion(
        source_id="sql_db_1",
        source_type="sql",
        success=True,
        deletion_timestamp=now,
        signature="mock_signature_ed25519"
    )
    
    assert deletion.success is True
    assert deletion.signature == "mock_signature_ed25519"

def test_multisource_access_package_structure():
    """Test aggregated access package structure."""
    try:
        from ciris_engine.schemas.dsar import MultiSourceDSARAccessPackage, DataSourceExport
        from ciris_engine.schemas.consent.core import DSARAccessPackage, ConsentStatus, ConsentStream, ConsentImpactReport
    except ImportError:
        pytest.fail("Could not import schemas")

    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.isoformat()

    # Mock inner CIRIS data
    ciris_data = DSARAccessPackage(
        user_id="test_user",
        request_id="req_123",
        generated_at=now_dt,
        consent_status=ConsentStatus(
            user_id="test_user",
            stream=ConsentStream.TEMPORARY,
            categories=[],
            granted_at=now_dt,
            last_modified=now_dt,
        ),
        consent_history=[],
        interaction_summary={},
        contribution_metrics=ConsentImpactReport(
            user_id="test_user",
            total_interactions=0,
            patterns_contributed=0,
            users_helped=0,
            categories_active=[],
            impact_score=0.0,
            example_contributions=[],
        ),
        data_categories=[],
        retention_periods={},
        processing_purposes=[],
    )

    package = MultiSourceDSARAccessPackage(
        request_id="req_123",
        user_identifier="test_user",
        ciris_data=ciris_data,
        external_sources=[],
        generated_at=now_str,
        signature="pkg_signature_ed25519" # New requirement
    )
    
    assert package.signature == "pkg_signature_ed25519"
