"""Tests for AgentModeBroker — pub/sub, lock safety, persistence."""

from __future__ import annotations

import asyncio
import threading
from typing import List
from unittest.mock import AsyncMock

import pytest

from ciris_engine.logic.utils.agent_mode_broker import AGENT_MODE_CONFIG_KEY, AGENT_MODE_UPDATER, AgentModeBroker
from ciris_engine.schemas.runtime.agent_mode import AgentMode, AgentModeChangedEvent


@pytest.fixture
def broker() -> AgentModeBroker:
    return AgentModeBroker(initial_mode=AgentMode.PROXY)


class TestInitialState:
    def test_default_mode_is_proxy(self) -> None:
        b = AgentModeBroker()
        assert b.current_mode() is AgentMode.PROXY

    def test_initial_mode_argument_respected(self) -> None:
        b = AgentModeBroker(initial_mode=AgentMode.CLIENT)
        assert b.current_mode() is AgentMode.CLIENT


class TestSubscribeBroadcast:
    @pytest.mark.asyncio
    async def test_subscriber_receives_event(self, broker: AgentModeBroker) -> None:
        received: List[AgentModeChangedEvent] = []
        broker.subscribe(received.append)

        event = await broker.set_mode(AgentMode.SERVER)

        assert len(received) == 1
        assert received[0] is event
        assert event.previous_mode is AgentMode.PROXY
        assert event.new_mode is AgentMode.SERVER

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_notified(self, broker: AgentModeBroker) -> None:
        a: List[AgentModeChangedEvent] = []
        b: List[AgentModeChangedEvent] = []
        broker.subscribe(a.append)
        broker.subscribe(b.append)

        await broker.set_mode(AgentMode.CLIENT)
        assert len(a) == 1
        assert len(b) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self, broker: AgentModeBroker) -> None:
        received: List[AgentModeChangedEvent] = []
        broker.subscribe(received.append)
        broker.unsubscribe(received.append)

        await broker.set_mode(AgentMode.CLIENT)
        assert received == []

    @pytest.mark.asyncio
    async def test_raising_subscriber_does_not_block_others(self, broker: AgentModeBroker) -> None:
        survived: List[AgentModeChangedEvent] = []

        def bad(_e: AgentModeChangedEvent) -> None:
            raise RuntimeError("boom")

        broker.subscribe(bad)
        broker.subscribe(survived.append)

        await broker.set_mode(AgentMode.SERVER)
        assert len(survived) == 1, "good subscriber must still be notified"


class TestPersistence:
    @pytest.mark.asyncio
    async def test_set_mode_persists_via_config_service(self, broker: AgentModeBroker) -> None:
        config_service = AsyncMock()
        broker.attach_config_service(config_service)

        await broker.set_mode(AgentMode.SERVER)

        config_service.set_config.assert_awaited_once()
        kwargs = config_service.set_config.await_args.kwargs
        assert kwargs["key"] == AGENT_MODE_CONFIG_KEY
        assert kwargs["value"] == "server"
        assert kwargs["updated_by"] == AGENT_MODE_UPDATER

    @pytest.mark.asyncio
    async def test_no_config_service_still_updates(self, broker: AgentModeBroker) -> None:
        # No service attached: in-memory state still flips.
        await broker.set_mode(AgentMode.CLIENT)
        assert broker.current_mode() is AgentMode.CLIENT

    @pytest.mark.asyncio
    async def test_config_persistence_failure_does_not_abort(self, broker: AgentModeBroker) -> None:
        failing_service = AsyncMock()
        failing_service.set_config.side_effect = RuntimeError("graph offline")
        broker.attach_config_service(failing_service)

        received: List[AgentModeChangedEvent] = []
        broker.subscribe(received.append)

        # Should not raise; the in-memory transition is what callers depend on.
        await broker.set_mode(AgentMode.SERVER)
        assert broker.current_mode() is AgentMode.SERVER
        # Subscribers still get notified.
        assert len(received) == 1


class TestLockSafety:
    """The broker is documented as thread-safe; sanity check that read/write
    from many threads does not deadlock or interleave catastrophically."""

    def test_concurrent_reads_do_not_deadlock(self, broker: AgentModeBroker) -> None:
        results: List[AgentMode] = []
        errors: List[BaseException] = []

        def reader() -> None:
            try:
                for _ in range(50):
                    results.append(broker.current_mode())
            except BaseException as exc:  # pragma: no cover - defensive
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
            assert not t.is_alive(), "reader thread deadlocked"

        assert not errors
        assert len(results) == 8 * 50
        # All reads see the same initial mode (no writers).
        assert set(results) == {AgentMode.PROXY}

    def test_subscribe_unsubscribe_under_contention(self, broker: AgentModeBroker) -> None:
        # Add/remove the same callback under contention without crashing.
        cb_holder: List[AgentModeChangedEvent] = []
        callback = cb_holder.append
        errors: List[BaseException] = []

        def churn() -> None:
            try:
                for _ in range(100):
                    broker.subscribe(callback)
                    broker.unsubscribe(callback)
            except BaseException as exc:  # pragma: no cover - defensive
                errors.append(exc)

        threads = [threading.Thread(target=churn) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
            assert not t.is_alive()
        assert not errors


class TestSingletonHelper:
    def test_get_agent_mode_broker_returns_module_singleton(self) -> None:
        from ciris_engine.logic.utils.agent_mode_broker import agent_mode_broker, get_agent_mode_broker

        assert get_agent_mode_broker() is agent_mode_broker

    @pytest.mark.asyncio
    async def test_reset_for_tests_clears_subscribers(self, broker: AgentModeBroker) -> None:
        received: List[AgentModeChangedEvent] = []
        broker.subscribe(received.append)

        broker.reset_for_tests(mode=AgentMode.CLIENT)
        assert broker.current_mode() is AgentMode.CLIENT

        await broker.set_mode(AgentMode.SERVER)
        assert received == [], "reset_for_tests should have cleared subscribers"
