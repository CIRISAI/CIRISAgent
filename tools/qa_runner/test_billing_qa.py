#!/usr/bin/env python3
"""
Quick test script for billing QA module.

Usage:
    python tools/qa_runner/test_billing_qa.py

This will:
1. Connect to local API (http://localhost:8000)
2. Login with admin credentials
3. Run all billing tests
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from rich.console import Console

from ciris_sdk.client import CIRISClient
from tools.qa_runner.modules.billing_tests import BillingTests


async def main():
    """Run billing tests against local API."""
    console = Console()

    console.print("[bold cyan]CIRIS Billing QA Tests[/bold cyan]\n")

    # Connect to local API
    async with CIRISClient(base_url="http://localhost:8000") as client:
        try:
            # Login
            await client.login("admin", "ciris_admin_password")
            console.print("[green]✅ Authenticated with local API[/green]\n")

            # Run billing tests
            billing_tests = BillingTests(client, console)
            results = await billing_tests.run()

            # Check if all passed
            all_passed = all(r["status"] == "✅ PASS" for r in results)

            if all_passed:
                console.print("\n[bold green]✅ All billing tests passed![/bold green]")
            else:
                console.print(
                    "\n[bold yellow]⚠️  Some tests failed (may be expected based on configuration)[/bold yellow]"
                )

            return all_passed

        except Exception as e:
            console.print(f"\n[red]❌ Error running tests: {e}[/red]")
            import traceback

            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
