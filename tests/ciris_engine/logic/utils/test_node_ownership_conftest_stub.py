"""The conftest "owned" stub: the only "owned" answer without a node, and only under pytest."""

import pytest

from ciris_engine.logic.runtime import node_fold
from ciris_engine.logic.utils import node_ownership
from ciris_engine.schemas.runtime.node_ownership import NodeOwnershipReading


@pytest.mark.asyncio
async def test_unmarked_tests_get_the_explicit_stub_owner() -> None:
    assert node_fold.fold_status() is None, "the suite runs fold-off"
    state = await node_ownership.node_owned(fresh=True)
    assert state.reading == NodeOwnershipReading.OWNED and not state.unclaimed
    assert state.owner_key_id == "pytest-stub-owner", "an owner without a node must be the named pytest stub"
