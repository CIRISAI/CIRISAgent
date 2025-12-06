"""
Cognitive State API test module.

Tests the /v1/system/state/transition endpoint and cognitive state processors
(DREAM, PLAY, SOLITUDE state transitions).
"""

import asyncio
import time
from typing import Any, Dict, List

from rich.console import Console

from ..config import QAModule, QATestCase


class CognitiveStateAPITests:
    """Test module for cognitive state transition API endpoint."""

    def __init__(self, client: Any, console: Console):
        """Initialize test module.

        Args:
            client: CIRISClient instance for making API requests
            console: Rich console for output
        """
        self.client = client
        self.console = console
        self.results: List[Dict] = []

    async def run(self) -> List[Dict]:
        """Run all cognitive state API tests."""
        self.console.print("\n[bold cyan]Running Cognitive State API Tests[/bold cyan]")
        self.console.print("=" * 60)

        # Test API endpoint validation
        await self._test_invalid_target_state()
        await self._test_missing_target_state()

        # Test valid state transitions (from WORK)
        await self._test_get_current_state()
        await self._test_transition_to_dream()
        await self._test_transition_back_to_work()
        await self._test_transition_to_play()
        await self._test_transition_back_to_work()
        await self._test_transition_to_solitude()
        await self._test_transition_back_to_work()

        # Test transition with custom reason
        await self._test_transition_with_reason()

        # Print summary
        passed = sum(1 for r in self.results if r["status"] == "\u2705 PASS")
        total = len(self.results)
        self.console.print(f"\n[bold]Cognitive State API Tests: {passed}/{total} passed[/bold]")

        return self.results

    def _record_result(self, test_name: str, passed: bool, error: str = None, details: dict = None):
        """Record a test result."""
        status = "\u2705 PASS" if passed else "\u274c FAIL"
        result = {"test": test_name, "status": status, "error": error}
        if details:
            result["details"] = details
        self.results.append(result)

        if passed:
            self.console.print(f"  {status} {test_name}")
        else:
            self.console.print(f"  {status} {test_name}: {error}")

    async def _make_request(self, method: str, path: str, json: dict = None) -> dict:
        """Make a raw HTTP request via the SDK transport."""
        try:
            kwargs = {}
            if json:
                kwargs["json"] = json
            response = await self.client._transport.request(method, path, **kwargs)
            return {"status_code": 200, "data": response}
        except Exception as e:
            # Parse error response if available
            error_str = str(e)
            if "400" in error_str:
                return {"status_code": 400, "error": error_str}
            elif "401" in error_str:
                return {"status_code": 401, "error": error_str}
            elif "403" in error_str:
                return {"status_code": 403, "error": error_str}
            elif "404" in error_str:
                return {"status_code": 404, "error": error_str}
            elif "422" in error_str:
                return {"status_code": 422, "error": error_str}
            elif "500" in error_str:
                return {"status_code": 500, "error": error_str}
            elif "503" in error_str:
                return {"status_code": 503, "error": error_str}
            raise

    async def _test_invalid_target_state(self):
        """Test that invalid target state is rejected."""
        test_name = "invalid_target_state"
        try:
            response = await self._make_request(
                "POST",
                "/v1/system/state/transition",
                json={"target_state": "INVALID_STATE"},
            )

            if response.get("status_code") == 400:
                self._record_result(test_name, True)
            else:
                self._record_result(
                    test_name,
                    False,
                    f"Expected 400, got {response.get('status_code')}",
                )
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_missing_target_state(self):
        """Test that missing target_state field is rejected."""
        test_name = "missing_target_state"
        try:
            response = await self._make_request(
                "POST",
                "/v1/system/state/transition",
                json={},
            )

            # Should get 422 (validation error) or 400
            status = response.get("status_code")
            if status in (400, 422):
                self._record_result(test_name, True)
            else:
                self._record_result(
                    test_name,
                    False,
                    f"Expected 400/422, got {status}",
                )
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_get_current_state(self):
        """Test getting current cognitive state via status endpoint."""
        test_name = "get_current_state"
        try:
            # Use SDK's agent.get_status() method
            status = await self.client.agent.get_status()
            if hasattr(status, "cognitive_state"):
                state = status.cognitive_state
                self._record_result(test_name, True, details={"current_state": state})
            else:
                self._record_result(test_name, False, "Response missing cognitive_state")
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_transition_to_dream(self):
        """Test transitioning to DREAM state."""
        test_name = "transition_to_dream"
        await self._test_transition("DREAM", test_name)

    async def _test_transition_to_play(self):
        """Test transitioning to PLAY state."""
        test_name = "transition_to_play"
        await self._test_transition("PLAY", test_name)

    async def _test_transition_to_solitude(self):
        """Test transitioning to SOLITUDE state."""
        test_name = "transition_to_solitude"
        await self._test_transition("SOLITUDE", test_name)

    async def _test_transition_back_to_work(self):
        """Test transitioning back to WORK state."""
        test_name = "transition_to_work"
        await self._test_transition("WORK", test_name)

    async def _test_transition(self, target_state: str, test_name: str):
        """Helper to test a state transition."""
        try:
            response = await self._make_request(
                "POST",
                "/v1/system/state/transition",
                json={"target_state": target_state},
            )

            status_code = response.get("status_code")
            if status_code == 200:
                data = response.get("data", {})
                if isinstance(data, dict) and "data" in data:
                    result = data["data"]
                else:
                    result = data

                success = result.get("success", False) if isinstance(result, dict) else False
                current = result.get("current_state", "UNKNOWN") if isinstance(result, dict) else "UNKNOWN"
                previous = result.get("previous_state", "UNKNOWN") if isinstance(result, dict) else "UNKNOWN"

                if success:
                    self._record_result(
                        test_name,
                        True,
                        details={
                            "previous": previous,
                            "current": current,
                            "target": target_state,
                        },
                    )
                else:
                    # Transition not initiated - might be expected if state is disabled
                    msg = result.get("message", "Unknown") if isinstance(result, dict) else "Unknown"
                    self._record_result(
                        test_name,
                        False,
                        f"Transition not initiated: {msg}",
                    )
            elif status_code == 503:
                # State transition not supported - record as skip
                self._record_result(
                    test_name,
                    False,
                    "State transition not supported by runtime",
                )
            else:
                self._record_result(
                    test_name,
                    False,
                    f"Status {status_code}: {response.get('error', 'Unknown')[:200]}",
                )
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_transition_with_reason(self):
        """Test transition with custom reason."""
        test_name = "transition_with_reason"
        try:
            response = await self._make_request(
                "POST",
                "/v1/system/state/transition",
                json={
                    "target_state": "WORK",
                    "reason": "QA test: returning to work after custom reason test",
                },
            )

            status_code = response.get("status_code")
            if status_code == 200:
                self._record_result(test_name, True)
            else:
                self._record_result(
                    test_name,
                    False,
                    f"Status {status_code}",
                )
        except Exception as e:
            self._record_result(test_name, False, str(e))

    @staticmethod
    def get_test_cases() -> List[QATestCase]:
        """Get static test cases for integration with main QA runner."""
        return [
            QATestCase(
                name="Get current cognitive state",
                module=QAModule.STATE_TRANSITIONS,
                endpoint="/v1/agent/status",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Get current cognitive state from agent status",
            ),
            QATestCase(
                name="Transition to DREAM state",
                module=QAModule.STATE_TRANSITIONS,
                endpoint="/v1/system/state/transition",
                method="POST",
                payload={"target_state": "DREAM"},
                expected_status=200,
                requires_auth=True,
                description="Request transition to DREAM cognitive state",
                timeout=60.0,
            ),
            QATestCase(
                name="Transition back to WORK state",
                module=QAModule.STATE_TRANSITIONS,
                endpoint="/v1/system/state/transition",
                method="POST",
                payload={"target_state": "WORK"},
                expected_status=200,
                requires_auth=True,
                description="Request transition back to WORK state",
                timeout=60.0,
            ),
            QATestCase(
                name="Transition to PLAY state",
                module=QAModule.STATE_TRANSITIONS,
                endpoint="/v1/system/state/transition",
                method="POST",
                payload={"target_state": "PLAY"},
                expected_status=200,
                requires_auth=True,
                description="Request transition to PLAY cognitive state",
                timeout=60.0,
            ),
            QATestCase(
                name="Transition to SOLITUDE state",
                module=QAModule.STATE_TRANSITIONS,
                endpoint="/v1/system/state/transition",
                method="POST",
                payload={"target_state": "SOLITUDE"},
                expected_status=200,
                requires_auth=True,
                description="Request transition to SOLITUDE cognitive state",
                timeout=60.0,
            ),
            QATestCase(
                name="Invalid state transition",
                module=QAModule.STATE_TRANSITIONS,
                endpoint="/v1/system/state/transition",
                method="POST",
                payload={"target_state": "INVALID_STATE"},
                expected_status=400,
                requires_auth=True,
                description="Test rejection of invalid target state",
            ),
            QATestCase(
                name="Transition with custom reason",
                module=QAModule.STATE_TRANSITIONS,
                endpoint="/v1/system/state/transition",
                method="POST",
                payload={
                    "target_state": "WORK",
                    "reason": "QA test: testing custom reason field",
                },
                expected_status=200,
                requires_auth=True,
                description="Test transition with custom reason",
            ),
        ]


def run_cognitive_state_api_tests_sync(client: Any, console: Console = None) -> List[Dict]:
    """Run cognitive state API tests synchronously (for CLI invocation)."""
    if console is None:
        console = Console()

    tests = CognitiveStateAPITests(client=client, console=console)
    return asyncio.run(tests.run())
