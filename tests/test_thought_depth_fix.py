"""Test for thought depth max=7 prevention fix."""
import pytest
from datetime import datetime, timezone
from ciris_engine.logic.infrastructure.handlers.helpers import create_follow_up_thought
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.runtime.enums import ThoughtStatus, ThoughtType


class MockTimeService:
    """Mock time service for testing."""
    def now(self):
        return datetime.now(timezone.utc)


def test_thought_depth_increases_correctly():
    """Test that thought depth increases by 1 for each follow-up."""
    time_service = MockTimeService()
    
    # Create initial thought at depth 0
    parent = Thought(
        thought_id="test-thought-0",
        source_task_id="test-task",
        thought_type=ThoughtType.STANDARD,
        status=ThoughtStatus.PENDING,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        round_number=1,
        content="Initial thought",
        thought_depth=0
    )
    
    # Create follow-up at depth 1
    follow_up = create_follow_up_thought(parent, time_service, "Follow-up 1")
    assert follow_up.thought_depth == 1
    assert follow_up.parent_thought_id == parent.thought_id
    
    # Create follow-up at depth 2
    follow_up2 = create_follow_up_thought(follow_up, time_service, "Follow-up 2")
    assert follow_up2.thought_depth == 2
    assert follow_up2.parent_thought_id == follow_up.thought_id


def test_thought_depth_capped_at_7():
    """Test that thought depth is capped at 7."""
    time_service = MockTimeService()
    
    # Create thought at depth 6
    parent = Thought(
        thought_id="test-thought-6",
        source_task_id="test-task",
        thought_type=ThoughtType.STANDARD,
        status=ThoughtStatus.PENDING,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        round_number=1,
        content="Thought at depth 6",
        thought_depth=6
    )
    
    # Should create follow-up at depth 7
    follow_up = create_follow_up_thought(parent, time_service, "Follow-up at max depth")
    assert follow_up.thought_depth == 7


def test_thought_depth_7_prevents_follow_up():
    """Test that thoughts at depth 7 stay capped at 7."""
    time_service = MockTimeService()
    
    # Create thought at max depth (7)
    parent = Thought(
        thought_id="test-thought-7",
        source_task_id="test-task",
        thought_type=ThoughtType.STANDARD,
        status=ThoughtStatus.PENDING,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        round_number=1,
        content="Thought at max depth 7",
        thought_depth=7
    )
    
    # Should create follow-up but capped at depth 7
    follow_up = create_follow_up_thought(parent, time_service, "Capped at 7")
    assert follow_up.thought_depth == 7  # Capped at max depth
    assert follow_up.parent_thought_id == parent.thought_id


def test_thought_depth_8_prevented_by_model():
    """Test that Thought model itself prevents depth > 7."""
    # The Thought model has validation that prevents thought_depth > 7
    with pytest.raises(ValueError) as exc_info:
        Thought(
            thought_id="test-thought-8",
            source_task_id="test-task",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=1,
            content="This should fail at model validation",
            thought_depth=8
        )
    
    assert "less than or equal to 7" in str(exc_info.value)


def test_multiple_thoughts_at_depth_6_can_all_create_depth_7():
    """Test that multiple thoughts at depth 6 can create depth 7 thoughts."""
    time_service = MockTimeService()
    
    # Create multiple thoughts at depth 6
    thoughts_at_6 = []
    for i in range(3):
        thought = Thought(
            thought_id=f"test-thought-6-{i}",
            source_task_id="test-task",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            round_number=1,
            content=f"Thought {i} at depth 6",
            thought_depth=6
        )
        thoughts_at_6.append(thought)
    
    # All should be able to create follow-ups at depth 7
    for i, parent in enumerate(thoughts_at_6):
        follow_up = create_follow_up_thought(parent, time_service, f"Follow-up {i}")
        assert follow_up.thought_depth == 7
        
        # Depth 7 thoughts stay capped at 7
        follow_up_2 = create_follow_up_thought(follow_up, time_service, "Stays at 7")
        assert follow_up_2.thought_depth == 7  # Capped at max