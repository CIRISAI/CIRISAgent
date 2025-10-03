import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.services.memory_service import LocalGraphMemoryService
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery


@pytest.mark.asyncio
async def test_memory_operations():
    # Create a temporary database file (not :memory:)
    # because :memory: creates separate databases per connection
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        db_path = tmp_file.name

    try:
        # Create mock dependencies
        mock_secrets_service = Mock()
        # Return the JSON string and empty secret refs
        mock_secrets_service.process_incoming_text = AsyncMock(return_value=('{"value": "test_data"}', []))
        mock_secrets_service.process_outgoing_data = AsyncMock(return_value={"value": "test_data"})

        mock_time_service = Mock()
        mock_time_service.now = Mock(return_value=datetime.now(timezone.utc))

        memory = LocalGraphMemoryService(db_path, secrets_service=mock_secrets_service, time_service=mock_time_service)
        await memory.start()

        # Test memorize
        node = GraphNode(
            id="test_key", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={"value": "test_data"}
        )
        result = await memory.memorize(node)
        assert result.status.value == "ok"

        # Test recall
        recall_query = MemoryQuery(
            node_id="test_key", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, include_edges=False, depth=1
        )
        results = await memory.recall(recall_query)
        assert len(results) == 1
        assert results[0].id == "test_key"
        assert results[0].attributes["value"] == "test_data"

        # Test forget - forget takes a GraphNode (now async)
        forget_node = GraphNode(id="test_key", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={})
        result = await memory.forget(forget_node)
        assert result.status.value == "ok"

        await memory.stop()
    finally:
        # Clean up the temporary file
        if os.path.exists(db_path):
            os.unlink(db_path)
