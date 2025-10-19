"""Test that memory_service logs warnings when secrets_service is None."""

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType


@pytest.mark.asyncio
async def test_memorize_warns_when_secrets_service_none(caplog, tmp_path):
    """Test that _process_secrets_for_memorize logs warning when secrets_service is None."""
    # Create memory service WITHOUT secrets_service
    db_path = str(tmp_path / "test.db")
    time_service = MagicMock()
    time_service.now.return_value = datetime.now(timezone.utc)

    memory_service = LocalGraphMemoryService(
        db_path=db_path,
        secrets_service=None,  # No secrets service
        time_service=time_service,
    )
    await memory_service.start()

    # Create a node to memorize
    node = GraphNode(
        id="test_node",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes=GraphNodeAttributes(
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by="test",
            tags=["test"],
        ),
        updated_by="test",
        updated_at=datetime.now(timezone.utc),
    )

    # Capture logs
    with caplog.at_level(logging.WARNING):
        result = await memory_service.memorize(node)

    # Verify success
    assert result.status.value == "ok"

    # Verify warning was logged
    assert any(
        "Secrets service unavailable for memorize operation" in record.message and record.levelname == "WARNING"
        for record in caplog.records
    ), f"Expected warning about secrets service unavailable. Got: {[r.message for r in caplog.records]}"

    await memory_service.stop()


@pytest.mark.asyncio
async def test_recall_no_warning_without_secret_refs(caplog, tmp_path):
    """Test that _process_secrets_for_recall does NOT warn when there are no secret_refs."""
    # Create memory service WITHOUT secrets_service
    db_path = str(tmp_path / "test.db")
    time_service = MagicMock()
    time_service.now.return_value = datetime.now(timezone.utc)

    memory_service = LocalGraphMemoryService(
        db_path=db_path,
        secrets_service=None,  # No secrets service
        time_service=time_service,
    )
    await memory_service.start()

    # Create attributes WITHOUT secret_refs
    attributes_without_refs = {"test": "data", "value": 123}

    # Capture logs
    with caplog.at_level(logging.WARNING):
        # Directly call _process_secrets_for_recall
        result = await memory_service._process_secrets_for_recall(attributes_without_refs, "speak")

    # Verify result is unchanged dict
    assert result == attributes_without_refs

    # Verify NO warning was logged (because there are no secret_refs to decrypt)
    warnings_about_secrets = [
        record
        for record in caplog.records
        if "Secrets service unavailable" in record.message and record.levelname == "WARNING"
    ]
    assert len(warnings_about_secrets) == 0, f"Should not have warnings when no secret_refs: {warnings_about_secrets}"

    await memory_service.stop()


@pytest.mark.asyncio
async def test_no_warning_when_secrets_service_present(caplog, tmp_path):
    """Test that NO warning is logged when secrets_service is present."""
    from unittest.mock import AsyncMock

    # Create memory service WITH secrets_service
    db_path = str(tmp_path / "test.db")
    time_service = MagicMock()
    time_service.now.return_value = datetime.now(timezone.utc)

    mock_secrets = MagicMock()
    # Use AsyncMock for async method
    mock_secrets.process_incoming_text = AsyncMock(return_value=('{"test": "data"}', []))

    memory_service = LocalGraphMemoryService(
        db_path=db_path,
        secrets_service=mock_secrets,  # Secrets service present
        time_service=time_service,
    )
    await memory_service.start()

    # Create a node to memorize
    node = GraphNode(
        id="test_node",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes=GraphNodeAttributes(
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by="test",
            tags=["test"],
        ),
        updated_by="test",
        updated_at=datetime.now(timezone.utc),
    )

    # Capture logs
    with caplog.at_level(logging.WARNING):
        result = await memory_service.memorize(node)

    # Verify success
    assert result.status.value == "ok"

    # Verify NO warning was logged about secrets service
    warnings_about_secrets = [
        record
        for record in caplog.records
        if "Secrets service unavailable" in record.message and record.levelname == "WARNING"
    ]
    assert (
        len(warnings_about_secrets) == 0
    ), f"Should not have warnings when secrets_service present: {warnings_about_secrets}"

    await memory_service.stop()
