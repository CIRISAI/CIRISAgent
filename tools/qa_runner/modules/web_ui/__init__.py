"""
Web UI QA Runner Module

End-to-end browser testing for CIRIS web interface.
Uses Playwright with Firefox for cross-platform testing.

Usage:
    # As CLI
    python -m tools.qa_runner.modules.web_ui e2e --wipe

    # As library
    from tools.qa_runner.modules.web_ui import run_web_ui_tests
    suite = await run_web_ui_tests(wipe_data=True, provider="openrouter")
"""

# Browser automation
from .browser_helper import (
    BrowserConfig,
    BrowserHelper,
    Screenshot,
    check_playwright_installed,
    ensure_playwright_installed,
)

# Server lifecycle management
from .server_manager import ServerConfig, ServerManager, ServerStatus

# Test cases
from .test_cases import (
    TestReport,
    TestResult,
    WebUITestConfig,
    test_complete_setup,
    test_enter_api_key,
    test_full_e2e_flow,
    test_live_model_listing,
    test_load_models,
    test_load_setup_wizard,
    test_navigate_to_llm_config,
    test_receive_response,
    test_select_model,
    test_select_provider,
    test_send_message,
)

# Test runner
from .test_runner import WebUITestRunner, WebUITestSuite, run_web_ui_tests

__all__ = [
    # Browser
    "BrowserConfig",
    "BrowserHelper",
    "Screenshot",
    "check_playwright_installed",
    "ensure_playwright_installed",
    # Server
    "ServerConfig",
    "ServerManager",
    "ServerStatus",
    # Test config and results
    "TestReport",
    "TestResult",
    "WebUITestConfig",
    # Test cases
    "test_load_setup_wizard",
    "test_navigate_to_llm_config",
    "test_select_provider",
    "test_enter_api_key",
    "test_load_models",
    "test_live_model_listing",
    "test_select_model",
    "test_complete_setup",
    "test_send_message",
    "test_receive_response",
    "test_full_e2e_flow",
    # Runner
    "WebUITestRunner",
    "WebUITestSuite",
    "run_web_ui_tests",
]
