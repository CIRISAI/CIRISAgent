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

    def run(self, modules: List[QAModule]) -> bool:
        """Run QA tests for specified modules."""
        start_time = time.time()

        self.console.print(
            Panel.fit(
                "[bold cyan]CIRIS QA Test Runner[/bold cyan]\n" f"Modules: {', '.join(m.value for m in modules)}",
                title="🧪 Starting QA Tests",
            )
        )

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

        # Generate reports
        self._generate_reports()

        # Stop server if we started it
        if self.config.auto_start_server:
            self.server_manager.stop()

        # Print summary
        elapsed = time.time() - start_time
        self._print_summary(elapsed)

        return success

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

                if not passed:
                    all_passed = False

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

                    if not passed:
                        all_passed = False

                    progress.advance(task)

        return all_passed

    def _run_single_test(self, test: QATestCase) -> Tuple[bool, Dict]:
        """Run a single test case."""
        headers = {}
        if test.requires_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        start_time = time.time()

        for attempt in range(self.config.retry_count):
            try:
                if test.method == "GET":
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
                else:
                    return False, {
                        "success": False,
                        "error": f"Unknown method: {test.method}",
                        "duration": time.time() - start_time,
                    }

                if response.status_code == test.expected_status:
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

        return False, {"success": False, "error": "Max retries exceeded"}

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

    def _print_summary(self, elapsed: float):
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

        # Overall result
        if summary["failed"] == 0:
            self.console.print("\n[bold green]✅ All tests passed![/bold green]")
        else:
            self.console.print(f"\n[bold red]❌ {summary['failed']} test(s) failed[/bold red]")
