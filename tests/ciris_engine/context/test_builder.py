import pytest
from ciris_engine.context.builder import ContextBuilder
from ciris_engine.schemas.agent_core_schemas_v1 import Thought, Task
from ciris_engine.schemas.context_schemas_v1 import ThoughtContext, SystemSnapshot
from pydantic import BaseModel
import types
import asyncio
from ciris_engine.action_handlers.helpers import create_follow_up_thought
from ciris_engine.schemas.foundational_schemas_v1 import ThoughtType, ThoughtStatus

class DummyMemoryService:
    def __init__(self):
        self._identity = "Agent identity string"
    async def export_identity_context(self):
        return self._identity
    # Note: Removed delegation methods that were inappropriately mixed into memory service
    # The ContextBuilder now uses persistence functions directly for task/thought data

class DummyGraphQLProvider:
    async def enrich_context(self, task, thought):
        from ciris_engine.schemas.graphql_schemas_v1 import EnrichedContext, UserProfile
        return EnrichedContext(
            user_profiles={"u1": UserProfile(nick="Alice")},
            identity_context="Test identity"
        )

def make_thought():
    return Thought(
        thought_id="th1",
        source_task_id="t1",
        thought_type=ThoughtType.STANDARD,
        status=ThoughtStatus.PENDING,
        created_at="now",
        updated_at="now",
        round_number=1,
        content="test content",
        context={},
        thought_depth=0,
        ponder_notes=None,
        parent_thought_id=None,
        final_action={}
    )

def make_task():
    return Task(
        task_id="t1",
        description="desc",
        status="active",
        priority=0,
        created_at="now",
        updated_at="now"
    )

@pytest.mark.asyncio
async def test_build_thought_context_minimal():
    builder = ContextBuilder()
    thought = make_thought()
    ctx = await builder.build_thought_context(thought)
    assert isinstance(ctx, ThoughtContext)
    assert isinstance(ctx.system_snapshot, SystemSnapshot)
    assert isinstance(ctx.user_profiles, dict)
    assert isinstance(ctx.task_history, list)

@pytest.mark.asyncio
async def test_build_thought_context_with_memory_and_graphql():
    builder = ContextBuilder(memory_service=DummyMemoryService(), graphql_provider=DummyGraphQLProvider())
    thought = make_thought()
    task = make_task()
    ctx = await builder.build_thought_context(thought, task)
    # Should have user_profiles from GraphQL
    assert ctx.user_profiles["u1"].nick == "Alice"
    # Should have identity_context from memory service (not GraphQL)
    assert "Agent identity string" in ctx.identity_context
    # Should have task_history from recently_completed_tasks_summary
    assert isinstance(ctx.task_history, list)
    # Note: GraphQL provider's identity_context is only used when no memory service is available

@pytest.mark.asyncio
async def test_discord_channel_context(monkeypatch):
    builder = ContextBuilder(memory_service=DummyMemoryService())
    thought = make_thought()
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "12345")
    ctx = await builder.build_thought_context(thought)
    assert "12345" in ctx.identity_context
    monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)

@pytest.mark.asyncio
async def test_build_context_includes_task_summaries():
    builder = ContextBuilder(memory_service=DummyMemoryService())
    thought = make_thought()
    task = make_task()
    ctx = await builder.build_thought_context(thought, task)
    snap = ctx.system_snapshot
    assert isinstance(snap.top_pending_tasks_summary, list)


@pytest.mark.asyncio
async def test_followup_thought_channel_context():
    from ciris_engine.schemas.context_schemas_v1 import ThoughtContext, SystemSnapshot
    from ciris_engine.utils.channel_utils import create_channel_context
    
    builder = ContextBuilder()
    parent = make_thought()
    # Create proper ThoughtContext with ChannelContext
    parent.context = ThoughtContext(
        system_snapshot=SystemSnapshot(
            channel_context=create_channel_context("chan-123")
        )
    )
    child = create_follow_up_thought(parent, content="child")
    task = make_task()
    ctx = await builder.build_thought_context(child, task)
    
    # Check channel context propagation
    assert ctx.system_snapshot.channel_context is not None
    assert ctx.system_snapshot.channel_context.channel_id == "chan-123"


@pytest.mark.asyncio
async def test_current_task_details_is_summary():
    builder = ContextBuilder()
    thought = make_thought()
    task = make_task()
    ctx = await builder.build_thought_context(thought, task)
    assert ctx.system_snapshot.current_task_details.task_id == task.task_id
    from ciris_engine.schemas.context_schemas_v1 import TaskSummary
    assert isinstance(ctx.system_snapshot.current_task_details, TaskSummary)


@pytest.mark.asyncio
async def test_app_config_channel_fallback(monkeypatch):
    class DummyConfig:
        agent_mode = 'cli'

    # Clear DISCORD_CHANNEL_ID env var to test app_config fallback
    monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
    
    builder = ContextBuilder(app_config=DummyConfig())
    thought = make_thought()
    ctx = await builder.build_thought_context(thought)
    assert 'CLI' in ctx.identity_context
