#!/usr/bin/env python3
"""
Web UI QA Runner CLI

End-to-end web UI testing for CIRIS.

Usage:
    python -m tools.qa_runner.modules.web_ui [command] [options]

Commands:
    e2e         Run full end-to-end test flow (default)
    setup       Test only setup wizard steps
    interact    Test only interaction steps
    models      Test only model listing feature
    list        List available tests

Examples:
    # Full E2E test with data wipe
    python -m tools.qa_runner.modules.web_ui e2e --wipe

    # Test with OpenRouter provider
    python -m tools.qa_runner.modules.web_ui e2e --provider openrouter

    # Run specific tests
    python -m tools.qa_runner.modules.web_ui --tests load_setup,select_provider,enter_key

    # Headless mode (no browser window)
    python -m tools.qa_runner.modules.web_ui e2e --headless

    # Use mock LLM (no API key needed)
    python -m tools.qa_runner.modules.web_ui e2e --mock-llm
"""

import argparse
import asyncio
import os
import sys
from typing import List, Optional

from .browser_helper import BrowserConfig, ensure_playwright_installed
from .server_manager import ServerConfig
from .test_cases import WebUITestConfig
from .test_runner import WebUITestRunner, run_web_ui_tests


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CIRIS Web UI QA Runner - End-to-end browser testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s e2e --wipe                    Full E2E test with clean slate
  %(prog)s setup --provider anthropic    Test setup wizard with Anthropic
  %(prog)s models                        Test only model listing feature
  %(prog)s --tests load_setup,enter_key  Run specific tests
  %(prog)s e2e --headless --mock-llm     Headless with mock LLM
        """,
    )

    # Commands
    parser.add_argument(
        "command",
        nargs="?",
        default="e2e",
        choices=["e2e", "setup", "interact", "models", "list"],
        help="Test command to run (default: e2e)",
    )

    # Server options
    parser.add_argument(
        "--wipe",
        action="store_true",
        default=True,
        help="Wipe all data before testing (clean slate) - enabled by default",
    )
    parser.add_argument(
        "--no-wipe",
        action="store_true",
        help="Don't wipe data (continue from existing state)",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock LLM (no API key needed)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Server port (default: 8080)",
    )

    # Browser options
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no window)",
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        help="Slow down browser actions by N milliseconds",
    )

    # LLM options
    parser.add_argument(
        "--provider",
        default="openrouter",
        choices=["openai", "anthropic", "openrouter", "groq", "google", "together", "local"],
        help="LLM provider (default: openrouter)",
    )
    parser.add_argument(
        "--api-key",
        help="API key (or set LLM_API_KEY env var, or use ~/.provider_key file)",
    )
    parser.add_argument(
        "--model",
        help="Specific model to select (default: auto-select recommended)",
    )

    # Test options
    parser.add_argument(
        "--tests",
        help="Comma-separated list of specific tests to run",
    )
    parser.add_argument(
        "--output-dir",
        default="web_ui_qa_reports",
        help="Directory for screenshots and reports",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Server startup timeout in seconds",
    )

    # Verbosity
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    # Keep open
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep browser and server running after tests (for demos)",
    )

    return parser.parse_args()


def list_tests() -> None:
    """List available tests."""
    print("\n📋 Available Tests:\n")

    test_info = {
        "load_setup": "Load the setup wizard page",
        "navigate_llm": "Navigate to LLM configuration step",
        "select_provider": "Select LLM provider (OpenAI, Anthropic, etc.)",
        "enter_key": "Enter API key",
        "load_models": "Load available models (live model listing)",
        "select_model": "Select a model from the list",
        "complete_setup": "Complete remaining setup steps",
        "send_message": "Send a test message to the agent",
        "receive_response": "Wait for and validate agent response",
    }

    for name, desc in test_info.items():
        print(f"  • {name:20s} - {desc}")

    print("\n🔄 Test Groups:\n")
    print("  • e2e       - All tests in sequence")
    print("  • setup     - Setup wizard tests only (load_setup through complete_setup)")
    print("  • interact  - Interaction tests only (send_message, receive_response)")
    print("  • models    - Model listing tests only (load_setup through load_models)")

    print("\n💡 Examples:\n")
    print("  python -m tools.qa_runner.modules.web_ui e2e --wipe")
    print("  python -m tools.qa_runner.modules.web_ui --tests load_setup,enter_key,load_models")
    print()


def get_test_list(command: str, specific_tests: Optional[str]) -> Optional[List[str]]:
    """Get list of tests to run based on command and specific tests."""
    if specific_tests:
        return [t.strip() for t in specific_tests.split(",")]

    test_groups = {
        "e2e": None,  # Full flow
        "setup": [
            "load_setup",
            "navigate_llm",
            "select_provider",
            "enter_key",
            "load_models",
            "select_model",
            "complete_setup",
        ],
        "interact": [
            "send_message",
            "receive_response",
        ],
        "models": [
            "load_setup",
            "navigate_llm",
            "select_provider",
            "enter_key",
            "load_models",
        ],
    }

    return test_groups.get(command)


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Handle list command
    if args.command == "list":
        list_tests()
        return 0

    # Ensure Playwright is installed
    print("🔍 Checking Playwright installation...")
    try:
        ensure_playwright_installed()
        print("✅ Playwright ready")
    except Exception as e:
        print(f"❌ Playwright setup failed: {e}")
        print("   Run: pip install playwright && playwright install firefox")
        return 1

    # Build configs
    server_config = ServerConfig(
        port=args.port,
        wipe_data=args.wipe and not args.no_wipe,
        mock_llm=args.mock_llm,
        startup_timeout=args.timeout,
    )

    browser_config = BrowserConfig(
        headless=args.headless,
        slow_mo=args.slow_mo,
        screenshot_dir=args.output_dir,
    )

    test_config = WebUITestConfig.from_env()
    test_config.llm_provider = args.provider

    if args.api_key:
        test_config.llm_api_key = args.api_key

    if args.model:
        test_config.llm_model = args.model

    # Get tests to run
    tests = get_test_list(args.command, args.tests)

    # Create runner
    runner = WebUITestRunner(
        server_config=server_config,
        browser_config=browser_config,
        test_config=test_config,
        keep_open=args.keep_open,
    )

    # Run tests
    if tests:
        suite = await runner.run_selected_tests(tests)
    else:
        suite = await runner.run_e2e_flow()

    # Print summary and save report
    runner.print_summary(suite)
    report_path = runner.save_report(suite)
    print(f"📄 Report saved: {report_path}")

    return 0 if suite.success else 1


def run() -> None:
    """Entry point for console script."""
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(130)


if __name__ == "__main__":
    run()
