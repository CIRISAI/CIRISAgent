"""
QA Runner CLI interface.
"""

import argparse
import sys
from pathlib import Path
from typing import List

from .config import QAConfig, QAModule
from .runner import QARunner


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CIRIS QA Test Runner - Modular quality assurance testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all API tests
  python -m tools.qa_runner api_full

  # Run specific modules
  python -m tools.qa_runner auth telemetry agent

  # Run handler tests
  python -m tools.qa_runner handlers

  # Run everything
  python -m tools.qa_runner all

  # Run with custom configuration
  python -m tools.qa_runner auth --url http://localhost:8080 --no-auto-start

  # Run in parallel with JSON output
  python -m tools.qa_runner api_full --parallel --json --report-dir ./reports

Available modules:
  auth            - Authentication endpoints
  telemetry       - Telemetry and metrics
  agent           - Agent interaction
  system          - System management
  memory          - Memory operations
  audit           - Audit trail
  tools           - Tool management
  tasks           - Task management
  guidance        - Guidance system
  consent         - Consent management
  billing         - Billing and credit system
  handlers        - Message handlers
  simple_handlers - Simple handler tests
  streaming       - H3ERE pipeline streaming verification
  sdk             - SDK tests
  pause_step      - Enhanced single-step/pause debugging
  single_step_comprehensive - Complete 17-phase COVENANT single-step validation
  api_full        - All API modules
  handlers_full   - All handler modules
  all             - Everything
""",
    )

    parser.add_argument("modules", nargs="+", help="Modules to test (e.g., auth, telemetry, api_full, all)")

    # Server configuration
    parser.add_argument(
        "--url", default="http://localhost:8000", help="Base URL of the API server (default: http://localhost:8000)"
    )
    parser.add_argument("--port", type=int, default=8000, help="API server port (default: 8000)")
    parser.add_argument("--no-auto-start", action="store_true", help="Don't automatically start the API server")
    parser.add_argument("--no-mock-llm", action="store_true", help="Don't use mock LLM (requires real LLM)")
    parser.add_argument(
        "--adapter", default="api", choices=["api", "cli", "discord"], help="Adapter to use (default: api)"
    )

    # Authentication
    parser.add_argument("--username", default="admin", help="Admin username (default: admin)")
    parser.add_argument(
        "--password", default="ciris_admin_password", help="Admin password (default: ciris_admin_password)"
    )

    # Test configuration
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers (default: 4)")
    parser.add_argument("--timeout", type=float, default=300.0, help="Total timeout in seconds (default: 300)")
    parser.add_argument("--retry", type=int, default=3, help="Number of retries for failed tests (default: 3)")

    # Output configuration
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="Generate JSON report")
    parser.add_argument("--html", action="store_true", help="Generate HTML report")
    parser.add_argument("--report-dir", default="qa_reports", help="Directory for reports (default: qa_reports)")

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Parse modules
    modules: List[QAModule] = []
    for module_name in args.modules:
        try:
            module = QAModule(module_name.lower())
            modules.append(module)
        except ValueError:
            print(f"❌ Unknown module: {module_name}")
            print(f"Available modules: {', '.join(m.value for m in QAModule)}")
            sys.exit(1)

    # Create configuration
    config = QAConfig(
        base_url=args.url,
        api_port=args.port,
        admin_username=args.username,
        admin_password=args.password,
        parallel_tests=args.parallel,
        max_workers=args.workers,
        timeout=args.timeout,
        retry_count=args.retry,
        verbose=args.verbose,
        json_output=args.json,
        html_report=args.html,
        report_dir=Path(args.report_dir),
        auto_start_server=not args.no_auto_start,
        mock_llm=not args.no_mock_llm,
        adapter=args.adapter,
    )

    # Create and run runner
    runner = QARunner(config)
    success = runner.run(modules)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
