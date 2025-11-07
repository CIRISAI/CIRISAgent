"""
QA Runner configuration and module definitions.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class QAModule(Enum):
    """Available QA test modules."""

    # API modules
    AUTH = "auth"
    TELEMETRY = "telemetry"
    AGENT = "agent"
    SYSTEM = "system"
    MEMORY = "memory"
    AUDIT = "audit"
    TOOLS = "tools"
    TASKS = "tasks"
    GUIDANCE = "guidance"
    CONSENT = "consent"
    DSAR = "dsar"  # DSAR automation testing
    DSAR_MULTI_SOURCE = "dsar_multi_source"  # Multi-source DSAR orchestration testing
    PARTNERSHIP = "partnership"  # Partnership bilateral consent testing
    BILLING = "billing"
    BILLING_INTEGRATION = "billing_integration"  # Full OAuth user billing workflow
    MULTI_OCCURRENCE = "multi_occurrence"
    MESSAGE_ID_DEBUG = "message_id_debug"  # Message ID correlation debugging
    REDDIT = "reddit"  # Reddit adapter testing
    SQL_EXTERNAL_DATA = "sql_external_data"  # SQL external data service testing

    # Handler modules
    HANDLERS = "handlers"
    SIMPLE_HANDLERS = "simple_handlers"

    # Filter modules
    FILTERS = "filters"

    # SDK modules
    SDK = "sdk"

    # Extended modules
    EXTENDED_API = "extended_api"
    PAUSE_STEP = "pause_step"
    SINGLE_STEP_SIMPLE = "single_step_simple"
    SINGLE_STEP_COMPREHENSIVE = "single_step_comprehensive"
    STREAMING = "streaming"  # H3ERE pipeline streaming verification

    # Full suites
    API_FULL = "api_full"
    HANDLERS_FULL = "handlers_full"
    ALL = "all"


@dataclass
class QATestCase:
    """Definition of a QA test case."""

    name: str
    module: QAModule
    endpoint: str
    method: str = "GET"
    payload: Optional[Dict] = None
    expected_status: int = 200
    requires_auth: bool = True
    description: Optional[str] = None
    timeout: float = 30.0

    # Advanced validation
    validation_rules: Optional[Dict[str, Callable[[Dict], bool]]] = None
    custom_validation: Optional[Callable] = None
    custom_handler: Optional[str] = None  # For CUSTOM method tests

    # Test execution options
    repeat_count: int = 1


@dataclass
class QAConfig:
    """Configuration for QA runner."""

    # Server configuration
    base_url: str = "http://localhost:8000"
    api_port: int = 8000

    # Authentication
    admin_username: str = "admin"
    admin_password: str = "ciris_admin_password"

    # OAuth test user configuration (for billing integration tests)
    oauth_test_user_id: str = "google:999888777666555444"
    oauth_test_email: str = "test.billing@example.com"
    oauth_test_provider: str = "google"
    oauth_test_external_id: str = "999888777666555444"

    # Billing backend configuration (for billing integration tests)
    billing_enabled: bool = False
    billing_api_key: Optional[str] = None
    billing_api_url: str = "https://billing.ciris.ai"

    # Test configuration
    parallel_tests: bool = False
    max_workers: int = 4
    timeout: float = 300.0  # 5 minutes total timeout
    retry_count: int = 3
    retry_delay: float = 2.0

    # Output configuration
    verbose: bool = False
    json_output: bool = False
    html_report: bool = False
    report_dir: Path = Path("qa_reports")

    # Server management
    auto_start_server: bool = True
    server_startup_timeout: float = (
        180.0  # Startup with TSDB consolidation can take 45-60 seconds (up to 3 min for PostgreSQL with weekly consolidation)
    )
    mock_llm: bool = True
    adapter: str = "api"

    # Database backend configuration (for parallel testing)
    database_backends: List[str] = None  # None = ["sqlite"], or ["sqlite", "postgres"] for parallel
    postgres_url: str = "postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db"
    postgres_port: int = 8001  # Port for PostgreSQL backend server (SQLite uses api_port)
    parallel_backends: bool = False  # Run backend tests in parallel instead of sequentially

    def get_module_tests(self, module: QAModule) -> List[QATestCase]:
        """Get test cases for a specific module."""
        from .modules import APITestModule, HandlerTestModule, SDKTestModule
        from .modules.comprehensive_api_tests import ComprehensiveAPITestModule
        from .modules.comprehensive_single_step_tests import ComprehensiveSingleStepTestModule
        from .modules.filter_tests import FilterTestModule
        from .modules.multi_occurrence_tests import MultiOccurrenceTestModule
        from .modules.simple_single_step_tests import SimpleSingleStepTestModule

        # API test modules
        if module == QAModule.AUTH:
            return APITestModule.get_auth_tests()
        elif module == QAModule.TELEMETRY:
            return APITestModule.get_telemetry_tests()
        elif module == QAModule.AGENT:
            return APITestModule.get_agent_tests()
        elif module == QAModule.SYSTEM:
            return APITestModule.get_system_tests()
        elif module == QAModule.MEMORY:
            return APITestModule.get_memory_tests()
        elif module == QAModule.AUDIT:
            return APITestModule.get_audit_tests()
        elif module == QAModule.TOOLS:
            return APITestModule.get_tool_tests()
        elif module == QAModule.TASKS:
            return APITestModule.get_task_tests()
        elif module == QAModule.GUIDANCE:
            return APITestModule.get_guidance_tests()
        elif module == QAModule.CONSENT:
            # Consent tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.DSAR:
            # DSAR tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.DSAR_MULTI_SOURCE:
            # DSAR multi-source tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.PARTNERSHIP:
            # Partnership tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.BILLING:
            # Billing tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.BILLING_INTEGRATION:
            # Billing integration tests use SDK client with OAuth user
            return []  # Will be handled separately by runner
        elif module == QAModule.MULTI_OCCURRENCE:
            return MultiOccurrenceTestModule.get_all_multi_occurrence_tests()
        elif module == QAModule.MESSAGE_ID_DEBUG:
            # Message ID debug tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.REDDIT:
            # Reddit tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.SQL_EXTERNAL_DATA:
            # SQL external data tests use SDK client
            return []  # Will be handled separately by runner

        # Handler test modules
        elif module == QAModule.HANDLERS:
            return HandlerTestModule.get_handler_tests()
        elif module == QAModule.SIMPLE_HANDLERS:
            return HandlerTestModule.get_simple_handler_tests()

        # Filter test modules
        elif module == QAModule.FILTERS:
            return FilterTestModule.get_filter_tests()

        # SDK test modules
        elif module == QAModule.SDK:
            return SDKTestModule.get_sdk_tests()

        # Extended API tests
        elif module == QAModule.EXTENDED_API:
            return ComprehensiveAPITestModule.get_all_extended_tests()

        # Pause/step testing (redirected to comprehensive single-step)
        elif module == QAModule.PAUSE_STEP:
            return ComprehensiveSingleStepTestModule.get_comprehensive_single_step_tests()

        # Simple single-step testing
        elif module == QAModule.SINGLE_STEP_SIMPLE:
            return SimpleSingleStepTestModule.get_simple_single_step_tests()

        # Comprehensive single-step testing
        elif module == QAModule.SINGLE_STEP_COMPREHENSIVE:
            return ComprehensiveSingleStepTestModule.get_comprehensive_single_step_tests()

        # Streaming verification
        elif module == QAModule.STREAMING:
            from .modules.streaming_verification import StreamingVerificationModule

            return StreamingVerificationModule.get_streaming_verification_tests()

        # Aggregate modules
        elif module == QAModule.API_FULL:
            tests = []
            for m in [
                QAModule.AUTH,
                QAModule.TELEMETRY,
                QAModule.AGENT,
                QAModule.SYSTEM,
                QAModule.MEMORY,
                QAModule.AUDIT,
                QAModule.TOOLS,
                QAModule.TASKS,
                QAModule.GUIDANCE,
            ]:
                tests.extend(self.get_module_tests(m))
            return tests

        elif module == QAModule.HANDLERS_FULL:
            tests = []
            for m in [QAModule.HANDLERS, QAModule.SIMPLE_HANDLERS]:
                tests.extend(self.get_module_tests(m))
            return tests

        elif module == QAModule.ALL:
            tests = []
            # Run all modules in sequence - comprehensive test suite
            for m in [
                # Streaming tests FIRST (requires clean queue state)
                QAModule.STREAMING,
                # Core API modules
                QAModule.AUTH,
                QAModule.TELEMETRY,
                QAModule.AGENT,
                QAModule.SYSTEM,
                QAModule.MEMORY,
                QAModule.AUDIT,
                QAModule.TOOLS,
                QAModule.TASKS,
                QAModule.GUIDANCE,
                QAModule.CONSENT,
                QAModule.DSAR,
                QAModule.DSAR_MULTI_SOURCE,
                QAModule.PARTNERSHIP,
                QAModule.BILLING,
                QAModule.REDDIT,
                QAModule.SQL_EXTERNAL_DATA,
                QAModule.MULTI_OCCURRENCE,
                # Handler modules
                QAModule.HANDLERS,
                QAModule.SIMPLE_HANDLERS,
                # Filter modules
                QAModule.FILTERS,
                # SDK modules
                QAModule.SDK,
                # Extended modules
                QAModule.EXTENDED_API,
                QAModule.SINGLE_STEP_SIMPLE,
                QAModule.SINGLE_STEP_COMPREHENSIVE,
            ]:
                tests.extend(self.get_module_tests(m))
            return tests

        return []
