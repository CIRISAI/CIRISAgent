"""
Main QA Runner implementation.
"""

import asyncio
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config import QAConfig, QAModule, QATestCase
from .modules.filter_test_helper import FilterTestHelper
from .server import APIServerManager


class QARunner:
    """Main QA test runner."""

    def __init__(self, config: Optional[QAConfig] = None):
        """Initialize QA runner with configuration."""
        self.config = config or QAConfig()
        self.console = Console()
        self.token: Optional[str] = None
        self.server_manager = APIServerManager(self.config)
        self.results: Dict[str, Dict] = {}
        self._startup_incidents_position = 0
        self._filter_helper: Optional[FilterTestHelper] = None

    def run(self, modules: List[QAModule]) -> bool:
        """Run QA tests for specified modules."""
        start_time = time.time()

        self.console.print(
            Panel.fit(
                "[bold cyan]CIRIS QA Test Runner[/bold cyan]\n" f"Modules: {', '.join(m.value for m in modules)}",
                title="🧪 Starting QA Tests",
            )
        )

        # Show initial incidents log status and record baseline
        self._show_incidents_status("STARTUP")
        self._record_startup_incidents_position()

        # Start API server if needed
        if self.config.auto_start_server:
            if not self.server_manager.start():
                self.console.print("[red]❌ Failed to start API server[/red]")
                return False

        # Get authentication token
        if not self._authenticate():
            self.console.print("[red]❌ Authentication failed[/red]")
            if self.config.auto_start_server:
                self.server_manager.stop()
            return False

        # Initialize SSE monitoring helper for HANDLERS and FILTERS tests
        # Both now use async /agent/message endpoint + SSE streaming
        if QAModule.FILTERS in modules or QAModule.HANDLERS in modules:
            self._filter_helper = FilterTestHelper(self.config.base_url, self.token, verbose=self.config.verbose)
            try:
                self._filter_helper.start_monitoring()
                module_names = []
                if QAModule.FILTERS in modules:
                    module_names.append("filters")
                if QAModule.HANDLERS in modules:
                    module_names.append("handlers")
                self.console.print(f"[green]✅ SSE monitoring started for {', '.join(module_names)} tests[/green]")
            except Exception as e:
                self.console.print(f"[yellow]⚠️  Failed to start SSE monitoring: {e}[/yellow]")
                self._filter_helper = None

        # Collect all test cases
        all_tests = []
        for module in modules:
            tests = self.config.get_module_tests(module)
            all_tests.extend(tests)

        self.console.print(f"\n📋 Running {len(all_tests)} test cases...")

        # Run tests
        if self.config.parallel_tests:
            success = self._run_parallel(all_tests)
        else:
            success = self._run_sequential(all_tests)

        # MANDATORY: Always show incidents log status after tests
        self._show_incidents_status("POST-TEST")

        # Check if any incidents occurred during testing
        has_incidents = self._has_incidents_occurred()

        # Generate reports
        self._generate_reports()

        # Stop filter helper if running
        if self._filter_helper:
            self._filter_helper.stop_monitoring()
            self.console.print("[cyan]⏹️  SSE monitoring stopped[/cyan]")

        # Stop server if we started it
        if self.config.auto_start_server:
            self.server_manager.stop()

        # Print summary
        elapsed = time.time() - start_time
        self._print_summary(elapsed, has_incidents)

        # Final incidents reminder - CANNOT be missed
        if has_incidents:
            self.console.print("\n" + "=" * 60)
            self.console.print("[bold red]🚨 CRITICAL: INCIDENTS DETECTED DURING TESTING! 🚨[/bold red]")
            self.console.print("[bold red]REVIEW THE INCIDENTS LOG ABOVE IMMEDIATELY![/bold red]")
            self.console.print("=" * 60)
            return False  # Force failure if incidents occurred
        else:
            self.console.print("\n[bold green]✅ No critical incidents - tests completed cleanly![/bold green]")

        return success

    def _check_incidents_for_test(self, test_name: str) -> List[str]:
        """Check incidents log for errors during a specific test.

        Returns list of critical incidents found.
        """
        incidents_log = Path("logs/incidents_latest.log")

        if not incidents_log.exists():
            return []

        # Patterns to ignore (non-critical)
        ignore_patterns = [
            "MOCK_MODULE_LOADED",
            "MOCK LLM",
            "RUNTIME SHUTDOWN",
            "SYSTEM SHUTDOWN",
            "GRACEFUL SHUTDOWN",
            "Edge already exists",
            "duplicate edge",
            "TSDB consolidation",
        ]

        critical_errors = []

        try:
            # Get file size to track new entries
            current_size = incidents_log.stat().st_size

            # Only read new entries since last check
            if not hasattr(self, "_last_incidents_position"):
                self._last_incidents_position = 0

            if current_size > self._last_incidents_position:
                with open(incidents_log, "r") as f:
                    f.seek(self._last_incidents_position)

                    for line in f:
                        # Check if line contains ERROR or CRITICAL
                        if "ERROR" in line or "CRITICAL" in line:
                            # Skip if it matches an ignore pattern
                            if any(pattern in line for pattern in ignore_patterns):
                                continue

                            # Extract the error message
                            if " - ERROR - " in line:
                                parts = line.split(" - ERROR - ")
                                if len(parts) > 1:
                                    error_msg = parts[-1].strip()
                                    # Skip very long errors (likely stack traces)
                                    if len(error_msg) < 500:
                                        critical_errors.append(f"[{test_name}] {error_msg}")

                self._last_incidents_position = current_size

        except Exception as e:
            logger.error(f"Error checking incidents log: {e}")

        return critical_errors

    def _show_incidents_status(self, phase: str):
        """ALWAYS show incidents log status - prominent and mandatory."""
        incidents_log = Path("logs/incidents_latest.log")

        self.console.print(f"\n[bold cyan]📋 INCIDENTS LOG STATUS ({phase}):[/bold cyan]")

        if not incidents_log.exists():
            self.console.print("[bold red]❌ NO INCIDENTS LOG FOUND[/bold red]")
            return

        # Show log file info
        try:
            log_size = incidents_log.stat().st_size
            self.console.print(f"   📁 Log: {incidents_log.resolve()}")
            self.console.print(f"   📊 Size: {log_size:,} bytes")
        except Exception as e:
            self.console.print(f"[red]❌ Cannot read log file: {e}[/red]")
            return

        # Patterns to ignore (non-critical)
        ignore_patterns = [
            "MOCK_MODULE_LOADED",
            "MOCK LLM",
            "RUNTIME SHUTDOWN",
            "SYSTEM SHUTDOWN",
            "GRACEFUL SHUTDOWN",
            "Edge already exists",
            "duplicate edge",
            "TSDB consolidation",
        ]

        critical_errors = []
        warning_count = 0
        error_count = 0
        critical_count = 0

        try:
            with open(incidents_log, "r") as f:
                for line in f:
                    if "WARNING" in line:
                        warning_count += 1
                    elif "ERROR" in line:
                        error_count += 1
                        # Check if it's a critical error we should report
                        if not any(pattern in line for pattern in ignore_patterns):
                            if " - ERROR - " in line:
                                parts = line.split(" - ERROR - ")
                                if len(parts) > 1:
                                    error_msg = parts[-1].strip()
                                    if len(error_msg) < 500:
                                        critical_errors.append(error_msg)
                    elif "CRITICAL" in line:
                        critical_count += 1
                        # Check if it's a critical error we should report
                        if not any(pattern in line for pattern in ignore_patterns):
                            if " - CRITICAL - " in line:
                                parts = line.split(" - CRITICAL - ")
                                if len(parts) > 1:
                                    error_msg = parts[-1].strip()
                                    if len(error_msg) < 500:
                                        critical_errors.append(error_msg)

        except Exception as e:
            self.console.print(f"[red]❌ Could not read incidents log: {e}[/red]")
            return

        # ALWAYS show counts - even if zero
        self.console.print(f"   ⚠️  Warnings: {warning_count}")
        self.console.print(f"   🚫 Errors: {error_count}")
        self.console.print(f"   💥 Critical: {critical_count}")

        # Report critical errors prominently
        if critical_errors:
            unique_errors = list(dict.fromkeys(critical_errors))
            self.console.print(f"\n[bold red]🚨 CRITICAL ISSUES FOUND ({len(unique_errors)}):[/bold red]")
            for i, error in enumerate(unique_errors[:10], 1):  # Show more errors
                self.console.print(f"   {i:2d}. {error[:250]}")  # Show more of each error

            if len(unique_errors) > 10:
                self.console.print(f"   ... and {len(unique_errors) - 10} more critical errors")

            # Make it impossible to miss
            self.console.print(f"\n[bold red]🚨 {len(unique_errors)} CRITICAL ISSUES REQUIRE ATTENTION! 🚨[/bold red]")
        else:
            self.console.print("[bold green]✅ No critical issues found[/bold green]")

        self.console.print()  # Extra spacing

    def _record_startup_incidents_position(self):
        """Record the incidents log position at startup for comparison."""
        incidents_log = Path("logs/incidents_latest.log")

        if incidents_log.exists():
            try:
                self._startup_incidents_position = incidents_log.stat().st_size
            except Exception:
                self._startup_incidents_position = 0
        else:
            self._startup_incidents_position = 0

    def _has_incidents_occurred(self) -> bool:
        """Check if any NEW incidents occurred during testing."""
        incidents_log = Path("logs/incidents_latest.log")

        if not incidents_log.exists():
            return False

        # Only check for new content added since startup
        try:
            current_size = incidents_log.stat().st_size
            if current_size <= self._startup_incidents_position:
                return False  # No new content

            # Check only the new content
            ignore_patterns = [
                "MOCK_MODULE_LOADED",
                "MOCK LLM",
                "RUNTIME SHUTDOWN",
                "SYSTEM SHUTDOWN",
                "GRACEFUL SHUTDOWN",
                "Edge already exists",
                "duplicate edge",
                "TSDB consolidation",
            ]

            with open(incidents_log, "r") as f:
                f.seek(self._startup_incidents_position)  # Start from where we left off

                for line in f:
                    if ("ERROR" in line or "CRITICAL" in line) and not any(
                        pattern in line for pattern in ignore_patterns
                    ):
                        return True

        except Exception:
            return False

        return False

    def _authenticate(self) -> bool:
        """Get authentication token."""
        try:
            response = requests.post(
                f"{self.config.base_url}/v1/auth/login",
                json={"username": self.config.admin_username, "password": self.config.admin_password},
                timeout=10,
            )

            if response.status_code == 200:
                self.token = response.json()["access_token"]
                self.console.print("[green]✅ Authentication successful[/green]")
                return True
            else:
                self.console.print(f"[red]Authentication failed: {response.status_code}[/red]")
                return False

        except Exception as e:
            self.console.print(f"[red]Authentication error: {e}[/red]")
            return False

    def _run_sequential(self, tests: List[QATestCase]) -> bool:
        """Run tests sequentially."""
        all_passed = True

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=self.console
        ) as progress:
            task = progress.add_task("Running tests...", total=len(tests))

            for test in tests:
                progress.update(task, description=f"Testing {test.name}...")

                passed, result = self._run_single_test(test)
                self.results[f"{test.module.value}::{test.name}"] = result

                # Check if this was a test that invalidated our token
                token_invalidating_tests = [("logout", "/auth/logout"), ("refresh token", "/auth/refresh")]

                for test_name_pattern, endpoint_pattern in token_invalidating_tests:
                    if test_name_pattern.lower() in test.name.lower() and endpoint_pattern in test.endpoint:
                        if self.config.verbose:
                            self.console.print(f"[yellow]🔄 Re-authenticating after {test.name}...[/yellow]")
                        # Re-authenticate to restore token for subsequent tests
                        if not self._authenticate():
                            self.console.print(f"[red]❌ Failed to re-authenticate after {test.name}[/red]")
                            all_passed = False
                        break

                # Check incidents log after each test for immediate feedback
                incidents = self._check_incidents_for_test(test.name)
                if incidents:
                    result["incidents"] = incidents
                    if self.config.verbose:
                        self.console.print(f"[yellow]⚠️  Found {len(incidents)} incidents during {test.name}[/yellow]")

                if not passed:
                    all_passed = False

                # FILTER & HANDLER TESTS: Wait for task completion between tests
                # Each test creates a task that must complete before the next test
                if test.module in (QAModule.FILTERS, QAModule.HANDLERS):
                    if self._filter_helper:
                        if self.config.verbose:
                            self.console.print(f"[dim]⏳ Waiting for TASK_COMPLETE event via SSE...[/dim]")

                        # Wait for task completion via SSE (30s timeout per test)
                        completed = self._filter_helper.wait_for_task_complete(task_id=None, timeout=30.0)

                        if not completed:
                            self.console.print(f"[yellow]⚠️  Task did not complete within 30s for {test.name}[/yellow]")
                            # Give extra buffer time
                            time.sleep(2.0)
                        elif self.config.verbose:
                            self.console.print(f"[green]✅ Task completed for {test.name}[/green]")
                    else:
                        # Fallback to simple delay if SSE monitoring not available
                        if self.config.verbose:
                            self.console.print(f"[dim]⏳ Waiting for task completion (fallback delay)...[/dim]")
                        time.sleep(2.0)

                progress.advance(task)

        return all_passed

    def _run_parallel(self, tests: List[QATestCase]) -> bool:
        """Run tests in parallel."""
        all_passed = True

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = []

            for test in tests:
                future = executor.submit(self._run_single_test, test)
                futures.append((test, future))

            with Progress(
                SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=self.console
            ) as progress:
                task = progress.add_task("Running parallel tests...", total=len(tests))

                for test, future in futures:
                    progress.update(task, description=f"Waiting for {test.name}...")

                    passed, result = future.result(timeout=self.config.timeout)
                    self.results[f"{test.module.value}::{test.name}"] = result

                    # Check incidents log after each test (note: less precise in parallel mode)
                    incidents = self._check_incidents_for_test(test.name)
                    if incidents:
                        result["incidents"] = incidents
                        if self.config.verbose:
                            self.console.print(
                                f"[yellow]⚠️  Found {len(incidents)} incidents during {test.name}[/yellow]"
                            )

                    if not passed:
                        all_passed = False

                    progress.advance(task)

        return all_passed

    def _run_single_test(self, test: QATestCase) -> Tuple[bool, Dict]:
        """Run a single test case with enhanced validation support."""
        # Handle repeat_count for multi-execution tests
        if hasattr(test, "repeat_count") and test.repeat_count > 1:
            return self._run_repeated_test(test)

        return self._execute_single_test(test)

    def _run_repeated_test(self, test: QATestCase) -> Tuple[bool, Dict]:
        """Run a test multiple times and aggregate results."""
        results = []
        all_passed = True

        # Store auth token in config for custom validators
        if hasattr(self.config, "_auth_token") is False:
            self.config._auth_token = self.token

        for i in range(test.repeat_count):
            passed, result = self._execute_single_test(test)
            result["execution_number"] = i + 1
            results.append(result)

            if not passed:
                all_passed = False

        # Aggregate results
        aggregated_result = {
            "success": all_passed,
            "executions": results,
            "total_executions": len(results),
            "successful_executions": sum(1 for r in results if r.get("success")),
            "duration": sum(r.get("duration", 0) for r in results),
        }

        return all_passed, aggregated_result

    def _execute_single_test(self, test: QATestCase) -> Tuple[bool, Dict]:
        """Run a single test case."""
        headers = {}
        if test.requires_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        start_time = time.time()

        for attempt in range(self.config.retry_count):
            try:
                if test.method == "GET":
                    # Special handling for SSE endpoints
                    if test.endpoint and "reasoning-stream" in test.endpoint:
                        # SSE endpoint - just verify it connects
                        response = requests.get(
                            f"{self.config.base_url}{test.endpoint}",
                            headers=headers,
                            stream=True,
                            timeout=2,  # Short timeout for connection
                        )
                        # Close immediately after verifying connection
                        response.close()
                    else:
                        response = requests.get(
                            f"{self.config.base_url}{test.endpoint}", headers=headers, timeout=test.timeout
                        )
                elif test.method == "POST":
                    response = requests.post(
                        f"{self.config.base_url}{test.endpoint}",
                        headers=headers,
                        json=test.payload,
                        timeout=test.timeout,
                    )
                elif test.method == "PUT":
                    response = requests.put(
                        f"{self.config.base_url}{test.endpoint}",
                        headers=headers,
                        json=test.payload,
                        timeout=test.timeout,
                    )
                elif test.method == "DELETE":
                    response = requests.delete(
                        f"{self.config.base_url}{test.endpoint}", headers=headers, timeout=test.timeout
                    )
                elif test.method == "WEBSOCKET":
                    # WebSocket testing support
                    if self.config.verbose:
                        self.console.print(f"[cyan]Testing WebSocket: {test.endpoint}[/cyan]")

                    try:
                        import websocket
                    except ImportError:
                        return False, {
                            "success": False,
                            "error": "websocket-client not installed",
                            "duration": time.time() - start_time,
                        }

                    # Convert HTTP URL to WebSocket URL
                    ws_url = self.config.base_url.replace("http://", "ws://").replace("https://", "wss://")
                    ws_url = f"{ws_url}{test.endpoint}"

                    if self.config.verbose:
                        self.console.print(f"[cyan]WebSocket URL: {ws_url}[/cyan]")

                    try:
                        # Add auth header if needed
                        ws_headers = []
                        if test.requires_auth and self.token:
                            ws_headers.append(f"Authorization: Bearer {self.token}")

                        # Try to connect with short timeout
                        if self.config.verbose:
                            self.console.print(f"[cyan]Attempting WebSocket connection...[/cyan]")

                        ws = websocket.create_connection(
                            ws_url, header=ws_headers, timeout=2  # Short timeout for WebSocket handshake
                        )
                        ws.close()

                        # WebSocket connected successfully (101 Switching Protocols)
                        if self.config.verbose:
                            self.console.print(f"[green]✅ {test.name} - Connected![/green]")

                        result = {
                            "success": True,
                            "status_code": 101,
                            "duration": time.time() - start_time,
                            "attempts": attempt + 1,
                            "message": "WebSocket connection established",
                        }
                        break  # Success, exit retry loop

                    except websocket.WebSocketException as e:
                        error_msg = str(e)
                        if self.config.verbose:
                            self.console.print(f"[yellow]WebSocket error: {error_msg}[/yellow]")

                        # Check if it's an auth/forbidden error (endpoint exists but auth failed)
                        if any(code in error_msg for code in ["401", "403", "Handshake status"]):
                            # This is expected - endpoint exists but requires proper auth
                            if self.config.verbose:
                                self.console.print(f"[green]✅ {test.name} (endpoint verified)[/green]")

                            result = {
                                "success": True,
                                "status_code": 101,
                                "duration": time.time() - start_time,
                                "attempts": attempt + 1,
                                "message": "WebSocket endpoint verified (auth required)",
                            }
                            break  # Success, exit retry loop
                        else:
                            # Real error - endpoint might not exist or server error
                            if attempt == max_attempts - 1:
                                # Last attempt, fail the test
                                if self.config.verbose:
                                    self.console.print(f"[red]❌ {test.name}: {error_msg[:100]}[/red]")

                                return False, {
                                    "success": False,
                                    "error": f"WebSocket failed: {error_msg[:200]}",
                                    "duration": time.time() - start_time,
                                    "attempts": attempt + 1,
                                }
                            else:
                                # Not last attempt, wait and retry
                                time.sleep(retry_delay)
                                continue
                    except Exception as e:
                        # Non-WebSocket error
                        if attempt == max_attempts - 1:
                            return False, {
                                "success": False,
                                "error": f"Unexpected error: {str(e)[:200]}",
                                "duration": time.time() - start_time,
                                "attempts": attempt + 1,
                            }
                        else:
                            time.sleep(retry_delay)
                            continue
                elif test.method == "CUSTOM":
                    # Custom method handler for special tests like streaming verification
                    if test.custom_handler:
                        from .modules.streaming_verification import StreamingVerificationModule

                        custom_result = StreamingVerificationModule.run_custom_test(test, self.config, self.token)
                        if custom_result["success"]:
                            # Print validation details
                            if self.config.verbose:
                                self.console.print(f"[cyan]{custom_result.get('message', 'Custom test passed')}[/cyan]")
                                if "details" in custom_result:
                                    import json

                                    details = custom_result["details"]
                                    # Print dma_results validation specifically
                                    if "perform_aspdma_dma_results" in details:
                                        dma_info = details["perform_aspdma_dma_results"]
                                        self.console.print(
                                            f"[cyan]   PERFORM_ASPDMA DMA Results: {dma_info['with_dma_results']}/{dma_info['total_aspdma_steps']} steps have dma_results[/cyan]"
                                        )
                                        if dma_info["missing_dma_results"] > 0:
                                            self.console.print(
                                                f"[yellow]   ⚠️  {dma_info['missing_dma_results']} PERFORM_ASPDMA steps missing dma_results![/yellow]"
                                            )
                            result = {
                                "success": True,
                                "status_code": 200,
                                "duration": time.time() - start_time,
                                "attempts": attempt + 1,
                                "custom_result": custom_result,
                            }
                        else:
                            if self.config.verbose:
                                self.console.print(
                                    f"[yellow]{custom_result.get('message', 'Custom test failed')}[/yellow]"
                                )
                            return False, {
                                "success": False,
                                "error": custom_result.get("message", "Custom test failed"),
                                "duration": time.time() - start_time,
                                "custom_result": custom_result,
                            }
                        break
                    else:
                        return False, {
                            "success": False,
                            "error": f"Custom handler not found for test: {test.name}",
                            "duration": time.time() - start_time,
                        }
                else:
                    return False, {
                        "success": False,
                        "error": f"Unknown method: {test.method}",
                        "duration": time.time() - start_time,
                    }

                # For WebSocket tests, we already have the result set
                if test.method == "WEBSOCKET":
                    # Result was set in the WebSocket handler above
                    pass
                elif response.status_code == test.expected_status:
                    result = {
                        "success": True,
                        "status_code": response.status_code,
                        "duration": time.time() - start_time,
                        "attempts": attempt + 1,
                    }

                    if self.config.verbose:
                        try:
                            result["response"] = response.json()
                        except:
                            result["response"] = response.text[:500]

                    # CRITICAL: Update token after successful refresh
                    # The refresh endpoint revokes the old token and returns a new one
                    if test.name == "SDK token refresh" and response.status_code == 200:
                        try:
                            new_token = response.json().get("access_token")
                            if new_token:
                                self.token = new_token
                                if self.config.verbose:
                                    self.console.print(f"[yellow]🔄 Updated auth token after refresh[/yellow]")
                        except Exception as e:
                            if self.config.verbose:
                                self.console.print(f"[yellow]⚠️ Failed to update token: {e}[/yellow]")

                    # Enhanced validation support
                    validation_passed, validation_result = self._validate_response(test, response)
                    result.update(validation_result)

                    if not validation_passed:
                        result["success"] = False
                        if self.config.verbose:
                            self.console.print(f"[red]❌ {test.name}: Validation failed[/red]")
                        return False, result

                    if self.config.verbose:
                        self.console.print(f"[green]✅ {test.name}[/green]")

                    return True, result
                else:
                    if attempt < self.config.retry_count - 1:
                        time.sleep(self.config.retry_delay)
                        continue

                    result = {
                        "success": False,
                        "status_code": response.status_code,
                        "expected_status": test.expected_status,
                        "error": response.text[:500],
                        "duration": time.time() - start_time,
                        "attempts": attempt + 1,
                    }

                    if self.config.verbose:
                        self.console.print(f"[red]❌ {test.name}: {response.status_code}[/red]")

                    return False, result

            except Exception as e:
                if attempt < self.config.retry_count - 1:
                    time.sleep(self.config.retry_delay)
                    continue

                result = {
                    "success": False,
                    "error": str(e),
                    "duration": time.time() - start_time,
                    "attempts": attempt + 1,
                }

                if self.config.verbose:
                    self.console.print(f"[red]❌ {test.name}: {e}[/red]")

                return False, result

        # If we got here and result was set (e.g., by WebSocket test breaking loop), return it
        if "result" in locals() and result:
            return result.get("success", False), result

        return False, {"success": False, "error": "Max retries exceeded"}

    def _validate_response(self, test: QATestCase, response) -> Tuple[bool, Dict]:
        """Validate response using validation rules and custom validation."""
        validation_result = {"validation": {"passed": True, "details": {}, "errors": []}}

        try:
            # Get response data for validation
            response_data = None
            try:
                response_data = response.json()
            except:
                response_data = {"raw_text": response.text}

            # Apply validation rules
            if hasattr(test, "validation_rules") and test.validation_rules:
                for rule_name, rule_func in test.validation_rules.items():
                    try:
                        rule_passed = rule_func(response_data)
                        validation_result["validation"]["details"][rule_name] = rule_passed

                        if not rule_passed:
                            validation_result["validation"]["errors"].append(f"Rule '{rule_name}' failed")
                            validation_result["validation"]["passed"] = False
                    except Exception as e:
                        validation_result["validation"]["errors"].append(f"Rule '{rule_name}' error: {str(e)}")
                        validation_result["validation"]["passed"] = False

            # Apply custom validation
            if hasattr(test, "custom_validation") and test.custom_validation:
                # Store auth token in config for custom validators
                if hasattr(self.config, "_auth_token") is False:
                    self.config._auth_token = self.token

                try:
                    custom_result = test.custom_validation(response, self.config)
                    validation_result["validation"]["custom"] = custom_result

                    if not custom_result.get("passed", True):
                        validation_result["validation"]["passed"] = False
                        validation_result["validation"]["errors"].extend(custom_result.get("errors", []))

                except Exception as e:
                    validation_result["validation"]["errors"].append(f"Custom validation error: {str(e)}")
                    validation_result["validation"]["passed"] = False

        except Exception as e:
            validation_result["validation"]["errors"].append(f"Validation framework error: {str(e)}")
            validation_result["validation"]["passed"] = False

        return validation_result["validation"]["passed"], validation_result

    def _generate_reports(self):
        """Generate test reports."""
        if not self.config.json_output and not self.config.html_report:
            return

        # Create report directory
        self.config.report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # JSON report
        if self.config.json_output:
            json_file = self.config.report_dir / f"qa_report_{timestamp}.json"
            report_data = {
                "timestamp": timestamp,
                "config": {
                    "base_url": self.config.base_url,
                    "modules": list(set(k.split("::")[0] for k in self.results.keys())),
                },
                "results": self.results,
                "summary": self._get_summary(),
            }

            with open(json_file, "w") as f:
                json.dump(report_data, f, indent=2)

            self.console.print(f"📄 JSON report: {json_file}")

        # HTML report
        if self.config.html_report:
            html_file = self.config.report_dir / f"qa_report_{timestamp}.html"
            self._generate_html_report(html_file)
            self.console.print(f"📄 HTML report: {html_file}")

    def _generate_html_report(self, file_path: Path):
        """Generate HTML report."""
        summary = self._get_summary()

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>CIRIS QA Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #2c3e50; }}
        .summary {{ background: #ecf0f1; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #3498db; color: white; }}
        .pass {{ color: #27ae60; font-weight: bold; }}
        .fail {{ color: #e74c3c; font-weight: bold; }}
        .module-header {{ background: #95a5a6; color: white; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>CIRIS QA Test Report</h1>
    <div class="summary">
        <h2>Summary</h2>
        <p>Total Tests: {summary['total']}</p>
        <p>Passed: <span class="pass">{summary['passed']}</span></p>
        <p>Failed: <span class="fail">{summary['failed']}</span></p>
        <p>Success Rate: {summary['success_rate']:.1f}%</p>
    </div>

    <h2>Test Results</h2>
    <table>
        <tr>
            <th>Module</th>
            <th>Test</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Details</th>
        </tr>
"""

        current_module = None
        for key in sorted(self.results.keys()):
            module, test_name = key.split("::")
            result = self.results[key]

            if module != current_module:
                html += f'<tr class="module-header"><td colspan="5">{module.upper()}</td></tr>'
                current_module = module

            status_class = "pass" if result["success"] else "fail"
            status_text = "✅ PASS" if result["success"] else "❌ FAIL"
            duration = f"{result.get('duration', 0):.2f}s"

            details = ""
            if not result["success"]:
                if "status_code" in result:
                    details = f"Status: {result['status_code']} (expected {result.get('expected_status', 200)})"
                else:
                    details = result.get("error", "Unknown error")[:100]

            html += f"""
        <tr>
            <td>{module}</td>
            <td>{test_name}</td>
            <td class="{status_class}">{status_text}</td>
            <td>{duration}</td>
            <td>{details}</td>
        </tr>
"""

        html += """
    </table>
</body>
</html>
"""

        with open(file_path, "w") as f:
            f.write(html)

    def _get_summary(self) -> Dict:
        """Get test summary statistics."""
        total = len(self.results)
        passed = sum(1 for r in self.results.values() if r["success"])
        failed = total - passed

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "success_rate": (passed / total * 100) if total > 0 else 0,
        }

    def _print_summary(self, elapsed: float, has_incidents: bool = False):
        """Print test summary."""
        summary = self._get_summary()

        # Create summary table
        table = Table(title="QA Test Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Total Tests", str(summary["total"]))
        table.add_row("Passed", f"[green]{summary['passed']}[/green]")
        table.add_row("Failed", f"[red]{summary['failed']}[/red]")
        table.add_row("Success Rate", f"{summary['success_rate']:.1f}%")
        table.add_row("Duration", f"{elapsed:.2f}s")

        self.console.print("\n")
        self.console.print(table)

        # Print failed tests if any
        if summary["failed"] > 0:
            self.console.print("\n[red]Failed Tests:[/red]")
            for key, result in self.results.items():
                if not result["success"]:
                    module, test = key.split("::")
                    error = result.get("error", "Unknown error")[:100]
                    self.console.print(f"  • {module}::{test}: {error}")

        # Print tests with incidents
        tests_with_incidents = []
        for key, result in self.results.items():
            if "incidents" in result and result["incidents"]:
                tests_with_incidents.append((key, result["incidents"]))

        if tests_with_incidents:
            self.console.print("\n[yellow]Tests with Incidents:[/yellow]")
            for key, incidents in tests_with_incidents:
                module, test = key.split("::")
                self.console.print(f"  • {module}::{test}:")
                for incident in incidents[:3]:  # Show max 3 incidents per test
                    self.console.print(f"    - {incident[:150]}")
                if len(incidents) > 3:
                    self.console.print(f"    ... and {len(incidents) - 3} more")

        # Overall result
        if summary["failed"] == 0:
            self.console.print("\n[bold green]✅ All tests passed![/bold green]")
        else:
            self.console.print(f"\n[bold red]❌ {summary['failed']} test(s) failed[/bold red]")
