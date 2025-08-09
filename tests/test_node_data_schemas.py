"""
Tests for node data schemas.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.services.graph.node_data import (
    AuditNodeData,
    BaseNodeData,
    ConfigNodeData,
    MemoryNodeData,
    TelemetryNodeData,
    ValidationRule,
)


class TestValidationRule:
    """Test ValidationRule schema."""

    def test_valid_validation_rule(self):
        """Test creating a valid validation rule."""
        rule = ValidationRule(
            rule_type="range", parameters={"min": 0, "max": 100}, error_message="Value must be between 0 and 100"
        )
        assert rule.rule_type == "range"
        assert rule.parameters["min"] == 0
        assert rule.parameters["max"] == 100
        assert rule.error_message == "Value must be between 0 and 100"

    def test_validation_rule_without_error_message(self):
        """Test validation rule without error message."""
        rule = ValidationRule(rule_type="regex", parameters={"pattern": r"^\d+$"})
        assert rule.rule_type == "regex"
        assert rule.error_message is None

    def test_validation_rule_forbids_extra_fields(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError) as exc_info:
            ValidationRule(rule_type="enum", parameters={"values": ["a", "b", "c"]}, extra_field="not allowed")
        assert "Extra inputs are not permitted" in str(exc_info.value)


class TestBaseNodeData:
    """Test BaseNodeData schema."""

    def test_base_node_data_defaults(self):
        """Test BaseNodeData with default values."""
        now = datetime.now(timezone.utc)
        data = BaseNodeData(created_at=now, updated_at=now)
        assert data.version == 1
        assert data.created_at == now
        assert data.updated_at == now

    def test_datetime_serialization(self):
        """Test datetime fields are serialized to ISO format."""
        now = datetime.now(timezone.utc)
        data = BaseNodeData(created_at=now, updated_at=now)
        serialized = data.model_dump()
        assert isinstance(serialized["created_at"], str)
        assert isinstance(serialized["updated_at"], str)
        assert serialized["created_at"] == now.isoformat()

    def test_base_node_data_forbids_extra(self):
        """Test that extra fields are forbidden."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            BaseNodeData(created_at=now, updated_at=now, extra="not allowed")
        assert "Extra inputs are not permitted" in str(exc_info.value)


class TestConfigNodeData:
    """Test ConfigNodeData schema."""

    def test_config_node_with_string_value(self):
        """Test config node with string value."""
        now = datetime.now(timezone.utc)
        config = ConfigNodeData(
            created_at=now,
            updated_at=now,
            key="api.timeout",
            value="30",
            description="API timeout in seconds",
            category="operational",
        )
        assert config.key == "api.timeout"
        assert config.value == "30"
        assert config.is_sensitive is False

    def test_config_node_with_list_value(self):
        """Test config node with list value."""
        now = datetime.now(timezone.utc)
        config = ConfigNodeData(
            created_at=now, updated_at=now, key="allowed_hosts", value=["localhost", "127.0.0.1"], category="security"
        )
        assert config.value == ["localhost", "127.0.0.1"]

    def test_config_node_with_dict_value(self):
        """Test config node with dict value."""
        now = datetime.now(timezone.utc)
        config = ConfigNodeData(
            created_at=now, updated_at=now, key="features", value={"auth": "enabled", "logging": "debug"}
        )
        assert config.value["auth"] == "enabled"

    def test_config_node_with_validation_rules(self):
        """Test config node with validation rules."""
        now = datetime.now(timezone.utc)
        rule = ValidationRule(rule_type="range", parameters={"min": 1, "max": 3600})
        config = ConfigNodeData(created_at=now, updated_at=now, key="timeout", value=30, validation_rules=[rule])
        assert len(config.validation_rules) == 1
        assert config.validation_rules[0].rule_type == "range"

    def test_sensitive_config(self):
        """Test sensitive configuration marking."""
        now = datetime.now(timezone.utc)
        config = ConfigNodeData(created_at=now, updated_at=now, key="api_key", value="secret123", is_sensitive=True)
        assert config.is_sensitive is True


class TestTelemetryNodeData:
    """Test TelemetryNodeData schema."""

    def test_basic_telemetry_node(self):
        """Test basic telemetry node creation."""
        now = datetime.now(timezone.utc)
        telemetry = TelemetryNodeData(
            created_at=now,
            updated_at=now,
            metric_name="cpu_usage",
            metric_value=75.5,
            metric_type="gauge",
            unit="percent",
        )
        assert telemetry.metric_name == "cpu_usage"
        assert telemetry.metric_value == 75.5
        assert telemetry.metric_type == "gauge"
        assert telemetry.unit == "percent"

    def test_telemetry_with_labels(self):
        """Test telemetry with labels."""
        now = datetime.now(timezone.utc)
        telemetry = TelemetryNodeData(
            created_at=now,
            updated_at=now,
            metric_name="http_requests",
            metric_value=100,
            metric_type="counter",
            labels={"method": "GET", "status": "200"},
        )
        assert telemetry.labels["method"] == "GET"
        assert telemetry.labels["status"] == "200"

    def test_telemetry_time_series(self):
        """Test telemetry with time series data."""
        now = datetime.now(timezone.utc)
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc)

        telemetry = TelemetryNodeData(
            created_at=now,
            updated_at=now,
            metric_name="requests_per_hour",
            metric_value=1000,
            metric_type="histogram",
            start_time=start,
            end_time=end,
            sample_count=1000,
            aggregation_type="sum",
        )
        assert telemetry.start_time == start
        assert telemetry.end_time == end
        assert telemetry.sample_count == 1000
        assert telemetry.aggregation_type == "sum"

    def test_telemetry_defaults(self):
        """Test telemetry default values."""
        now = datetime.now(timezone.utc)
        telemetry = TelemetryNodeData(
            created_at=now, updated_at=now, metric_name="test", metric_value=1.0, metric_type="gauge"
        )
        assert telemetry.labels == {}
        assert telemetry.unit is None
        assert telemetry.aggregation_type is None


