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
    SINGLE_STEP_COMPREHENSIVE = "single_step_comprehensive"

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
    server_startup_timeout: float = 30.0  # Normal startup with wakeup takes ~10-15 seconds
    mock_llm: bool = True
    adapter: str = "api"

    def get_module_tests(self, module: QAModule) -> List[QATestCase]:
        """Get test cases for a specific module."""
        from .modules import APITestModule, HandlerTestModule, SDKTestModule
        from .modules.comprehensive_api_tests import ComprehensiveAPITestModule
        from .modules.filter_tests import FilterTestModule
        from .modules.pause_step_tests import PauseStepTestModule
        from .modules.comprehensive_single_step_tests import ComprehensiveSingleStepTestModule

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
        
        # Pause/step testing
        elif module == QAModule.PAUSE_STEP:
            return PauseStepTestModule.get_all_pause_step_tests()
        
        # Comprehensive single-step testing
        elif module == QAModule.SINGLE_STEP_COMPREHENSIVE:
            return ComprehensiveSingleStepTestModule.get_comprehensive_single_step_tests()

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
            for m in [QAModule.API_FULL, QAModule.HANDLERS_FULL, QAModule.FILTERS, QAModule.SDK]:
                tests.extend(self.get_module_tests(m))
            return tests

        return []
