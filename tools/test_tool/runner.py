"""Main test runner implementation."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .config import CONTAINER_NAME, DEFAULT_COMPOSE_FILE, STATUS_FILE, TEST_OUTPUT_DIR
from .docker import DockerManager
from .log_parser import LogParser
from .pytest_cmd import build_pytest_command


class TestRunner:
    """Manages background test execution in Docker containers."""

    def __init__(self):
        TEST_OUTPUT_DIR.mkdir(exist_ok=True)

    def start(
        self,
        coverage: bool = False,
        coverage_path: Optional[str] = None,
        filter_pattern: Optional[str] = None,
        test_path: Optional[str] = None,
        compose_file: str = DEFAULT_COMPOSE_FILE,
        rebuild: bool = True,
        markers: Optional[List[str]] = None,
        parallel: Optional[int] = None,
        verbose: int = 1,
    ) -> str:
        """
        Start a new test run in the background.

        Args:
            coverage: Run with coverage reporting
            filter_pattern: Pytest -k filter pattern
            test_path: Specific test file or test to run
            compose_file: Docker compose file to use
            rebuild: Whether to rebuild container before running
            markers: Pytest markers to filter by
            parallel: Number of parallel workers
            verbose: Verbosity level (0-3)

        Returns:
            Run ID or empty string if failed
        """
        # Check if already running
        if self.is_running():
            print("[WARN] Tests already running. Use 'status' to check or 'stop' to cancel.")
            return ""

        # Docker manager
        docker = DockerManager(compose_file)

        # Rebuild container if requested
        if rebuild:
            success, message = docker.rebuild_container()
            if not success:
                print(f"[FAIL] {message}")
                return ""
            print(f"[OK] {message}")

        # Generate run ID
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = TEST_OUTPUT_DIR / f"test_run_{run_id}.log"

        # Build pytest command
        pytest_cmd = build_pytest_command(
            coverage=coverage,
            coverage_path=coverage_path,
            filter_pattern=filter_pattern,
            test_path=test_path,
            markers=markers,
            parallel=parallel,
            verbose=verbose,
        )

        # Start process
        process = docker.run_command(pytest_cmd, CONTAINER_NAME, output_file)

        # Save status
        status = {
            "run_id": run_id,
            "pid": process.pid,
            "start_time": datetime.now().isoformat(),
            "output_file": str(output_file),
            "coverage": coverage,
            "filter": filter_pattern,
            "test_path": test_path,
            "command": pytest_cmd,
        }

        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)

        print(f"[OK] Test run started: {run_id}")
        print(f"   Output: {output_file}")
        print(f"   Command: {pytest_cmd}")
        if test_path:
            print(f"   Running: {test_path}")
        print("\nUse 'python tools/test_tool status' to check progress")

        return run_id

    def is_running(self) -> bool:
        """Check if tests are currently running."""
        if not STATUS_FILE.exists():
            return False

        try:
            with open(STATUS_FILE, "r") as f:
                status = json.load(f)

            pid = status.get("pid")
            if pid:
                # Check if process is still running
                try:
                    os.kill(pid, 0)  # sonar-hotspot: safe - signal 0 only checks if process exists, doesn't terminate
                    return True
                except ProcessLookupError:
                    return False
        except Exception:
            return False

        return False

    def show_status(self):
        """Show current test run status."""
        if not STATUS_FILE.exists():
            print("[FAIL] No test run found")
            return

        with open(STATUS_FILE, "r") as f:
            status = json.load(f)

        run_id = status["run_id"]
        output_file = Path(status["output_file"])

        print(f"Test Run: {run_id}")
        print(f"Started: {status['start_time']}")

        if self.is_running():
            print("Status: Running")
        else:
            # Parse log file to determine success/failure
            if output_file.exists():
                parser = LogParser(output_file)
                results = parser.parse_test_results()
                failed = len([r for r in results if r.status in ("FAILED", "ERROR")])
                if failed > 0:
                    print("Status: Completed - FAILED")
                else:
                    print("Status: [OK] Completed - SUCCESS")
            else:
                print("Status: [WARN] Completed - UNKNOWN")

        # Parse log file for test counts
        if output_file.exists():
            parser = LogParser(output_file)
            results = parser.parse_test_results()

            passed = len([r for r in results if r.status == "PASSED"])
            failed = len([r for r in results if r.status in ("FAILED", "ERROR")])

            print(f"\nTests: {passed} passed, {failed} failed")
            print(f"Output lines: {len(parser._lines)}")

            # Show last few lines
            print("\nLast 10 lines:")
            print("-" * 70)
            for line in parser._lines[-10:]:
                print(line.rstrip())

    def logs(self, tail: int = 50, errors_only: bool = False):
        """
        Show test output logs.

        Args:
            tail: Number of lines to show from end (0 for all)
            errors_only: Only show failures and errors with context
        """
        if not STATUS_FILE.exists():
            print("[FAIL] No test run found")
            return

        with open(STATUS_FILE, "r") as f:
            status = json.load(f)

        output_file = Path(status["output_file"])
        if not output_file.exists():
            print("[FAIL] Output file not found")
            return

        parser = LogParser(output_file)

        if errors_only:
            errors = parser.parse_errors()
            if not errors:
                print("[OK] No errors found!")
                return

            print(f"Found {len(errors)} errors:\n")
            print("=" * 80)

            for error in errors:
                print(f"TEST: {error.test_name}")
                print(f"ERROR: {error.error_type}")
                print(f"MESSAGE: {error.error_message}")
                print("\nTRACEBACK:")
                for line in error.traceback:
                    print(line)
                if error.captured_output:
                    print("\nCAPTURED OUTPUT:")
                    print(error.captured_output)
                print("=" * 80)
        else:
            # Show raw log
            with open(output_file, "r") as f:
                lines = f.readlines()

            if tail > 0:
                lines = lines[-tail:]

            for line in lines:
                print(line.rstrip())

    def stop(self):
        """Stop the current test run."""
        if not self.is_running():
            print("[FAIL] No test running")
            return

        docker = DockerManager()
        if docker.stop_container(CONTAINER_NAME):
            print("[OK] Test run stopped")
        else:
            print("[FAIL] Failed to stop test run")

    def results(self):
        """Show test results summary."""
        if not STATUS_FILE.exists():
            print("[FAIL] No test run found")
            return

        with open(STATUS_FILE, "r") as f:
            status = json.load(f)

        output_file = Path(status["output_file"])
        if not output_file.exists():
            print("[FAIL] Output file not found")
            return

        parser = LogParser(output_file)
        summary = parser.get_summary()

        print(f"Test Run: {status['run_id']}")
        print(f"Command: {status['command']}")
        print("=" * 70)
        print(f"Total Tests: {summary['total']}")
        print(f"Passed: {summary['passed']} [OK]")
        print(f"Failed: {summary['failed']} [FAIL]")
        print(f"Skipped: {summary['skipped']} ⏭")

        if summary["coverage"] is not None:
            print(f"\nCoverage: {summary['coverage']}%")

        if summary["failed_tests"]:
            print("\nFailed Tests:")
            for test in summary["failed_tests"]:
                print(f" [FAIL] {test}")

    def run_single_test(
        self, test_path: str, coverage: bool = False, coverage_path: Optional[str] = None, rebuild: bool = True
    ) -> str:
        """
        Convenience method to run a single test.

        Args:
            test_path: Path to test file or specific test
                      e.g., "tests/test_foo.py::TestClass::test_method"
            coverage: Run with coverage
            coverage_path: Specific path to measure coverage for
            rebuild: Rebuild container first

        Returns:
            Run ID
        """
        return self.start(test_path=test_path, coverage=coverage, coverage_path=coverage_path, rebuild=rebuild)
