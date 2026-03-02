"""
Desktop App QA Runner Module

End-to-end UI testing for CIRIS Desktop application.
Uses the embedded TestAutomationServer for native Compose Desktop automation.

Usage:
    # As CLI
    python -m tools.qa_runner.modules.web_ui desktop --help

    # As library
    from tools.qa_runner.modules.web_ui import DesktopAppHelper
    helper = await DesktopAppHelper().start()
    await helper.click("btn_login_submit")
"""

# Legacy browser automation (still available for web testing)
from .browser_helper import BrowserConfig, BrowserHelper
from .browser_helper import ElementInfo as BrowserElementInfo
from .browser_helper import check_playwright_installed, ensure_playwright_installed

# Desktop app automation (primary - uses embedded TestAutomationServer)
from .desktop_app_helper import DesktopAppConfig, DesktopAppHelper
from .desktop_app_helper import ElementInfo as DesktopElementInfo
from .desktop_app_helper import Screenshot, check_desktop_app_running, ensure_desktop_app_running

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
    # Desktop App (primary)
    "DesktopAppConfig",
    "DesktopAppHelper",
    "DesktopElementInfo",
    "check_desktop_app_running",
    "ensure_desktop_app_running",
    # Browser (legacy)
    "BrowserConfig",
    "BrowserHelper",
    "BrowserElementInfo",
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
