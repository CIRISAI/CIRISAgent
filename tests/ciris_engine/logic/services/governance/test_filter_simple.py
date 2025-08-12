"""
Simple pragmatic tests for AdaptiveFilterService.
Goal: Find out what's actually broken.
"""

import asyncio

import pytest

from ciris_engine.logic.services.governance.filter import AdaptiveFilterService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.filters_core import FilterPriority


@pytest.fixture
async def filter_service():
    """Create a minimal filter service for testing."""

    # Mock the required services
    class MockMemory:
        pass

    class MockConfig:
        async def get_config(self, key):
            return None

        async def set_config(self, key, value, updated_by):
            pass

    time_service = TimeService()
    await time_service.start()

    service = AdaptiveFilterService(
        memory_service=MockMemory(), time_service=time_service, llm_service=None, config_service=MockConfig()
    )
    await service.start()
    await asyncio.sleep(0.1)  # Let it initialize

    yield service

    await service.stop()
    await time_service.stop()


@pytest.mark.asyncio
async def test_dm_detection(filter_service):
    """Test: Does DM detection work?"""
    # Simple dict with is_dm=True
    msg = {"content": "Hello", "is_dm": True}
    result = await filter_service.filter_message(msg, "discord")

    print(f"DM test - Priority: {result.priority}, Triggers: {result.triggered_filters}")
    assert result.priority == FilterPriority.CRITICAL
    assert "dm_1" in result.triggered_filters


@pytest.mark.asyncio
async def test_mention_detection(filter_service):
    """Test: Does @mention detection work?"""
    msg = {"content": "<@123456789> help me"}
    result = await filter_service.filter_message(msg, "discord")

    print(f"Mention test - Priority: {result.priority}, Triggers: {result.triggered_filters}")
    assert result.priority == FilterPriority.CRITICAL
    assert "mention_1" in result.triggered_filters


@pytest.mark.asyncio
async def test_name_detection(filter_service):
    """Test: Does name detection work?"""
    msg = {"content": "Hey echo, can you help?"}
    result = await filter_service.filter_message(msg, "discord")

    print(f"Name test - Priority: {result.priority}, Triggers: {result.triggered_filters}")
    assert result.priority == FilterPriority.CRITICAL
    assert "name_1" in result.triggered_filters


@pytest.mark.asyncio
async def test_spam_detection(filter_service):
    """Test: Does spam detection work?"""
    msg = {"content": "BUY CRYPTO NOW " * 100}
    result = await filter_service.filter_message(msg, "discord")

    print(f"Spam test - Priority: {result.priority}, Triggers: {result.triggered_filters}")
    assert result.priority == FilterPriority.HIGH
    assert "wall_1" in result.triggered_filters


@pytest.mark.asyncio
async def test_normal_message(filter_service):
    """Test: Do normal messages get appropriate priority?"""
    msg = {"content": "Just having a normal conversation"}
    result = await filter_service.filter_message(msg, "discord")

    print(f"Normal test - Priority: {result.priority}, Triggers: {result.triggered_filters}")
    print(f"Full result: {result}")

    # Let's test the regex directly
    import re

    caps_pattern = r"[A-Z\s!?]{20,}"
    test_content = "Just having a normal conversation"
    match = re.search(caps_pattern, test_content)
    print(f"Caps regex match on '{test_content}': {match}")

    # With minimal config (returns None), filter uses MEDIUM priority for safety
    # This is expected behavior - better to review than miss something
    assert result.priority == FilterPriority.MEDIUM


# Property-based tests with hypothesis
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


@pytest.mark.asyncio
@given(content=st.text())
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
async def test_filter_never_crashes(content):
    """Invariant: Filter should never crash on any text input"""
    # Create service inline to avoid fixture issues
    from ciris_engine.logic.services.lifecycle.time import TimeService

    class MockMemory:
        pass

    class MockConfig:
        async def get_config(self, key):
            return None

        async def set_config(self, key, value, updated_by):
            pass

    time_service = TimeService()
    await time_service.start()

    service = AdaptiveFilterService(
        memory_service=MockMemory(), time_service=time_service, llm_service=None, config_service=MockConfig()
    )
    await service.start()
    await asyncio.sleep(0.1)

    try:
        msg = {"content": content}
        result = await service.filter_message(msg, "discord")
        # Should always return a valid result
        assert result is not None
        assert hasattr(result, "priority")
        assert hasattr(result, "triggered_filters")
    finally:
        await service.stop()
        await time_service.stop()


@pytest.mark.asyncio
async def test_all_filters_evaluated(filter_service):
    """Invariant: All configured filters should be evaluated"""
    # Message that should trigger multiple filters
    msg = {"content": "<@123456789> HELLO ECHO " * 10, "is_dm": True}  # mention + caps + name
    result = await filter_service.filter_message(msg, "discord")

    # Should have triggered multiple filters
    assert len(result.triggered_filters) >= 2
    print(f"Triggered filters: {result.triggered_filters}")


if __name__ == "__main__":
    # Run directly to see output
    pytest.main([__file__, "-v", "-s"])
