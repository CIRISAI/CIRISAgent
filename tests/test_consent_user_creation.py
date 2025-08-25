"""
Regression test for consent creation with user nodes.

Ensures that when a USER node is created, a TEMPORARY consent is automatically created.
This is a critical requirement for GDPR compliance.
"""

import tempfile
from datetime import timedelta

import pytest

from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.persistence.models.graph import add_graph_node, get_graph_node
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


class TestConsentUserCreation:
    """Test automatic consent creation for new users."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
            db_path = tmp_db.name
            initialize_database(db_path)
            yield db_path
            # Cleanup happens automatically when file is deleted

    @pytest.fixture
    def time_service(self):
        """Provide a time service instance."""
        return TimeService()

    def test_user_node_creates_temporary_consent(self, temp_db, time_service):
        """Test that creating a USER node automatically creates TEMPORARY consent."""
        # Create a new USER node
        user_id = "test_user_123"
        user_node = GraphNode(
            id=user_id,
            type=NodeType.USER,
            scope=GraphScope.LOCAL,
            attributes={"name": "Test User", "created_at": time_service.now().isoformat()},
            updated_by="test_script",
            updated_at=time_service.now(),
        )

        # Add the user node
        add_graph_node(user_node, time_service=time_service, db_path=temp_db)

        # Check if consent node was created
        consent_id = f"consent_{user_id}"
        consent_node = get_graph_node(consent_id, GraphScope.LOCAL, db_path=temp_db)

        # Verify consent was created
        assert consent_node is not None, "Consent node should be created automatically"
        assert consent_node.type == NodeType.CONSENT
        assert consent_node.attributes.get("user_id") == user_id
        assert consent_node.attributes.get("stream") == "temporary"
        assert "expires_at" in consent_node.attributes
        assert "granted_at" in consent_node.attributes
        assert consent_node.attributes.get("reason") == "Default TEMPORARY consent on user creation"

    def test_updating_user_does_not_duplicate_consent(self, temp_db, time_service):
        """Test that updating an existing user doesn't create duplicate consent."""
        # Create a new USER node
        user_id = "test_user_456"
        user_node = GraphNode(
            id=user_id,
            type=NodeType.USER,
            scope=GraphScope.LOCAL,
            attributes={"name": "Test User"},
            updated_by="test_script",
            updated_at=time_service.now(),
        )

        # Add the user node (should create consent)
        add_graph_node(user_node, time_service=time_service, db_path=temp_db)

        # Get the initial consent
        consent_id = f"consent_{user_id}"
        initial_consent = get_graph_node(consent_id, GraphScope.LOCAL, db_path=temp_db)
        assert initial_consent is not None
        initial_granted_at = initial_consent.attributes.get("granted_at")

        # Update the user node
        user_node.attributes["updated"] = "true"
        add_graph_node(user_node, time_service=time_service, db_path=temp_db)

        # Verify consent still exists and wasn't recreated
        updated_consent = get_graph_node(consent_id, GraphScope.LOCAL, db_path=temp_db)
        assert updated_consent is not None
        assert (
            updated_consent.attributes.get("granted_at") == initial_granted_at
        ), "Consent should not be recreated on user update"

    def test_non_user_nodes_do_not_create_consent(self, temp_db, time_service):
        """Test that non-USER nodes don't trigger consent creation."""
        # Create a CONCEPT node
        concept_node = GraphNode(
            id="test_concept_789",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={"description": "Test concept"},
            updated_by="test_script",
            updated_at=time_service.now(),
        )

        # Add the concept node
        add_graph_node(concept_node, time_service=time_service, db_path=temp_db)

        # Check that no consent was created
        consent_id = f"consent_test_concept_789"
        consent_node = get_graph_node(consent_id, GraphScope.LOCAL, db_path=temp_db)

        assert consent_node is None, "Consent should not be created for non-USER nodes"

    def test_consent_has_correct_expiry(self, temp_db, time_service):
        """Test that TEMPORARY consent has 14-day expiry."""
        # Create a new USER node
        user_id = "test_user_expiry"
        user_node = GraphNode(
            id=user_id,
            type=NodeType.USER,
            scope=GraphScope.LOCAL,
            attributes={"name": "Test User"},
            updated_by="test_script",
            updated_at=time_service.now(),
        )

        # Add the user node
        add_graph_node(user_node, time_service=time_service, db_path=temp_db)

        # Check consent expiry
        consent_id = f"consent_{user_id}"
        consent_node = get_graph_node(consent_id, GraphScope.LOCAL, db_path=temp_db)

        assert consent_node is not None

        # Parse timestamps
        from datetime import datetime

        granted_at = datetime.fromisoformat(consent_node.attributes["granted_at"])
        expires_at = datetime.fromisoformat(consent_node.attributes["expires_at"])

        # Verify 14-day expiry
        expiry_delta = expires_at - granted_at
        assert 13 <= expiry_delta.days <= 14, "TEMPORARY consent should expire in 14 days"


def test_consent_metadata_definitions():
    """Test that consent metadata dictionaries are properly defined."""
    from ciris_engine.logic.adapters.api.routes.consent import (
        STREAM_METADATA,
        CATEGORY_METADATA,
        ConsentStream,
        ConsentCategory
    )
    
    # Test all streams have metadata
    for stream in ConsentStream:
        assert stream in STREAM_METADATA
        metadata = STREAM_METADATA[stream]
        assert "name" in metadata
        assert "description" in metadata
    
    # Test all categories have metadata
    for category in ConsentCategory:
        assert category in CATEGORY_METADATA
        metadata = CATEGORY_METADATA[category]
        assert "name" in metadata
        assert "description" in metadata
    
    # Test specific metadata values
    assert STREAM_METADATA[ConsentStream.TEMPORARY]["duration_days"] == 14
    assert STREAM_METADATA[ConsentStream.PARTNERED].get("requires_categories") is True
    assert CATEGORY_METADATA[ConsentCategory.INTERACTION]["name"] == "Interaction"
