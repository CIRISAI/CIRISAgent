"""Tests for AgentMode schemas (enum + pydantic models)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.runtime.agent_mode import (
    AgentMode,
    AgentModeChangedEvent,
    AgentModeStatus,
    AgentModeUpdateRequest,
)


class TestAgentModeEnum:
    def test_three_values(self) -> None:
        assert {m.value for m in AgentMode} == {"client", "proxy", "server"}

    def test_string_serialization(self) -> None:
        # str-enum: value coerces to lowercase string
        assert str(AgentMode.PROXY.value) == "proxy"
        assert AgentMode("client") is AgentMode.CLIENT
        assert AgentMode("server") is AgentMode.SERVER

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            AgentMode("listener")

    def test_case_sensitivity(self) -> None:
        # The enum stores lowercase. Upper-case lookups must fail so callers
        # are forced to normalize (the EssentialConfig env-var reader does
        # `.lower()` explicitly).
        with pytest.raises(ValueError):
            AgentMode("CLIENT")


class TestAgentModeStatus:
    def test_minimal_construction(self) -> None:
        status = AgentModeStatus(
            mode=AgentMode.PROXY,
            available_disk_bytes=10,
            server_minimum_disk_bytes=100,
            server_eligible=False,
            data_dir="/var/data",
        )
        assert status.mode is AgentMode.PROXY
        assert status.server_eligible is False

    def test_server_eligible_round_trip(self) -> None:
        status = AgentModeStatus(
            mode=AgentMode.SERVER,
            available_disk_bytes=500 * 1024**3,
            server_minimum_disk_bytes=256 * 1024**3,
            server_eligible=True,
            data_dir="/var/data",
        )
        dumped = status.model_dump()
        # mode round-trips as the underlying string value
        assert dumped["mode"] == "server"
        rebuilt = AgentModeStatus.model_validate(dumped)
        assert rebuilt == status

    def test_negative_disk_rejected(self) -> None:
        # The schema requires non-negative byte counts.
        with pytest.raises(ValidationError):
            AgentModeStatus(
                mode=AgentMode.PROXY,
                available_disk_bytes=-1,
                server_minimum_disk_bytes=0,
                server_eligible=False,
                data_dir="/x",
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            AgentModeStatus(
                mode=AgentMode.PROXY,
                available_disk_bytes=0,
                server_minimum_disk_bytes=0,
                server_eligible=False,
                data_dir="/x",
                undeclared=True,  # type: ignore[call-arg]
            )

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            AgentModeStatus(  # type: ignore[call-arg]
                mode=AgentMode.PROXY,
                available_disk_bytes=0,
                server_minimum_disk_bytes=0,
                # server_eligible missing
                data_dir="/x",
            )


class TestAgentModeUpdateRequest:
    def test_construction_accepts_string_value(self) -> None:
        req = AgentModeUpdateRequest.model_validate({"mode": "server"})
        assert req.mode is AgentMode.SERVER

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentModeUpdateRequest.model_validate({"mode": "shadow"})


class TestAgentModeChangedEvent:
    def test_construction(self) -> None:
        now = datetime.now(timezone.utc)
        event = AgentModeChangedEvent(
            previous_mode=AgentMode.PROXY,
            new_mode=AgentMode.SERVER,
            timestamp=now,
        )
        assert event.previous_mode is AgentMode.PROXY
        assert event.new_mode is AgentMode.SERVER
        assert event.timestamp == now

    def test_round_trip(self) -> None:
        event = AgentModeChangedEvent(
            previous_mode=AgentMode.CLIENT,
            new_mode=AgentMode.PROXY,
            timestamp=datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc),
        )
        rebuilt = AgentModeChangedEvent.model_validate(event.model_dump())
        assert rebuilt == event
