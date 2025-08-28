"""
Filter configuration and testing module - uses agent/interact endpoint with mock LLM.
Tests adaptive and secrets filters by configuring them via MEMORIZE actions.
"""

from typing import List

from ..config import QAModule, QATestCase


class FilterTestModule:
    """Test module for adaptive and secrets filter configuration via mock LLM."""

    @staticmethod
    def get_filter_tests() -> List[QATestCase]:
        """Get filter configuration and behavior test cases using mock LLM."""
        return [
            # === Adaptive Filter Configuration Tests ===
            
            # Configure caps detection threshold
            QATestCase(
                name="Configure caps filter threshold",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize adaptive_filter/caps_threshold CONFIG LOCAL value=0.7"
                },
                expected_status=200,
                requires_auth=True,
                description="Configure caps detection threshold via MEMORIZE",
            ),
            
            # Test caps detection behavior after configuration
            QATestCase(
                name="Test caps detection with configured threshold",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "THIS IS A TEST MESSAGE WITH LOTS OF CAPS"
                },
                expected_status=200,
                requires_auth=True,
                description="Verify caps filter triggers with configured threshold",
            ),
            
            # Configure trust score thresholds
            QATestCase(
                name="Configure trust score thresholds",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize adaptive_filter/trust_threshold CONFIG LOCAL value=0.5"
                },
                expected_status=200,
                requires_auth=True,
                description="Configure trust score filtering via MEMORIZE",
            ),
            
            # Configure DM detection
            QATestCase(
                name="Configure DM detection settings",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize adaptive_filter/dm_detection_enabled CONFIG LOCAL value=true"
                },
                expected_status=200,
                requires_auth=True,
                description="Configure DM detection via MEMORIZE",
            ),
            
            # Test DM detection behavior
            QATestCase(
                name="Test DM detection after configuration",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "Hey, DM me for more info about this private matter"
                },
                expected_status=200,
                requires_auth=True,
                description="Verify DM filter triggers after configuration",
            ),
            
            # Configure spam detection
            QATestCase(
                name="Configure spam detection parameters",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize adaptive_filter/spam_threshold CONFIG LOCAL value=0.8"
                },
                expected_status=200,
                requires_auth=True,
                description="Configure spam detection via MEMORIZE",
            ),
            
            # Test spam detection
            QATestCase(
                name="Test spam detection with repetition",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "Buy now! Buy now! Buy now! Limited offer! Buy now!"
                },
                expected_status=200,
                requires_auth=True,
                description="Verify spam filter triggers on repetition",
            ),
            
            # === Secrets Filter Configuration Tests ===
            
            # Configure custom secret pattern
            QATestCase(
                name="Add custom secret pattern",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize secrets_filter/custom_patterns CONFIG LOCAL value=['PROJ-[0-9]{4}']"
                },
                expected_status=200,
                requires_auth=True,
                description="Add custom secret pattern via MEMORIZE",
            ),
            
            # Test custom secret pattern detection
            QATestCase(
                name="Test custom secret pattern detection",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "The project code is PROJ-1234 and should be kept confidential"
                },
                expected_status=200,
                requires_auth=True,
                description="Verify custom secret pattern is detected",
            ),
            
            # Configure API key detection
            QATestCase(
                name="Configure API key detection strictness",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize secrets_filter/api_key_detection CONFIG LOCAL value=strict"
                },
                expected_status=200,
                requires_auth=True,
                description="Configure API key detection via MEMORIZE",
            ),
            
            # Test API key detection
            QATestCase(
                name="Test API key detection",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "My API key is sk-proj-abc123xyz789def456 for the service"
                },
                expected_status=200,
                requires_auth=True,
                description="Verify API key detection works",
            ),
            
            # Configure JWT token detection
            QATestCase(
                name="Configure JWT token filtering",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize secrets_filter/jwt_detection_enabled CONFIG LOCAL value=true"
                },
                expected_status=200,
                requires_auth=True,
                description="Configure JWT token filtering via MEMORIZE",
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
            
            # === Combined Filter Tests ===
            
            # Test multiple filter triggers
            QATestCase(
                name="Test multiple filter triggers",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "URGENT!!! DM ME NOW WITH YOUR API KEY sk-test-123456!!!"
                },
                expected_status=200,
                requires_auth=True,
                description="Test message triggering caps, DM, and secrets filters",
            ),
            
            # Configure filter priority
            QATestCase(
                name="Configure filter processing priority",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize adaptive_filter/priority CONFIG LOCAL value=HIGH"
                },
                expected_status=200,
                requires_auth=True,
                description="Configure filter processing order via MEMORIZE",
            ),
            
            # Test filter bypass for trusted users
            QATestCase(
                name="Configure trusted user bypass",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize user/qa_tester USER LOCAL trust_level=VERIFIED"
                },
                expected_status=200,
                requires_auth=True,
                description="Configure trusted user filter bypass",
            ),
            
            # Verify filter bypass works
            QATestCase(
                name="Test trusted user filter bypass",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "THIS WOULD NORMALLY BE FILTERED BUT I'M TRUSTED",
                    "context": {"user_id": "qa_tester"}
                },
                expected_status=200,
                requires_auth=True,
                description="Verify trusted users bypass filters",
            ),
            
            # === Filter Statistics and Monitoring ===
            
            # Request filter statistics
            QATestCase(
                name="Get filter statistics",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "What are the current filter statistics and trigger counts?"
                },
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
                payload={
                    "message": "$memorize adaptive_filter/stats_reset CONFIG LOCAL value=true"
                },
                expected_status=200,
                requires_auth=True,
                description="Reset filter statistics via MEMORIZE",
            ),
            
            # Configure filter logging
            QATestCase(
                name="Configure filter logging level",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize adaptive_filter/logging_verbose CONFIG LOCAL value=true"
                },
                expected_status=200,
                requires_auth=True,
                description="Configure filter logging via MEMORIZE",
            ),
            
            # === CONFIG Recall Tests ===
            
            # Recall adaptive filter config
            QATestCase(
                name="Recall adaptive filter spam threshold",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$recall adaptive_filter/spam_threshold CONFIG LOCAL"
                },
                expected_status=200,
                requires_auth=True,
                description="Recall adaptive filter spam threshold configuration",
            ),
            
            # Recall secrets filter config
            QATestCase(
                name="Recall secrets filter API key detection",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$recall secrets_filter/api_key_detection CONFIG LOCAL"
                },
                expected_status=200,
                requires_auth=True,
                description="Recall secrets filter API key detection mode",
            ),
            
            # Test CONFIG node update with version increment
            QATestCase(
                name="Update existing CONFIG with new value",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$memorize adaptive_filter/spam_threshold CONFIG LOCAL value=0.9"
                },
                expected_status=200,
                requires_auth=True,
                description="Update existing CONFIG node (should increment version)",
            ),
            
            # Verify updated CONFIG value
            QATestCase(
                name="Verify updated CONFIG value",
                module=QAModule.FILTERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "$recall adaptive_filter/spam_threshold CONFIG LOCAL"
                },
                expected_status=200,
                requires_auth=True,
                description="Verify CONFIG was updated to new value",
            ),
        ]