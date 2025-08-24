"""
QA Runner configuration and module definitions.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


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

    # Handler modules
    HANDLERS = "handlers"
    SIMPLE_HANDLERS = "simple_handlers"

    # SDK modules
    SDK = "sdk"
    SDK_COMPREHENSIVE = "sdk_comprehensive"

    # Full suites
    API_FULL = "api_full"
    HANDLERS_FULL = "handlers_full"
    ALL = "all"


@dataclass
class QATestCase:
    """Definition of a QA test case."""

    name: str
    module: QAModule
    endpoint: Optional[str] = None
    method: str = "GET"
    payload: Optional[Dict] = None
    expected_status: int = 200
    requires_auth: bool = True
    description: Optional[str] = None
    timeout: float = 30.0


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
    server_startup_timeout: float = 60.0
    mock_llm: bool = True
    adapter: str = "api"

    def get_module_tests(self, module: QAModule) -> List[QATestCase]:
        """Get test cases for a specific module."""

        # Define test cases for each module
        test_definitions = {
            QAModule.AUTH: [
                QATestCase(
                    "Login",
                    QAModule.AUTH,
                    "/v1/auth/login",
                    "POST",
                    {"username": self.admin_username, "password": self.admin_password},
                    requires_auth=False,
                ),
                QATestCase("Current User", QAModule.AUTH, "/v1/auth/me", "GET"),
                QATestCase("List Users", QAModule.AUTH, "/v1/auth/users", "GET"),
            ],
            QAModule.TELEMETRY: [
                QATestCase("Unified Telemetry", QAModule.TELEMETRY, "/v1/telemetry/unified", "GET"),
                QATestCase("Service Health", QAModule.TELEMETRY, "/v1/telemetry/services", "GET"),
                QATestCase("System Metrics", QAModule.TELEMETRY, "/v1/telemetry/metrics", "GET"),
            ],
            QAModule.AGENT: [
                QATestCase("Agent Status", QAModule.AGENT, "/v1/agent/status", "GET"),
                QATestCase(
                    "Agent Interact", QAModule.AGENT, "/v1/agent/interact", "POST", {"message": "Hello, how are you?"}
                ),
                QATestCase("Agent History", QAModule.AGENT, "/v1/agent/history", "GET"),
            ],
            QAModule.SYSTEM: [
                QATestCase("System Status", QAModule.SYSTEM, "/v1/system/status", "GET"),
                QATestCase("List Adapters", QAModule.SYSTEM, "/v1/system/adapters", "GET"),
                QATestCase("Processing Queue", QAModule.SYSTEM, "/v1/system/queue", "GET"),
            ],
            QAModule.MEMORY: [
                QATestCase(
                    "Search Memory", QAModule.MEMORY, "/v1/memory/search", "POST", {"query": "test", "limit": 10}
                ),
                QATestCase("Memory Stats", QAModule.MEMORY, "/v1/memory/stats", "GET"),
            ],
            QAModule.AUDIT: [
                QATestCase("Audit Events", QAModule.AUDIT, "/v1/audit/events", "GET"),
                QATestCase("Verify Chain", QAModule.AUDIT, "/v1/audit/verify", "GET"),
            ],
            QAModule.TOOLS: [
                QATestCase("List Tools", QAModule.TOOLS, "/v1/tools", "GET"),
                QATestCase("Tool Info", QAModule.TOOLS, "/v1/tools/list_files", "GET"),
            ],
            QAModule.TASKS: [
                QATestCase("List Tasks", QAModule.TASKS, "/v1/tasks", "GET"),
                QATestCase(
                    "Create Task", QAModule.TASKS, "/v1/tasks", "POST", {"description": "Test task", "priority": 5}
                ),
            ],
            QAModule.GUIDANCE: [
                QATestCase(
                    "Request Guidance",
                    QAModule.GUIDANCE,
                    "/v1/guidance/request",
                    "POST",
                    {"thought_id": "test-thought", "context": {"test": "context"}},
                ),
            ],
            QAModule.HANDLERS: [
                QATestCase(
                    "Test Greeting Handler", QAModule.HANDLERS, "/v1/agent/interact", "POST", {"message": "Hello CIRIS"}
                ),
                QATestCase(
                    "Test Help Handler", QAModule.HANDLERS, "/v1/agent/interact", "POST", {"message": "I need help"}
                ),
                QATestCase(
                    "Test Time Handler",
                    QAModule.HANDLERS,
                    "/v1/agent/interact",
                    "POST",
                    {"message": "What time is it?"},
                ),
            ],
            QAModule.SIMPLE_HANDLERS: [
                QATestCase(
                    "Simple Greeting", QAModule.SIMPLE_HANDLERS, "/v1/agent/interact", "POST", {"message": "Hi"}
                ),
                QATestCase(
                    "Simple Question",
                    QAModule.SIMPLE_HANDLERS,
                    "/v1/agent/interact",
                    "POST",
                    {"message": "How are you?"},
                ),
            ],
        }

        # Handle aggregate modules
        if module == QAModule.API_FULL:
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
                tests.extend(test_definitions.get(m, []))
            return tests

        elif module == QAModule.HANDLERS_FULL:
            tests = []
            for m in [QAModule.HANDLERS, QAModule.SIMPLE_HANDLERS]:
                tests.extend(test_definitions.get(m, []))
            return tests

        elif module == QAModule.ALL:
            tests = []
            for m in test_definitions:
                tests.extend(test_definitions[m])
            return tests

        return test_definitions.get(module, [])
