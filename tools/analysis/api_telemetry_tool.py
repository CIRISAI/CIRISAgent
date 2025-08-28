#!/usr/bin/env python3
"""
API Telemetry Testing Tool

Tests all telemetry endpoints with proper authentication and formatting.
"""

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

console = Console()


class APITelemetryTester:
    """Test telemetry endpoints."""

    def __init__(
        self, base_url: str = "http://localhost:8000", username: str = "admin", password: str = "ciris_admin_password"
    ):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.token: Optional[str] = None
        self.headers: Dict[str, str] = {}

    def authenticate(self) -> bool:
        """Get auth token."""
        try:
            response = requests.post(
                f"{self.base_url}/v1/auth/login", json={"username": self.username, "password": self.password}, timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.headers = {"Authorization": f"Bearer {self.token}"}
                console.print(f"[green]✓[/green] Authenticated as {self.username}")
                return True
            else:
                console.print(f"[red]✗[/red] Authentication failed: {response.status_code}")
                return False
        except Exception as e:
            console.print(f"[red]✗[/red] Authentication error: {e}")
            return False

    def test_unified(self) -> Dict[str, Any]:
        """Test unified telemetry endpoint."""
        try:
            response = requests.get(f"{self.base_url}/v1/telemetry/unified", headers=self.headers, timeout=5)
            if response.status_code == 200:
                json_data = response.json()
                # Handle both possible response formats
                if "data" in json_data:
                    data = json_data["data"]
                else:
                    data = json_data

                console.print(f"\n[bold cyan]Unified Telemetry:[/bold cyan]")
                console.print(f"  Services: {data['services_online']}/{data['services_total']} healthy")
                console.print(f"  System Healthy: {data.get('system_healthy', 'N/A')}")
                console.print(f"  Overall Uptime: {data.get('overall_uptime_seconds', 0):.1f}s")
                console.print(f"  Total Requests: {data.get('total_requests', 0)}")
                console.print(f"  Error Rate: {data.get('overall_error_rate', 0):.2%}")

                # Show unhealthy services
                unhealthy = [name for name, info in data["services"].items() if not info["healthy"]]
                if unhealthy:
                    console.print(f"  [yellow]Unhealthy services:[/yellow] {', '.join(unhealthy)}")

                return data
            else:
                console.print(f"[red]✗[/red] Unified telemetry failed: {response.status_code}")
                return {}
        except Exception as e:
            console.print(f"[red]✗[/red] Unified telemetry error: {e}")
            return {}

    def test_metrics(self) -> Dict[str, Any]:
        """Test metrics endpoint."""
        try:
            response = requests.get(f"{self.base_url}/v1/telemetry/metrics", headers=self.headers, timeout=5)
            if response.status_code == 200:
                data = response.json()["data"]
                console.print(f"\n[bold cyan]System Metrics:[/bold cyan]")

                system = data.get("system", {})
                console.print(f"  CPU: {system.get('cpu_percent', 0):.1f}%")
                console.print(
                    f"  Memory: {system.get('memory_used_mb', 0):.1f}/{system.get('memory_total_mb', 0):.1f} MB"
                )
                console.print(f"  Disk: {system.get('disk_used_gb', 0):.1f}/{system.get('disk_total_gb', 0):.1f} GB")

                services = data.get("services", {})
                console.print(f"  Total Services: {len(services)}")

                return data
            else:
                console.print(f"[red]✗[/red] Metrics failed: {response.status_code}")
                return {}
        except Exception as e:
            console.print(f"[red]✗[/red] Metrics error: {e}")
            return {}

    def test_traces(self) -> Dict[str, Any]:
        """Test traces endpoint."""
        try:
            response = requests.get(f"{self.base_url}/v1/telemetry/traces", headers=self.headers, timeout=5)
            if response.status_code == 200:
                data = response.json()["data"]
                console.print(f"\n[bold cyan]Reasoning Traces:[/bold cyan]")
                console.print(f"  Total traces: {data['total']}")
                console.print(f"  Has more: {data['has_more']}")

                if data["traces"]:
                    for trace in data["traces"][:3]:  # Show first 3
                        console.print(
                            f"  - {trace['trace_id']}: {trace['thought_count']} thoughts, {trace['duration_ms']:.0f}ms"
                        )

                return data
            else:
                console.print(f"[red]✗[/red] Traces failed: {response.status_code}")
                if response.text:
                    console.print(f"  Response: {response.text[:200]}")
                return {}
        except Exception as e:
            console.print(f"[red]✗[/red] Traces error: {e}")
            return {}

    def test_logs(self) -> Dict[str, Any]:
        """Test logs endpoint."""
        try:
            response = requests.get(f"{self.base_url}/v1/telemetry/logs", headers=self.headers, timeout=5)
            if response.status_code == 200:
                data = response.json()["data"]
                console.print(f"\n[bold cyan]System Logs:[/bold cyan]")
                console.print(f"  Total entries: {data.get('total', 0)}")
                console.print(f"  Has more: {data.get('has_more', False)}")

                if data.get("logs"):  # May be 'logs' instead of 'entries'
                    for entry in data["logs"][:3]:  # Show first 3
                        console.print(f"  [{entry.get('level', 'INFO')}] {entry.get('message', '')[:80]}...")
                elif data.get("entries"):
                    for entry in data["entries"][:3]:  # Show first 3
                        console.print(f"  [{entry.get('level', 'INFO')}] {entry.get('message', '')[:80]}...")

                return data
            else:
                console.print(f"[red]✗[/red] Logs failed: {response.status_code}")
                return {}
        except Exception as e:
            console.print(f"[red]✗[/red] Logs error: {e}")
            return {}

    def test_prometheus(self) -> str:
        """Test Prometheus metrics format."""
        try:
            response = requests.get(
                f"{self.base_url}/v1/telemetry/unified?format=prometheus", headers=self.headers, timeout=5
            )
            if response.status_code == 200:
                metrics = response.text
                console.print(f"\n[bold cyan]Prometheus Metrics:[/bold cyan]")

                # Count metric types
                lines = metrics.split("\n")
                metric_count = len([l for l in lines if l and not l.startswith("#")])
                help_count = len([l for l in lines if l.startswith("# HELP")])
                type_count = len([l for l in lines if l.startswith("# TYPE")])

                console.print(f"  Total metrics: {metric_count}")
                console.print(f"  Documented metrics: {help_count}")
                console.print(f"  Typed metrics: {type_count}")

                # Show sample metrics
                sample_metrics = [l for l in lines if "ciris_" in l and not l.startswith("#")][:3]
                if sample_metrics:
                    console.print("  Sample metrics:")
                    for metric in sample_metrics:
                        console.print(f"    {metric[:80]}...")

                return metrics
            else:
                console.print(f"[red]✗[/red] Prometheus metrics failed: {response.status_code}")
                return ""
        except Exception as e:
            console.print(f"[red]✗[/red] Prometheus metrics error: {e}")
            return ""

    def test_service_health(self) -> Dict[str, Any]:
        """Test individual service health."""
        try:
            # First get list of services
            unified = self.test_unified()
            if not unified:
                return {}

            console.print(f"\n[bold cyan]Service Health Details:[/bold cyan]")

            # Create table for services
            table = Table(title="Service Status")
            table.add_column("Service", style="cyan")
            table.add_column("Healthy", style="green")
            table.add_column("Uptime", style="yellow")
            table.add_column("Errors", style="red")

            for name, info in unified.get("services", {}).items():
                health_icon = "✓" if info["healthy"] else "✗"
                health_color = "green" if info["healthy"] else "red"
                uptime = f"{info.get('uptime_seconds', 0):.1f}s"
                errors = str(info.get("error_count", 0))

                table.add_row(name, f"[{health_color}]{health_icon}[/{health_color}]", uptime, errors)

            console.print(table)
            return unified.get("services", {})

        except Exception as e:
            console.print(f"[red]✗[/red] Service health error: {e}")
            return {}

    def run_all_tests(self):
        """Run all telemetry tests."""
        console.print("\n[bold magenta]API Telemetry Test Suite[/bold magenta]")
        console.print("=" * 50)

        # Authenticate first
        if not self.authenticate():
            console.print("[red]Cannot proceed without authentication[/red]")
            return

        # Run tests
        self.test_unified()
        self.test_metrics()
        self.test_traces()
        self.test_logs()
        self.test_prometheus()
        self.test_service_health()

        console.print("\n" + "=" * 50)
        console.print("[green]✓[/green] All telemetry tests completed")

    def monitor(self, interval: int = 5):
        """Monitor telemetry in real-time."""
        console.print(
            f"\n[bold magenta]Monitoring telemetry (refresh every {interval}s, Ctrl+C to stop)[/bold magenta]"
        )

        if not self.authenticate():
            return

        try:
            while True:
                console.clear()
                console.print(
                    f"[bold]CIRIS Telemetry Monitor[/bold] - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
                console.print("=" * 60)

                # Get unified telemetry
                response = requests.get(f"{self.base_url}/v1/telemetry/unified", headers=self.headers, timeout=5)

                if response.status_code == 200:
                    json_data = response.json()
                    # Handle both possible response formats
                    if "data" in json_data:
                        data = json_data["data"]
                    else:
                        data = json_data

                    # System stats
                    console.print(f"\n[bold cyan]System:[/bold cyan]")
                    console.print(f"  System Healthy: {data.get('system_healthy', 'N/A')}")
                    console.print(f"  Overall Uptime: {data.get('overall_uptime_seconds', 0):.1f}s")
                    console.print(f"  Services: {data['services_online']}/{data['services_total']} healthy")
                    console.print(f"  Total Requests: {data.get('total_requests', 0)}")
                    console.print(f"  Error Rate: {data.get('overall_error_rate', 0):.2%}")

                    # Service status
                    console.print(f"\n[bold cyan]Services:[/bold cyan]")
                    for name, info in sorted(data["services"].items()):
                        status = "[green]✓[/green]" if info["healthy"] else "[red]✗[/red]"
                        console.print(f"  {status} {name}: {info.get('uptime_seconds', 0):.1f}s")

                time.sleep(interval)

        except KeyboardInterrupt:
            console.print("\n[yellow]Monitoring stopped[/yellow]")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Test CIRIS API telemetry endpoints")
    parser.add_argument("--host", default="localhost", help="API host")
    parser.add_argument("--port", default=8000, type=int, help="API port")
    parser.add_argument("--username", default="admin", help="Auth username")
    parser.add_argument("--password", default="ciris_admin_password", help="Auth password")
    parser.add_argument("--monitor", action="store_true", help="Monitor mode")
    parser.add_argument("--interval", default=5, type=int, help="Monitor refresh interval")

    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    tester = APITelemetryTester(base_url, args.username, args.password)

    if args.monitor:
        tester.monitor(args.interval)
    else:
        tester.run_all_tests()


if __name__ == "__main__":
    main()
