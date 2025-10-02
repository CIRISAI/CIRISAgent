"""
Filter configuration and testing module - uses agent/interact endpoint with mock LLM.
Tests adaptive and secrets filters by configuring them via MEMORIZE actions.
Includes comprehensive RECALL before/after tests and secrets tool functionality.

NOTE: Filter tests use longer timeouts (120s) because each message triggers
task creation and processing through the full H3ERE pipeline. Tests must
complete their task before the next test starts to avoid interference.
"""

from typing import List

from ..config import QAModule, QATestCase


class FilterTestModule:
    """Test module for adaptive and secrets filter configuration via mock LLM."""

    @staticmethod
    def get_filter_tests() -> List[QATestCase]:
        """Get filter configuration and behavior test cases using mock LLM."""
        return [
            # === RECALL Before MEMORIZE Tests (should return not found) ===
            # Try to recall non-existent adaptive filter config
            QATestCase(
                name="Recall non-existent adaptive filter config",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$recall adaptive_filter/test_threshold CONFIG LOCAL"},
                expected_status=200,
                requires_auth=True,
                description="RECALL before MEMORIZE - should indicate not found",
                timeout=120.0,
            ),
            # Try to recall non-existent secrets filter config
            QATestCase(
                name="Recall non-existent secrets filter config",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$recall secrets_filter/test_pattern CONFIG LOCAL"},
                expected_status=200,
                requires_auth=True,
                description="RECALL before MEMORIZE - should indicate not found",
                timeout=120.0,
            ),
            # === Adaptive Filter MEMORIZE Tests ===
            # Configure spam threshold
            QATestCase(
                name="Memorize adaptive filter spam threshold",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize adaptive_filter/spam_threshold CONFIG LOCAL value=0.8"},
                expected_status=200,
                requires_auth=True,
                description="Configure spam detection threshold via MEMORIZE",
            ),
            # Immediately recall to verify storage
            QATestCase(
                name="Recall spam threshold after memorize",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$recall adaptive_filter/spam_threshold CONFIG LOCAL"},
                expected_status=200,
                requires_auth=True,
                description="Verify spam threshold was stored (should show 0.8)",
            ),
            # Configure caps detection threshold
            QATestCase(
                name="Memorize caps detection threshold",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize adaptive_filter/caps_threshold CONFIG LOCAL value=0.7"},
                expected_status=200,
                requires_auth=True,
                description="Configure caps detection threshold via MEMORIZE",
            ),
            # Recall caps threshold
            QATestCase(
                name="Recall caps threshold after memorize",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$recall adaptive_filter/caps_threshold CONFIG LOCAL"},
                expected_status=200,
                requires_auth=True,
                description="Verify caps threshold was stored (should show 0.7)",
            ),
            # Configure trust threshold
            QATestCase(
                name="Memorize trust threshold",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize adaptive_filter/trust_threshold CONFIG LOCAL value=0.5"},
                expected_status=200,
                requires_auth=True,
                description="Configure trust score filtering via MEMORIZE",
            ),
            # Configure DM detection
            QATestCase(
                name="Memorize DM detection enabled",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize adaptive_filter/dm_detection_enabled CONFIG LOCAL value=true"},
                expected_status=200,
                requires_auth=True,
                description="Enable DM detection via MEMORIZE",
            ),
            # Recall DM detection setting
            QATestCase(
                name="Recall DM detection setting",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$recall adaptive_filter/dm_detection_enabled CONFIG LOCAL"},
                expected_status=200,
                requires_auth=True,
                description="Verify DM detection was enabled (should show true)",
            ),
            # === Secrets Filter MEMORIZE Tests ===
            # Configure API key detection
            QATestCase(
                name="Memorize API key detection mode",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize secrets_filter/api_key_detection CONFIG LOCAL value=strict"},
                expected_status=200,
                requires_auth=True,
                description="Configure API key detection strictness via MEMORIZE",
            ),
            # Recall API key detection mode
            QATestCase(
                name="Recall API key detection mode",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$recall secrets_filter/api_key_detection CONFIG LOCAL"},
                expected_status=200,
                requires_auth=True,
                description="Verify API key detection mode (should show strict)",
            ),
            # Configure JWT detection
            QATestCase(
                name="Memorize JWT detection enabled",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize secrets_filter/jwt_detection_enabled CONFIG LOCAL value=true"},
                expected_status=200,
                requires_auth=True,
                description="Enable JWT token filtering via MEMORIZE",
            ),
            # Recall JWT detection setting
            QATestCase(
                name="Recall JWT detection setting",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$recall secrets_filter/jwt_detection_enabled CONFIG LOCAL"},
                expected_status=200,
                requires_auth=True,
                description="Verify JWT detection enabled (should show true)",
            ),
            # Configure custom patterns
            QATestCase(
                name="Memorize custom secret patterns",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize secrets_filter/custom_patterns CONFIG LOCAL value=['PROJ-[0-9]{4}','SECRET-[A-Z]+']"
                },
                expected_status=200,
                requires_auth=True,
                description="Add custom secret patterns via MEMORIZE",
            ),
            # Recall custom patterns
            QATestCase(
                name="Recall custom secret patterns",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$recall secrets_filter/custom_patterns CONFIG LOCAL"},
                expected_status=200,
                requires_auth=True,
                description="Verify custom patterns stored (should show list)",
            ),
            # Configure entropy threshold
            QATestCase(
                name="Memorize entropy threshold",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize secrets_filter/entropy_threshold CONFIG LOCAL value=4.0"},
                expected_status=200,
                requires_auth=True,
                description="Configure entropy threshold via MEMORIZE",
            ),
            # === CONFIG Update Tests (Version Increment) ===
            # Update existing spam threshold
            QATestCase(
                name="Update spam threshold to new value",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize adaptive_filter/spam_threshold CONFIG LOCAL value=0.9"},
                expected_status=200,
                requires_auth=True,
                description="Update existing CONFIG node (should increment version)",
            ),
            # Verify updated value
            QATestCase(
                name="Recall updated spam threshold",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$recall adaptive_filter/spam_threshold CONFIG LOCAL"},
                expected_status=200,
                requires_auth=True,
                description="Verify spam threshold updated to 0.9",
            ),
            # Update boolean value
            QATestCase(
                name="Update DM detection to false",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize adaptive_filter/dm_detection_enabled CONFIG LOCAL value=false"},
                expected_status=200,
                requires_auth=True,
                description="Update boolean CONFIG from true to false",
            ),
            # Verify boolean update
            QATestCase(
                name="Recall updated DM detection",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$recall adaptive_filter/dm_detection_enabled CONFIG LOCAL"},
                expected_status=200,
                requires_auth=True,
                description="Verify DM detection updated to false",
            ),
            # === Secrets Tool Tests ===
            # Test API key detection
            QATestCase(
                name="Test API key detection",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "My API key is sk-proj-abc123xyz789def456 for the service"},
                expected_status=200,
                requires_auth=True,
                description="Verify API key is detected and filtered",
            ),
            # Test JWT token detection
            QATestCase(
                name="Test JWT token detection",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
                },
                expected_status=200,
                requires_auth=True,
                description="Verify JWT token is detected and filtered",
            ),
            # Test custom pattern detection
            QATestCase(
                name="Test custom pattern detection",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "The project code is PROJ-1234 and SECRET-ABC for internal use"},
                expected_status=200,
                requires_auth=True,
                description="Verify custom patterns are detected",
            ),
            # List detected secrets
            QATestCase(
                name="List detected secrets via tool",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$tool secrets list"},
                expected_status=200,
                requires_auth=True,
                description="List all detected secrets using secrets tool",
            ),
            # Test AWS key detection
            QATestCase(
                name="Test AWS key detection",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "AWS Access Key: AKIAIOSFODNN7EXAMPLE"},
                expected_status=200,
                requires_auth=True,
                description="Verify AWS keys are detected",
            ),
            # === Filter Behavior Tests ===
            # Test caps detection with configured threshold
            QATestCase(
                name="Test caps filter with threshold",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "THIS IS A TEST MESSAGE WITH LOTS OF CAPS"},
                expected_status=200,
                requires_auth=True,
                description="Verify caps filter triggers with configured threshold",
            ),
            # Test spam detection
            QATestCase(
                name="Test spam detection with repetition",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "Buy now! Buy now! Buy now! Limited offer! Buy now!"},
                expected_status=200,
                requires_auth=True,
                description="Verify spam filter triggers on repetition",
            ),
            # Test DM detection
            QATestCase(
                name="Test DM detection",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "Hey, DM me for more info about this private matter"},
                expected_status=200,
                requires_auth=True,
                description="Verify DM filter triggers",
            ),
            # Test multiple filters
            QATestCase(
                name="Test multiple filter triggers",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "URGENT!!! DM ME NOW WITH YOUR API KEY sk-test-123456!!!"},
                expected_status=200,
                requires_auth=True,
                description="Test message triggering caps, DM, and secrets filters",
            ),
            # === Error Handling Tests ===
            # Test CONFIG without value
            QATestCase(
                name="Test CONFIG missing value error",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize test/missing_value CONFIG LOCAL"},
                expected_status=200,
                requires_auth=True,
                description="Should return detailed error with examples",
            ),
            # Test invalid CONFIG scope
            QATestCase(
                name="Test CONFIG with IDENTITY scope",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize agent/core_identity CONFIG IDENTITY value='Test Agent'"},
                expected_status=200,
                requires_auth=True,
                description="IDENTITY scope should require WA approval",
            ),
            # === User Trust Configuration ===
            # Configure trusted user
            QATestCase(
                name="Configure trusted user",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize user/qa_tester USER LOCAL trust_level=VERIFIED"},
                expected_status=200,
                requires_auth=True,
                description="Configure trusted user for filter bypass",
            ),
            # Test trusted user bypass
            QATestCase(
                name="Test trusted user filter bypass",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "THIS WOULD NORMALLY BE FILTERED BUT I'M TRUSTED",
                    "context": {"user_id": "qa_tester"},
                },
                expected_status=200,
                requires_auth=True,
                description="Verify trusted users bypass filters",
            ),
            # === Statistics and Monitoring ===
            # Get filter statistics
            QATestCase(
                name="Get filter statistics",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "What are the current filter statistics and trigger counts?"},
                expected_status=200,
                requires_auth=True,
                description="Request filter statistics via interact",
            ),
            # Reset filter statistics
            QATestCase(
                name="Reset filter statistics",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize adaptive_filter/stats_reset CONFIG LOCAL value=true"},
                expected_status=200,
                requires_auth=True,
                description="Reset filter statistics via MEMORIZE",
            ),
            # Configure verbose logging
            QATestCase(
                name="Configure filter logging level",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "$memorize adaptive_filter/logging_verbose CONFIG LOCAL value=true"},
                expected_status=200,
                requires_auth=True,
                description="Configure filter logging via MEMORIZE",
            ),
        ]
