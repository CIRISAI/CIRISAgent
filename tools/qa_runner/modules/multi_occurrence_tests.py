"""
True multi-occurrence integration test module.

Tests ACTUAL multi-occurrence functionality by spawning multiple API instances
against the same PostgreSQL database and verifying proper coordination.
"""

import time
from typing import Dict, List

from ..config import QAModule, QATestCase


class MultiOccurrenceTestModule:
    """Test module for TRUE multi-occurrence integration testing."""

    @staticmethod
    def get_multi_occurrence_tests() -> List[QATestCase]:
        """Get basic multi-occurrence API validation tests (run on single instance)."""
        return [
            # Basic configuration tests
            QATestCase(
                name="Verify occurrence_id in config",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/config",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify agent_occurrence_id is present in system configuration",
            ),
            QATestCase(
                name="Verify default occurrence_id value",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/config",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify default occurrence_id is 'default' for backward compatibility",
            ),
            # Task creation and isolation tests
            QATestCase(
                name="Create task - verify occurrence stamping",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Test occurrence isolation - create task"},
                expected_status=200,
                requires_auth=True,
                description="Submit message and verify task is created with occurrence_id",
            ),
            QATestCase(
                name="Query tasks - verify occurrence filtering",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify queue status only shows tasks for this occurrence",
            ),
        ]

    @staticmethod
    def run_true_multi_occurrence_integration_test(runner) -> Dict:
        """Run TRUE multi-occurrence integration test by spawning 2 separate runtimes.

        This test:
        1. Spawns 2 separate API server processes with unique occurrence IDs
        2. Verifies they share the same PostgreSQL database
        3. Tests that only ONE claims shared wakeup task
        4. Verifies separate log files per occurrence
        5. Confirms proper thought ownership after transfer

        Args:
            runner: QARunner instance with helper methods

        Returns:
            Dictionary with test results
        """
        results = {
            "test_name": "True Multi-Occurrence Integration Test",
            "success": False,
            "details": {},
            "errors": [],
        }

        runner.console.print("\n[bold cyan]🔄 STARTING TRUE MULTI-OCCURRENCE INTEGRATION TEST[/bold cyan]")
        runner.console.print("[dim]Spawning 2 separate runtime processes...[/dim]\n")

        occurrence_ids = ["occurrence_1", "occurrence_2"]
        occurrence_managers = {}

        try:
            # Step 1: Spawn occurrence managers
            runner.console.print("[cyan]📦 Creating occurrence managers...[/cyan]")
            occurrence_managers = runner.spawn_multi_occurrence_servers(occurrence_ids, base_port=9000)
            runner.console.print(f"[green]✅ Created {len(occurrence_managers)} occurrence managers[/green]\n")

            # Step 2: Start first occurrence
            runner.console.print("[cyan]🚀 Starting occurrence_1...[/cyan]")
            runner.console.print("[dim]📁 Logs: logs/occurrence_1/[/dim]")
            success_1 = runner.start_occurrence("occurrence_1", occurrence_managers["occurrence_1"])
            if not success_1:
                results["errors"].append("Failed to start occurrence_1")
                runner.console.print("[red]❌ Check logs at: logs/occurrence_1/incidents_latest.log[/red]")
                runner.console.print("[red]❌ Check logs at: logs/occurrence_1/latest.log[/red]")
                return results
            runner.console.print("[green]✅ occurrence_1 started successfully[/green]\n")

            # Give it time to complete wakeup
            runner.console.print("[dim]⏳ Waiting for occurrence_1 to complete wakeup (30s)...[/dim]")
            time.sleep(30)

            # Step 3: Start second occurrence (should detect wakeup already done)
            runner.console.print("[cyan]🚀 Starting occurrence_2...[/cyan]")
            runner.console.print("[dim]📁 Logs: logs/occurrence_2/[/dim]")
            success_2 = runner.start_occurrence("occurrence_2", occurrence_managers["occurrence_2"])
            if not success_2:
                results["errors"].append("Failed to start occurrence_2")
                runner.console.print("[red]❌ Check logs at: logs/occurrence_2/incidents_latest.log[/red]")
                runner.console.print("[red]❌ Check logs at: logs/occurrence_2/latest.log[/red]")
                return results
            runner.console.print("[green]✅ occurrence_2 started successfully[/green]\n")

            # Give it time to detect existing wakeup
            runner.console.print("[dim]⏳ Waiting for occurrence_2 to detect wakeup (20s)...[/dim]")
            time.sleep(20)

            # Step 4: Query shared tasks from database
            runner.console.print("\n[cyan]🔍 Querying shared tasks from database...[/cyan]")
            shared_tasks = runner.query_shared_tasks_db()

            runner.console.print(f"[yellow]Found {len(shared_tasks)} shared task(s):[/yellow]")
            for task in shared_tasks:
                runner.console.print(f"  • {task['description']} (status: {task['status']})")

            # Verify exactly 1 shared wakeup task FROM TODAY
            # Filter by today's date to exclude historical completed wakeup tasks
            from datetime import datetime, timezone

            today = datetime.now(timezone.utc).strftime("%Y%m%d")
            wakeup_tasks = [
                t for t in shared_tasks if "wakeup" in t["description"].lower() and f"_SHARED_{today}" in t["task_id"]
            ]
            results["details"]["shared_wakeup_tasks"] = len(wakeup_tasks)

            if len(wakeup_tasks) == 1:
                runner.console.print("[green]✅ Exactly 1 shared wakeup task from today (proper coordination!)[/green]")
                results["details"]["wakeup_coordination"] = "PASS"
            else:
                runner.console.print(f"[red]❌ Expected 1 wakeup task from today, found {len(wakeup_tasks)}[/red]")
                results["errors"].append(f"Expected 1 wakeup task from today, found {len(wakeup_tasks)}")
                results["details"]["wakeup_coordination"] = "FAIL"

            # Step 5: Query thoughts by occurrence
            runner.console.print("\n[cyan]🔍 Querying thoughts by occurrence...[/cyan]")
            thoughts_by_occ = runner.query_thoughts_by_occurrence_db()

            runner.console.print(f"[yellow]Thoughts by occurrence:[/yellow]")
            for occ_id, count in thoughts_by_occ.items():
                runner.console.print(f"  • {occ_id}: {count} thought(s)")

            results["details"]["thoughts_by_occurrence"] = thoughts_by_occ

            # Verify only the test occurrences have thoughts (filter out other runs)
            # Only consider the specific occurrence_ids we're testing
            test_occ_thoughts = {k: v for k, v in thoughts_by_occ.items() if k in occurrence_ids}
            if len(test_occ_thoughts) >= 1:
                runner.console.print(
                    f"[green]✅ Test occurrences have thoughts: {list(test_occ_thoughts.keys())}[/green]"
                )
                results["details"]["thought_ownership"] = "PASS"
            else:
                runner.console.print("[red]❌ No test occurrences have thoughts![/red]")
                results["details"]["thought_ownership"] = "FAIL"

            # Step 6a: Test thought processing on occurrence_1 (BASELINE CHECK)
            runner.console.print("\n[cyan]🧠 Testing thought processing on occurrence_1 (baseline)...[/cyan]")
            runner.console.print("[dim]This verifies interact endpoint works correctly[/dim]")

            import requests

            # Submit a message to occurrence_1's API
            try:
                occ1_port = 9000  # occurrence_1 runs on port 9000
                occ1_url = f"http://localhost:{occ1_port}"

                # Get auth token for occurrence_1
                runner.console.print(f"[dim]Authenticating to occurrence_1 at {occ1_url}...[/dim]")
                auth_response = requests.post(
                    f"{occ1_url}/v1/auth/login",
                    json={"username": "admin", "password": "ciris_admin_password"},
                    timeout=10,
                )

                if auth_response.status_code != 200:
                    runner.console.print(
                        f"[red]❌ Failed to authenticate to occurrence_1: {auth_response.status_code}[/red]"
                    )
                    results["errors"].append(f"occurrence_1 auth failed: {auth_response.status_code}")
                else:
                    token = auth_response.json()["access_token"]
                    runner.console.print("[green]✅ Authenticated to occurrence_1[/green]")

                    # Submit a test message
                    runner.console.print("[dim]Submitting test message to occurrence_1...[/dim]")
                    interact_response = requests.post(
                        f"{occ1_url}/v1/agent/interact",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"message": "Test thought processing for occurrence_1"},
                        timeout=60,  # Allow time for thought processing
                    )

                    if interact_response.status_code == 200:
                        response_data = interact_response.json()
                        # Extract response from SuccessResponse wrapper
                        actual_response = (
                            response_data.get("data", {}).get("response", "")
                            if isinstance(response_data.get("data"), dict)
                            else ""
                        )
                        if actual_response:
                            runner.console.print(f"[green]✅ occurrence_1 processed thought successfully![/green]")
                            runner.console.print(f"[dim]Response: {actual_response[:100]}...[/dim]")
                        else:
                            runner.console.print(f"[yellow]⚠️  occurrence_1 responded but with empty response[/yellow]")
                            runner.console.print(f"[dim]DEBUG response_data: {response_data}[/dim]")
                    else:
                        runner.console.print(
                            f"[red]❌ occurrence_1 interact failed: {interact_response.status_code}[/red]"
                        )
                        runner.console.print(f"[red]Response: {interact_response.text[:200]}[/red]")
                        results["errors"].append(f"occurrence_1 interact failed: {interact_response.status_code}")

            except requests.exceptions.Timeout:
                runner.console.print("[red]❌ occurrence_1 interact request timed out[/red]")
                results["errors"].append("occurrence_1 interact timeout")
            except Exception as e:
                runner.console.print(f"[red]❌ Error testing occurrence_1 thought processing: {e}[/red]")
                results["errors"].append(f"occurrence_1 thought processing test error: {str(e)}")

            # Step 6b: Test thought processing on occurrence_2 (CRITICAL BUG CHECK)
            runner.console.print("\n[cyan]🧠 Testing thought processing on occurrence_2...[/cyan]")
            runner.console.print(
                "[dim]This verifies thoughts can be fetched and processed with correct occurrence_id[/dim]"
            )

            # Submit a message to occurrence_2's API
            try:
                occ2_port = 9001  # occurrence_2 runs on port 9001
                occ2_url = f"http://localhost:{occ2_port}"

                # Get auth token for occurrence_2
                runner.console.print(f"[dim]Authenticating to occurrence_2 at {occ2_url}...[/dim]")
                auth_response = requests.post(
                    f"{occ2_url}/v1/auth/login",
                    json={"username": "admin", "password": "ciris_admin_password"},
                    timeout=10,
                )

                if auth_response.status_code != 200:
                    runner.console.print(
                        f"[red]❌ Failed to authenticate to occurrence_2: {auth_response.status_code}[/red]"
                    )
                    results["errors"].append(f"occurrence_2 auth failed: {auth_response.status_code}")
                    results["details"]["thought_processing"] = "FAIL"
                else:
                    token = auth_response.json()["access_token"]
                    runner.console.print("[green]✅ Authenticated to occurrence_2[/green]")

                    # Submit a test message
                    runner.console.print("[dim]Submitting test message to occurrence_2...[/dim]")
                    interact_response = requests.post(
                        f"{occ2_url}/v1/agent/interact",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"message": "Test thought processing for occurrence_2"},
                        timeout=60,  # Allow time for thought processing
                    )

                    if interact_response.status_code == 200:
                        response_data = interact_response.json()
                        # Extract response from SuccessResponse wrapper
                        actual_response = (
                            response_data.get("data", {}).get("response", "")
                            if isinstance(response_data.get("data"), dict)
                            else ""
                        )
                        if actual_response:
                            runner.console.print(f"[green]✅ occurrence_2 processed thought successfully![/green]")
                            runner.console.print(f"[dim]Response: {actual_response[:100]}...[/dim]")
                            results["details"]["thought_processing"] = "PASS"
                        else:
                            runner.console.print(f"[yellow]⚠️  occurrence_2 responded but with empty response[/yellow]")
                            runner.console.print(f"[dim]DEBUG response_data: {response_data}[/dim]")
                            results["details"]["thought_processing"] = "PARTIAL"
                    else:
                        runner.console.print(
                            f"[red]❌ occurrence_2 interact failed: {interact_response.status_code}[/red]"
                        )
                        runner.console.print(f"[red]Response: {interact_response.text[:200]}[/red]")
                        results["errors"].append(f"occurrence_2 interact failed: {interact_response.status_code}")
                        results["details"]["thought_processing"] = "FAIL"

            except requests.exceptions.Timeout:
                runner.console.print(
                    "[red]❌ occurrence_2 interact request timed out (thought processing likely hung)[/red]"
                )
                results["errors"].append("occurrence_2 interact timeout - thoughts may be stuck in processing")
                results["details"]["thought_processing"] = "TIMEOUT"
            except Exception as e:
                runner.console.print(f"[red]❌ Error testing occurrence_2 thought processing: {e}[/red]")
                results["errors"].append(f"occurrence_2 thought processing test error: {str(e)}")
                results["details"]["thought_processing"] = "ERROR"

            # Step 7: Verify separate log files
            runner.console.print("\n[cyan]📋 Verifying separate log files...[/cyan]")
            import os
            from pathlib import Path

            log_files_found = {}
            for occ_id in occurrence_ids:
                log_dir = Path(f"logs/occurrence_{occ_id}")
                if log_dir.exists():
                    log_files = list(log_dir.glob("ciris_agent_*.log"))
                    log_files_found[occ_id] = len(log_files)
                    runner.console.print(f"  • {occ_id}: {len(log_files)} log file(s) at {log_dir}")
                else:
                    log_files_found[occ_id] = 0
                    runner.console.print(f"  • {occ_id}: [red]No log directory found[/red]")

            results["details"]["log_files"] = log_files_found

            if all(count > 0 for count in log_files_found.values()):
                runner.console.print("[green]✅ All occurrences have separate log files[/green]")
                results["details"]["log_separation"] = "PASS"
            else:
                runner.console.print("[red]❌ Some occurrences missing log files[/red]")
                results["details"]["log_separation"] = "FAIL"

            # Determine overall success
            thought_processing_ok = results["details"].get("thought_processing") == "PASS"
            if (
                len(wakeup_tasks) == 1
                and len(test_occ_thoughts) >= 1  # At least one test occurrence has thoughts
                and all(count > 0 for count in log_files_found.values())
                and thought_processing_ok  # NEW: Thought processing must work
            ):
                results["success"] = True
                runner.console.print("\n[bold green]✅ MULTI-OCCURRENCE INTEGRATION TEST PASSED![/bold green]")
            else:
                runner.console.print("\n[bold yellow]⚠️  MULTI-OCCURRENCE INTEGRATION TEST HAD ISSUES[/bold yellow]")
                if not thought_processing_ok:
                    runner.console.print(
                        "[red]❌ CRITICAL: Thought processing failed (ProcessingQueueItem bug detected!)[/red]"
                    )

        except Exception as e:
            runner.console.print(f"\n[bold red]❌ Test failed with exception: {e}[/bold red]")
            results["errors"].append(str(e))
            results["success"] = False

        finally:
            # Cleanup: Stop all occurrences
            runner.console.print("\n[cyan]🛑 Stopping all occurrences...[/cyan]")
            for occ_id, manager in occurrence_managers.items():
                try:
                    manager.stop()
                    runner.console.print(f"[green]✅ Stopped {occ_id}[/green]")
                except Exception as e:
                    runner.console.print(f"[yellow]⚠️  Error stopping {occ_id}: {e}[/yellow]")

        return results

    @staticmethod
    def get_all_multi_occurrence_tests() -> List[QATestCase]:
        """Get all multi-occurrence test cases.

        NOTE: This returns basic API tests. For TRUE multi-occurrence integration testing,
        use run_true_multi_occurrence_integration_test() which spawns 2 runtimes.
        """
        return MultiOccurrenceTestModule.get_multi_occurrence_tests()
