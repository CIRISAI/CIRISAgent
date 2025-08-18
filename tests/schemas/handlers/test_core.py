"""
Comprehensive tests for schemas/handlers/core.py module.

Tests all deferral-related Pydantic models including validation,
serialization, and edge cases.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.handlers.core import (
    ActionHistoryItem,
    CSDMAAssessment,
    DeferralPackage,
    DeferralReason,
    DeferralReport,
    DeferralResolution,
    DSDMAAssessment,
    EthicalAssessment,
    TransportData,
)


class TestDeferralReason:
    """Test DeferralReason enum."""

    def test_all_reasons_defined(self):
        """Test that all expected deferral reasons are defined."""
        expected_reasons = [
            "conscience_failure",
            "max_rounds_reached",
            "channel_policy_update",
            "insufficient_context",
            "ethical_concern",
            "system_error",
            "wa_review_required",
            "memory_conflict",
            "unknown",
        ]

        actual_reasons = [reason.value for reason in DeferralReason]
        assert set(expected_reasons) == set(actual_reasons)

    def test_reason_enum_values(self):
        """Test that enum values are accessible."""
        assert DeferralReason.conscience_FAILURE.value == "conscience_failure"
        assert DeferralReason.MAX_ROUNDS_REACHED.value == "max_rounds_reached"
        assert DeferralReason.ETHICAL_CONCERN.value == "ethical_concern"

    def test_reason_from_string(self):
        """Test creating enum from string value."""
        reason = DeferralReason("ethical_concern")
        assert reason == DeferralReason.ETHICAL_CONCERN


class TestEthicalAssessment:
    """Test EthicalAssessment model."""

    def test_valid_ethical_assessment(self):
        """Test creating a valid ethical assessment."""
        assessment = EthicalAssessment(
            decision="approve",
            reasoning="Action aligns with all ethical principles",
            principles_upheld=["benevolence", "integrity"],
            principles_violated=[],
        )

        assert assessment.decision == "approve"
        assert assessment.reasoning == "Action aligns with all ethical principles"
        assert len(assessment.principles_upheld) == 2
        assert len(assessment.principles_violated) == 0

    def test_ethical_assessment_defaults(self):
        """Test ethical assessment with default values."""
        assessment = EthicalAssessment(decision="defer", reasoning="Need more information")

        assert assessment.principles_upheld == []
        assert assessment.principles_violated == []

    def test_ethical_assessment_validation(self):
        """Test that required fields are validated."""
        with pytest.raises(ValidationError) as exc_info:
            EthicalAssessment(decision="approve")  # Missing reasoning

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("reasoning",) for error in errors)

    def test_ethical_assessment_no_extra_fields(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError) as exc_info:
            EthicalAssessment(decision="approve", reasoning="Test", extra_field="not_allowed")

        errors = exc_info.value.errors()
        assert any("extra_field" in str(error) for error in errors)

    def test_ethical_assessment_serialization(self):
        """Test serialization to dict."""
        assessment = EthicalAssessment(
            decision="reject", reasoning="Violates user privacy", principles_violated=["privacy", "consent"]
        )

        data = assessment.model_dump()
        assert data["decision"] == "reject"
        assert data["principles_violated"] == ["privacy", "consent"]
        assert "principles_upheld" in data


class TestCSDMAAssessment:
    """Test CSDMAAssessment model."""

    def test_valid_csdma_assessment(self):
        """Test creating a valid common sense assessment."""
        assessment = CSDMAAssessment(
            makes_sense=True,
            practicality_score=0.85,
            flags=["verified", "safe"],
            reasoning="Action is practical and safe",
        )

        assert assessment.makes_sense is True
        assert assessment.practicality_score == 0.85
        assert len(assessment.flags) == 2

    def test_csdma_score_validation(self):
        """Test practicality score bounds validation."""
        # Valid scores
        CSDMAAssessment(makes_sense=True, practicality_score=0.0, reasoning="Test")
        CSDMAAssessment(makes_sense=True, practicality_score=1.0, reasoning="Test")

        # Invalid scores
        with pytest.raises(ValidationError):
            CSDMAAssessment(makes_sense=True, practicality_score=1.5, reasoning="Test")  # Too high

        with pytest.raises(ValidationError):
            CSDMAAssessment(makes_sense=True, practicality_score=-0.1, reasoning="Test")  # Too low

    def test_csdma_defaults(self):
        """Test CSDMA assessment defaults."""
        assessment = CSDMAAssessment(
            makes_sense=False, practicality_score=0.2, reasoning="Doesn't make practical sense"
        )

        assert assessment.flags == []


class TestDSDMAAssessment:
    """Test DSDMAAssessment model."""

    def test_valid_dsdma_assessment(self):
        """Test creating a valid domain-specific assessment."""
        assessment = DSDMAAssessment(
            domain="medical",
            alignment_score=0.95,
            recommendations=["consult_specialist", "review_history"],
            reasoning="Requires medical expertise",
        )

        assert assessment.domain == "medical"
        assert assessment.alignment_score == 0.95
        assert len(assessment.recommendations) == 2

    def test_dsdma_score_validation(self):
        """Test alignment score bounds validation."""
        # Valid scores
        DSDMAAssessment(domain="legal", alignment_score=0.5, reasoning="Test")

        # Invalid score
        with pytest.raises(ValidationError):
            DSDMAAssessment(domain="legal", alignment_score=2.0, reasoning="Test")  # Too high

    def test_dsdma_defaults(self):
        """Test DSDMA assessment defaults."""
        assessment = DSDMAAssessment(domain="technical", alignment_score=0.7, reasoning="Technical alignment check")

        assert assessment.recommendations == []


class TestActionHistoryItem:
    """Test ActionHistoryItem model."""

    def test_valid_action_history(self):
        """Test creating a valid action history item."""
        timestamp = datetime.now(timezone.utc)
        action = ActionHistoryItem(
            action_type="send_message",
            timestamp=timestamp,
            parameters={"channel": "general", "content": "Hello"},
            result="success",
        )

        assert action.action_type == "send_message"
        assert action.timestamp == timestamp
        assert action.parameters["channel"] == "general"
        assert action.result == "success"

    def test_action_history_defaults(self):
        """Test action history with defaults."""
        action = ActionHistoryItem(action_type="process", timestamp=datetime.now(timezone.utc))

        assert action.parameters == {}
        assert action.result is None

    def test_action_history_validation(self):
        """Test that required fields are validated."""
        with pytest.raises(ValidationError):
            ActionHistoryItem(action_type="test")  # Missing timestamp


class TestDeferralPackage:
    """Test DeferralPackage model."""

    def test_valid_deferral_package(self):
        """Test creating a valid deferral package."""
        package = DeferralPackage(
            thought_id="thought_123",
            task_id="task_456",
            deferral_reason=DeferralReason.ETHICAL_CONCERN,
            reason_description="Potential privacy violation",
            thought_content="User requested access to private data",
            task_description="Process data request",
        )

        assert package.thought_id == "thought_123"
        assert package.deferral_reason == DeferralReason.ETHICAL_CONCERN
        assert package.thought_content == "User requested access to private data"

    def test_deferral_package_with_assessments(self):
        """Test deferral package with all assessments."""
        ethical = EthicalAssessment(decision="defer", reasoning="Need review")
        csdma = CSDMAAssessment(makes_sense=False, practicality_score=0.3, reasoning="Impractical")
        dsdma = DSDMAAssessment(domain="security", alignment_score=0.2, reasoning="Security risk")

        package = DeferralPackage(
            thought_id="t1",
            task_id="t2",
            deferral_reason=DeferralReason.WA_REVIEW_REQUIRED,
            reason_description="Multiple concerns",
            thought_content="Sensitive action",
            ethical_assessment=ethical,
            csdma_assessment=csdma,
            dsdma_assessment=dsdma,
        )

        assert package.ethical_assessment.decision == "defer"
        assert package.csdma_assessment.makes_sense is False
        assert package.dsdma_assessment.domain == "security"

    def test_deferral_package_with_history(self):
        """Test deferral package with action history."""
        actions = [
            ActionHistoryItem(action_type="analyze", timestamp=datetime.now(timezone.utc), result="completed"),
            ActionHistoryItem(action_type="review", timestamp=datetime.now(timezone.utc), result="deferred"),
        ]

        package = DeferralPackage(
            thought_id="t1",
            task_id="t2",
            deferral_reason=DeferralReason.MAX_ROUNDS_REACHED,
            reason_description="Too many iterations",
            thought_content="Complex decision",
            action_history=actions,
            ponder_history=["thought1", "thought2"],
        )

        assert len(package.action_history) == 2
        assert len(package.ponder_history) == 2

    def test_deferral_package_defaults(self):
        """Test deferral package default values."""
        package = DeferralPackage(
            thought_id="t1",
            task_id="t2",
            deferral_reason=DeferralReason.UNKNOWN,
            reason_description="Unknown issue",
            thought_content="Content",
        )

        assert package.task_description is None
        assert package.ethical_assessment is None
        assert package.user_profiles == {}
        assert package.system_snapshot == {}
        assert package.ponder_history == []
        assert package.action_history == []
        assert package.created_at is not None

    def test_deferral_package_timestamp(self):
        """Test that created_at is automatically set."""
        before = datetime.now(timezone.utc)
        package = DeferralPackage(
            thought_id="t1",
            task_id="t2",
            deferral_reason=DeferralReason.SYSTEM_ERROR,
            reason_description="Error",
            thought_content="Content",
        )
        after = datetime.now(timezone.utc)

        assert before <= package.created_at <= after


class TestTransportData:
    """Test TransportData model."""

    def test_valid_transport_data(self):
        """Test creating valid transport data."""
        transport = TransportData(
            adapter_type="discord",
            channel_id="123456",
            user_id="789012",
            message_id="345678",
            additional_context={"guild": "test_guild"},
        )

        assert transport.adapter_type == "discord"
        assert transport.channel_id == "123456"
        assert transport.additional_context["guild"] == "test_guild"

    def test_transport_data_minimal(self):
        """Test transport data with minimal fields."""
        transport = TransportData(adapter_type="api")

        assert transport.adapter_type == "api"
        assert transport.channel_id is None
        assert transport.user_id is None
        assert transport.message_id is None
        assert transport.additional_context == {}

    def test_transport_data_validation(self):
        """Test that adapter_type is required."""
        with pytest.raises(ValidationError):
            TransportData()  # Missing adapter_type


class TestDeferralReport:
    """Test DeferralReport model."""

    def test_valid_deferral_report(self):
        """Test creating a valid deferral report."""
        package = DeferralPackage(
            thought_id="t1",
            task_id="t2",
            deferral_reason=DeferralReason.ETHICAL_CONCERN,
            reason_description="Ethics",
            thought_content="Content",
        )

        transport = TransportData(adapter_type="discord", user_id="wa_user_123")

        report = DeferralReport(
            report_id="report_001",
            package=package,
            target_wa_identifier="wa_user_123",
            urgency_level="high",
            transport_data=transport,
            created_at=datetime.now(timezone.utc),
        )

        assert report.report_id == "report_001"
        assert report.urgency_level == "high"
        assert report.delivered is False
        assert report.response_received is False

    def test_deferral_report_urgency_validation(self):
        """Test urgency level validation."""
        package = DeferralPackage(
            thought_id="t1",
            task_id="t2",
            deferral_reason=DeferralReason.SYSTEM_ERROR,
            reason_description="Error",
            thought_content="Content",
        )

        transport = TransportData(adapter_type="api")

        # Valid urgency levels
        for level in ["low", "normal", "high", "critical"]:
            report = DeferralReport(
                report_id=f"r_{level}",
                package=package,
                target_wa_identifier="wa",
                urgency_level=level,
                transport_data=transport,
                created_at=datetime.now(timezone.utc),
            )
            assert report.urgency_level == level

        # Invalid urgency level
        with pytest.raises(ValidationError):
            DeferralReport(
                report_id="r_bad",
                package=package,
                target_wa_identifier="wa",
                urgency_level="extreme",  # Invalid
                transport_data=transport,
                created_at=datetime.now(timezone.utc),
            )

    def test_deferral_report_delivery_tracking(self):
        """Test delivery tracking fields."""
        package = DeferralPackage(
            thought_id="t1",
            task_id="t2",
            deferral_reason=DeferralReason.UNKNOWN,
            reason_description="Unknown",
            thought_content="Content",
        )

        transport = TransportData(adapter_type="email")
        now = datetime.now(timezone.utc)

        report = DeferralReport(
            report_id="r1",
            package=package,
            target_wa_identifier="admin@example.com",
            transport_data=transport,
            created_at=now,
            delivered=True,
            delivered_at=now + timedelta(minutes=1),
            response_received=True,
            response_at=now + timedelta(minutes=5),
        )

        assert report.delivered is True
        assert report.delivered_at > report.created_at
        assert report.response_received is True
        assert report.response_at > report.delivered_at


class TestDeferralResolution:
    """Test DeferralResolution model."""

    def test_valid_deferral_resolution(self):
        """Test creating a valid deferral resolution."""
        resolution = DeferralResolution(
            report_id="report_001",
            wa_id="wa_admin_123",
            decision="approve",
            reasoning="Action is safe after review",
            resolved_at=datetime.now(timezone.utc),
            signature="digital_sig_xyz",
        )

        assert resolution.report_id == "report_001"
        assert resolution.decision == "approve"
        assert resolution.modified_action is None
        assert resolution.conditions == []

    def test_resolution_with_modifications(self):
        """Test resolution with modified action."""
        resolution = DeferralResolution(
            report_id="r1",
            wa_id="wa_123",
            decision="modify",
            reasoning="Needs constraints",
            modified_action="Limited data access only",
            conditions=["log_all_access", "notify_admin"],
            resolved_at=datetime.now(timezone.utc),
            signature="sig_abc",
        )

        assert resolution.decision == "modify"
        assert resolution.modified_action == "Limited data access only"
        assert len(resolution.conditions) == 2

    def test_resolution_validation(self):
        """Test that required fields are validated."""
        with pytest.raises(ValidationError):
            DeferralResolution(
                report_id="r1",
                wa_id="wa",
                decision="approve",
                # Missing reasoning, resolved_at, signature
            )


class TestSerialization:
    """Test model serialization and deserialization."""

    def test_full_deferral_flow_serialization(self):
        """Test serializing a complete deferral flow."""
        # Create package
        package = DeferralPackage(
            thought_id="t1",
            task_id="t2",
            deferral_reason=DeferralReason.ETHICAL_CONCERN,
            reason_description="Ethics check",
            thought_content="Sensitive content",
            ethical_assessment=EthicalAssessment(decision="defer", reasoning="Needs review"),
        )

        # Create report
        report = DeferralReport(
            report_id="r1",
            package=package,
            target_wa_identifier="wa_admin",
            transport_data=TransportData(adapter_type="api"),
            created_at=datetime.now(timezone.utc),
        )

        # Serialize to dict
        report_dict = report.model_dump()

        # Deserialize back
        restored_report = DeferralReport(**report_dict)

        # Verify integrity
        assert restored_report.report_id == "r1"
        assert restored_report.package.thought_id == "t1"
        assert restored_report.package.ethical_assessment.decision == "defer"

    def test_json_serialization(self):
        """Test JSON serialization."""
        assessment = EthicalAssessment(decision="approve", reasoning="All good", principles_upheld=["benevolence"])

        # To JSON
        json_str = assessment.model_dump_json()
        assert isinstance(json_str, str)
        assert "approve" in json_str
        assert "benevolence" in json_str

        # From JSON
        restored = EthicalAssessment.model_validate_json(json_str)
        assert restored.decision == "approve"
        assert restored.principles_upheld == ["benevolence"]


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_strings_validation(self):
        """Test that empty strings are handled correctly."""
        # Some fields should accept empty strings
        transport = TransportData(adapter_type="", additional_context={})  # Should this be allowed?

        # Required string fields should not be empty
        with pytest.raises(ValidationError):
            DeferralPackage(
                thought_id="",  # Empty ID
                task_id="t1",
                deferral_reason=DeferralReason.UNKNOWN,
                reason_description="",  # Empty description
                thought_content="",  # Empty content
            )

    def test_large_data_handling(self):
        """Test handling of large data structures."""
        # Create package with lots of history
        large_history = [f"thought_{i}" for i in range(1000)]
        large_actions = [
            ActionHistoryItem(
                action_type=f"action_{i}",
                timestamp=datetime.now(timezone.utc),
                parameters={f"param_{j}": f"value_{j}" for j in range(10)},
            )
            for i in range(100)
        ]

        package = DeferralPackage(
            thought_id="t1",
            task_id="t2",
            deferral_reason=DeferralReason.MAX_ROUNDS_REACHED,
            reason_description="Too many iterations",
            thought_content="Content",
            ponder_history=large_history,
            action_history=large_actions,
        )

        assert len(package.ponder_history) == 1000
        assert len(package.action_history) == 100

        # Should serialize without issues
        serialized = package.model_dump()
        assert len(serialized["ponder_history"]) == 1000