class TestAuditNodeData:
    """Test AuditNodeData schema."""

    def test_basic_audit_node(self):
        """Test basic audit event creation."""
        now = datetime.now(timezone.utc)
        audit = AuditNodeData(
            created_at=now,
            updated_at=now,
            event_type="login",
            event_category="security",
            actor="user123",
            action="authenticate",
            outcome="success",
        )
        assert audit.event_type == "login"
        assert audit.event_category == "security"
        assert audit.actor == "user123"
        assert audit.outcome == "success"

    def test_audit_with_full_context(self):
        """Test audit with full context information."""
        now = datetime.now(timezone.utc)
        audit = AuditNodeData(
            created_at=now,
            updated_at=now,
            event_type="data_access",
            event_category="compliance",
            actor="service_account",
            target="user_profiles",
            action="read",
            outcome="success",
            ip_address="192.168.1.1",
            user_agent="CIRIS/1.0",
            correlation_id="abc-123",
            risk_score=0.2,
            evidence={"records_accessed": "50", "time_taken": "2.5s"},
        )
        assert audit.ip_address == "192.168.1.1"
        assert audit.correlation_id == "abc-123"
        assert audit.risk_score == 0.2
        assert audit.evidence["records_accessed"] == "50"

    def test_audit_failure_with_error(self):
        """Test audit event for failure with error details."""
        now = datetime.now(timezone.utc)
        audit = AuditNodeData(
            created_at=now,
            updated_at=now,
            event_type="permission_check",
            event_category="security",
            actor="user456",
            target="admin_panel",
            action="access",
            outcome="failure",
            error_details="Insufficient permissions: requires ADMIN role",
        )
        assert audit.outcome == "failure"
        assert "Insufficient permissions" in audit.error_details

    def test_audit_defaults(self):
        """Test audit default values."""
        now = datetime.now(timezone.utc)
        audit = AuditNodeData(
            created_at=now,
            updated_at=now,
            event_type="test",
            event_category="operational",
            actor="system",
            action="test",
            outcome="success",
        )
        assert audit.evidence == {}
        assert audit.target is None
        assert audit.risk_score is None


class TestMemoryNodeData:
    """Test MemoryNodeData schema."""

    def test_basic_memory_node(self):
        """Test basic memory node creation."""
        now = datetime.now(timezone.utc)
        memory = MemoryNodeData(
            created_at=now,
            updated_at=now,
            content="User prefers dark mode",
            memory_type="fact",
            source="user_preferences",
        )
        assert memory.content == "User prefers dark mode"
        assert memory.memory_type == "fact"
        assert memory.source == "user_preferences"

    def test_memory_with_relationships(self):
        """Test memory with related memories."""
        now = datetime.now(timezone.utc)
        memory = MemoryNodeData(
            created_at=now,
            updated_at=now,
            content="User is frustrated with slow response times",
            memory_type="experience",
            source="conversation",
            related_memories=["mem_123", "mem_456"],
            derived_from="mem_789",
        )
        assert len(memory.related_memories) == 2
        assert "mem_123" in memory.related_memories
        assert memory.derived_from == "mem_789"

    def test_memory_usage_tracking(self):
        """Test memory usage tracking fields."""
        now = datetime.now(timezone.utc)
        last_access = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        memory = MemoryNodeData(
            created_at=now,
            updated_at=now,
            content="Important insight",
            memory_type="insight",
            source="analysis",
            access_count=10,
            last_accessed=last_access,
            importance_score=0.9,
        )
        assert memory.access_count == 10
        assert memory.last_accessed == last_access
        assert memory.importance_score == 0.9

    def test_memory_defaults(self):
        """Test memory default values."""
        now = datetime.now(timezone.utc)
        memory = MemoryNodeData(
            created_at=now, updated_at=now, content="Test memory", memory_type="fact", source="test"
        )
        assert memory.related_memories == []
        assert memory.access_count == 0
        assert memory.importance_score == 0.5
        assert memory.last_accessed is None

    def test_memory_importance_bounds(self):
        """Test memory importance score validation."""
        now = datetime.now(timezone.utc)
        # Should accept values between 0.0 and 1.0
        memory = MemoryNodeData(
            created_at=now, updated_at=now, content="Test", memory_type="fact", source="test", importance_score=0.0
        )
        assert memory.importance_score == 0.0

        memory2 = MemoryNodeData(
            created_at=now, updated_at=now, content="Test", memory_type="fact", source="test", importance_score=1.0
        )
        assert memory2.importance_score == 1.0
