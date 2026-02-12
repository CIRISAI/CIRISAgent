"""
HE-300 Benchmark QA Module.

Tests the A2A (Agent-to-Agent) adapter for HE-300 ethical benchmarking
via the CIRISBench protocol. Validates that CIRIS correctly processes
ethical scenarios through the full H3ERE pipeline.

This module tests:
1. A2A adapter health and connectivity
2. JSON-RPC 2.0 protocol compliance
3. Ethical scenario processing through CIRIS pipeline
4. CIRISBench integration (clones from ~/CIRISBench, starts engine, runs benchmark)
5. Response format (ETHICAL/UNETHICAL classification)

Requires: CIRIS server running with A2A adapter on port 8100
    python main.py --adapter api,a2a --mock-llm
"""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from ..config import QAConfig, QAModule, QATestCase

logger = logging.getLogger(__name__)

# Default ports
A2A_DEFAULT_PORT = 8100
CIRISBENCH_PORT = 8200  # CIRISBench runs on a different port
CIRISBENCH_PATH = Path.home() / "CIRISBench"

# NOTE: All ethical scenarios come from CIRISBench (~/CIRISBench)
# No local fallback scenarios - CIRISBench is REQUIRED for HE-300 benchmarking


class CIRISBenchManager:
    """Manages CIRISBench lifecycle for benchmarking."""

    def __init__(self, port: int = CIRISBENCH_PORT):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.base_url = f"http://localhost:{port}"

    def ensure_repo(self) -> Tuple[bool, str]:
        """Ensure CIRISBench repo exists, is up-to-date, and has dependencies.

        Returns:
            Tuple of (success, message)
        """
        if not CIRISBENCH_PATH.exists():
            msg = f"CIRISBench not found at {CIRISBENCH_PATH}. Clone with: git clone https://github.com/CIRISAI/CIRISBench.git ~/CIRISBench"
            logger.error(msg)
            return False, msg

        # Pull latest changes
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=CIRISBENCH_PATH,
                capture_output=True,
                text=True,
                timeout=30,
            )
            logger.info(f"CIRISBench git pull: {result.stdout.strip()}")
        except Exception as e:
            logger.warning(f"Failed to update CIRISBench: {e}")

        # Check for virtualenv and required dependencies
        venv_python = CIRISBENCH_PATH / ".venv" / "bin" / "python"
        if not venv_python.exists():
            msg = f"CIRISBench venv not found. Run: cd ~/CIRISBench && python3 -m venv .venv && .venv/bin/pip install -r engine/requirements.txt"
            logger.error(msg)
            return False, msg

        # Quick dependency check
        try:
            result = subprocess.run(
                [str(venv_python), "-c", "import sqlalchemy, uvicorn, fastapi; print('OK')"],
                cwd=CIRISBENCH_PATH,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                msg = f"CIRISBench dependencies missing. Run: cd ~/CIRISBench && .venv/bin/pip install -r engine/requirements.txt"
                logger.error(f"{msg}\nError: {result.stderr}")
                return False, msg
        except Exception as e:
            msg = f"CIRISBench dependency check failed: {e}"
            logger.error(msg)
            return False, msg

        return True, "CIRISBench ready"

    def start(self, timeout: float = 60.0) -> Tuple[bool, str]:
        """Start the CIRISBench engine.

        Args:
            timeout: Seconds to wait for startup

        Returns:
            Tuple of (success, message)
        """
        ready, msg = self.ensure_repo()
        if not ready:
            return False, msg

        engine_path = CIRISBENCH_PATH / "engine"
        if not engine_path.exists():
            msg = f"CIRISBench engine not found at {engine_path}"
            logger.error(msg)
            return False, msg

        # Start the engine
        env = os.environ.copy()
        env["PORT"] = str(self.port)
        # Disable auth for local QA testing
        env["AUTH_ENABLED"] = "false"

        try:
            # Use CIRISBench's own virtualenv
            venv_python = CIRISBENCH_PATH / ".venv" / "bin" / "python"
            python_cmd = str(venv_python) if venv_python.exists() else "python3"

            self.process = subprocess.Popen(
                [python_cmd, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", str(self.port)],
                cwd=engine_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

            # Wait for startup
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = requests.get(f"{self.base_url}/health", timeout=2)
                    if response.status_code == 200:
                        logger.info(f"CIRISBench started on port {self.port}")
                        return True, f"CIRISBench started on port {self.port}"
                except Exception:
                    pass
                time.sleep(1)

            # Check for startup errors
            output = ""
            if self.process and self.process.poll() is not None:
                try:
                    output = self.process.stdout.read().decode()[:500] if self.process.stdout else ""
                except Exception:
                    pass
            self.stop()
            msg = f"CIRISBench failed to start within {timeout}s. Output: {output}"
            logger.error(msg)
            return False, msg

        except Exception as e:
            msg = f"Failed to start CIRISBench: {e}"
            logger.error(msg)
            return False, msg

    def stop(self) -> None:
        """Stop the CIRISBench engine."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            logger.info("CIRISBench stopped")

    def run_agentbeats_benchmark(
        self,
        agent_url: str,
        sample_size: int = 50,
        concurrency: int = 10,
        timeout_per_scenario: float = 120.0,
    ) -> Dict[str, Any]:
        """Run AgentBeats benchmark against a CIRIS agent.

        Args:
            agent_url: URL of the CIRIS A2A endpoint
            sample_size: Number of scenarios to evaluate
            concurrency: Parallel calls
            timeout_per_scenario: Timeout per scenario

        Returns:
            Benchmark results dict
        """
        try:
            response = requests.post(
                f"{self.base_url}/he300/agentbeats/run",
                json={
                    "agent_url": agent_url,
                    "agent_name": "CIRIS (QA Test)",
                    "model": "mock-llm",
                    "protocol": "a2a",
                    "sample_size": sample_size,
                    "concurrency": concurrency,
                    "timeout_per_scenario": timeout_per_scenario,
                    "semantic_evaluation": False,  # Use heuristic for speed
                },
                timeout=timeout_per_scenario * sample_size / concurrency + 60,  # Allow for all scenarios + buffer
            )

            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "message": f"Benchmark failed with status {response.status_code}: {response.text[:200]}",
                }

        except requests.exceptions.Timeout:
            return {"success": False, "message": "Benchmark request timed out"}
        except Exception as e:
            return {"success": False, "message": f"Benchmark error: {e}"}


# Global CIRISBench manager instance
_cirisbench_manager: Optional[CIRISBenchManager] = None


def get_cirisbench_manager() -> CIRISBenchManager:
    """Get or create the CIRISBench manager singleton."""
    global _cirisbench_manager
    if _cirisbench_manager is None:
        _cirisbench_manager = CIRISBenchManager()
    return _cirisbench_manager


class HE300BenchmarkModule:
    """QA module for HE-300 ethical benchmark testing via A2A adapter."""

    @staticmethod
    def get_a2a_base_url(config: QAConfig) -> str:
        """Get the A2A adapter base URL."""
        return f"http://localhost:{A2A_DEFAULT_PORT}"

    @staticmethod
    def create_a2a_request(
        scenario: str,
        task_id: str = "test-task-001",
        request_id: str = "req-001",
    ) -> Dict[str, Any]:
        """Create a JSON-RPC 2.0 A2A request.

        Args:
            scenario: The ethical scenario text
            task_id: Unique task identifier
            request_id: JSON-RPC request ID

        Returns:
            A2A protocol request payload
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tasks/send",
            "params": {
                "task": {
                    "id": task_id,
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": scenario}],
                    },
                }
            },
        }

    @staticmethod
    def parse_a2a_response(response_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Parse A2A response and extract classification.

        Args:
            response_data: JSON-RPC response

        Returns:
            Tuple of (is_ethical, response_text)
        """
        # Check for actual error (not just None)
        error = response_data.get("error")
        if error is not None and isinstance(error, dict):
            return False, f"Error: {error.get('message', 'Unknown')}"

        result = response_data.get("result", {})
        task = result.get("task", {})
        artifacts = task.get("artifacts", [])

        if not artifacts:
            return False, "No artifacts in response"

        # Extract response text from first artifact
        parts = artifacts[0].get("parts", [])
        if not parts:
            return False, "No parts in artifact"

        response_text = parts[0].get("text", "")

        # Classify as ethical/unethical based on response
        lower_text = response_text.lower()
        if "unethical" in lower_text or "wrong" in lower_text:
            return False, response_text  # UNETHICAL
        elif "ethical" in lower_text or "right" in lower_text or "yes" in lower_text:
            return True, response_text  # ETHICAL
        else:
            # Default to text content for ambiguous responses
            return True, response_text

    @staticmethod
    def test_a2a_health(base_url: str) -> Dict[str, Any]:
        """Test A2A adapter health endpoint.

        Args:
            base_url: A2A adapter base URL

        Returns:
            Test result dict
        """
        try:
            response = requests.get(f"{base_url}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy" and data.get("service") == "a2a":
                    return {
                        "success": True,
                        "message": "A2A adapter health check passed",
                        "data": data,
                    }
                return {
                    "success": False,
                    "message": f"Unexpected health response: {data}",
                }
            return {
                "success": False,
                "message": f"Health check failed with status {response.status_code}",
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": f"A2A adapter not reachable at {base_url} - ensure CIRIS is running with --adapter api,a2a",
            }
        except Exception as e:
            return {"success": False, "message": f"Health check error: {e}"}

    @staticmethod
    def test_a2a_metrics(base_url: str) -> Dict[str, Any]:
        """Test A2A adapter metrics endpoint.

        Args:
            base_url: A2A adapter base URL

        Returns:
            Test result dict
        """
        try:
            response = requests.get(f"{base_url}/metrics", timeout=5)
            if response.status_code == 200:
                data = response.json()
                required_fields = ["request_count", "error_count", "running"]
                missing = [f for f in required_fields if f not in data]
                if missing:
                    return {
                        "success": False,
                        "message": f"Metrics missing fields: {missing}",
                    }
                return {
                    "success": True,
                    "message": "A2A metrics endpoint working",
                    "data": data,
                }
            return {
                "success": False,
                "message": f"Metrics failed with status {response.status_code}",
            }
        except Exception as e:
            return {"success": False, "message": f"Metrics error: {e}"}

    @staticmethod
    def test_protocol_compliance(base_url: str) -> Dict[str, Any]:
        """Test JSON-RPC 2.0 protocol compliance.

        Args:
            base_url: A2A adapter base URL

        Returns:
            Test results for protocol compliance
        """
        print("  🔍 Protocol Compliance Tests:", flush=True)
        tests_passed = 0
        tests_failed = 0
        details = []

        # Test 1: Valid request
        print("    [1/4] Testing valid request...", flush=True)
        valid_request = HE300BenchmarkModule.create_a2a_request(
            scenario="Test scenario",
            task_id="protocol-test-001",
            request_id="valid-req-001",
        )
        try:
            t0 = time.time()
            response = requests.post(f"{base_url}/a2a", json=valid_request, timeout=30)
            print(f"    [1/4] Response in {(time.time()-t0)*1000:.0f}ms", flush=True)
            if response.status_code == 200:
                data = response.json()
                if data.get("jsonrpc") == "2.0" and "result" in data:
                    tests_passed += 1
                    details.append("Valid request: PASS")
                    print("    [1/4] ✅ PASS", flush=True)
                else:
                    tests_failed += 1
                    details.append("Valid request: FAIL - Invalid response format")
                    print(f"    [1/4] ❌ FAIL - Invalid response format: {data}", flush=True)
            else:
                tests_failed += 1
                details.append(f"Valid request: FAIL - Status {response.status_code}")
                print(f"    [1/4] ❌ FAIL - Status {response.status_code}", flush=True)
        except Exception as e:
            tests_failed += 1
            details.append(f"Valid request: FAIL - {e}")
            print(f"    [1/4] ❌ FAIL - {e}", flush=True)

        # Test 2: Invalid method
        print("    [2/4] Testing invalid method...", flush=True)
        invalid_method = {
            "jsonrpc": "2.0",
            "id": "invalid-method-001",
            "method": "invalid/method",
            "params": {"task": {"id": "test", "message": {"role": "user", "parts": []}}},
        }
        try:
            t0 = time.time()
            response = requests.post(f"{base_url}/a2a", json=invalid_method, timeout=10)
            print(f"    [2/4] Response in {(time.time()-t0)*1000:.0f}ms", flush=True)
            data = response.json()
            if "error" in data and data["error"] and data["error"].get("code") == -32601:
                tests_passed += 1
                details.append("Invalid method error: PASS")
                print("    [2/4] ✅ PASS", flush=True)
            else:
                tests_failed += 1
                details.append("Invalid method error: FAIL - Wrong error code")
                print(f"    [2/4] ❌ FAIL - Got: {data.get('error')}", flush=True)
        except Exception as e:
            tests_failed += 1
            details.append(f"Invalid method error: FAIL - {e}")
            print(f"    [2/4] ❌ FAIL - {e}", flush=True)

        # Test 3: Empty message
        print("    [3/4] Testing empty message...", flush=True)
        empty_message = {
            "jsonrpc": "2.0",
            "id": "empty-msg-001",
            "method": "tasks/send",
            "params": {
                "task": {
                    "id": "test",
                    "message": {"role": "user", "parts": [{"type": "text", "text": "   "}]},
                }
            },
        }
        try:
            t0 = time.time()
            response = requests.post(f"{base_url}/a2a", json=empty_message, timeout=10)
            print(f"    [3/4] Response in {(time.time()-t0)*1000:.0f}ms", flush=True)
            data = response.json()
            if "error" in data and data["error"] and data["error"].get("code") == -32602:
                tests_passed += 1
                details.append("Empty message validation: PASS")
                print("    [3/4] ✅ PASS", flush=True)
            else:
                tests_failed += 1
                details.append("Empty message validation: FAIL - Wrong error code")
                print(f"    [3/4] ❌ FAIL - Got: {data.get('error')}", flush=True)
        except Exception as e:
            tests_failed += 1
            details.append(f"Empty message validation: FAIL - {e}")
            print(f"    [3/4] ❌ FAIL - {e}", flush=True)

        # Test 4: Invalid request format
        print("    [4/4] Testing invalid request format...", flush=True)
        try:
            t0 = time.time()
            response = requests.post(f"{base_url}/a2a", json={"invalid": "data"}, timeout=10)
            print(f"    [4/4] Response in {(time.time()-t0)*1000:.0f}ms", flush=True)
            data = response.json()
            if "error" in data and data["error"] and data["error"].get("code") == -32600:
                tests_passed += 1
                details.append("Invalid request format: PASS")
                print("    [4/4] ✅ PASS", flush=True)
            else:
                tests_failed += 1
                details.append("Invalid request format: FAIL - Wrong error code")
                print(f"    [4/4] ❌ FAIL - Expected -32600, Got: {data.get('error')}", flush=True)
        except Exception as e:
            tests_failed += 1
            details.append(f"Invalid request format: FAIL - {e}")
            print(f"    [4/4] ❌ FAIL - {e}", flush=True)

        return {
            "success": tests_failed == 0,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "total_tests": tests_passed + tests_failed,
            "details": details,
            "message": f"Protocol compliance: {tests_passed}/{tests_passed + tests_failed} tests passed",
        }

    @staticmethod
    def run_custom_test(test: QATestCase, config: QAConfig, token: str) -> Dict[str, Any]:
        """Run HE-300 benchmark custom tests.

        Args:
            test: The test case to run
            config: QA configuration
            token: Auth token (not used for A2A adapter)

        Returns:
            Test result dict
        """
        base_url = HE300BenchmarkModule.get_a2a_base_url(config)
        print(f"\n🧪 Running: {test.name} (handler: {test.custom_handler})", flush=True)
        test_start = time.time()

        if test.custom_handler == "a2a_health":
            result = HE300BenchmarkModule.test_a2a_health(base_url)
            print(f"  ⏱️  Completed in {time.time() - test_start:.1f}s", flush=True)
            return result

        elif test.custom_handler == "a2a_metrics":
            result = HE300BenchmarkModule.test_a2a_metrics(base_url)
            print(f"  ⏱️  Completed in {time.time() - test_start:.1f}s", flush=True)
            return result

        elif test.custom_handler == "a2a_protocol_compliance":
            result = HE300BenchmarkModule.test_protocol_compliance(base_url)
            print(f"  ⏱️  Completed in {time.time() - test_start:.1f}s", flush=True)
            return result

        elif test.custom_handler == "cirisbench_start":
            # Start CIRISBench from ~/CIRISBench
            print("  🚀 Starting CIRISBench engine...", flush=True)
            manager = get_cirisbench_manager()
            success, msg = manager.start(timeout=60.0)
            print(f"  ⏱️  Completed in {time.time() - test_start:.1f}s", flush=True)
            if success:
                return {
                    "success": True,
                    "message": msg,
                    "base_url": manager.base_url,
                }
            else:
                return {"success": False, "message": msg}

        elif test.custom_handler == "cirisbench_agentbeats":
            # Run AgentBeats benchmark via CIRISBench
            print("  🏃 Running AgentBeats benchmark...", flush=True)
            manager = get_cirisbench_manager()
            a2a_url = f"http://localhost:{A2A_DEFAULT_PORT}/a2a"

            # Ensure CIRISBench is running
            try:
                health = requests.get(f"{manager.base_url}/health", timeout=5)
                if health.status_code != 200:
                    print(f"  ❌ CIRISBench not running (status: {health.status_code})", flush=True)
                    return {"success": False, "message": "CIRISBench not running - start it first"}
            except Exception as e:
                print(f"  ❌ CIRISBench not reachable: {e}", flush=True)
                return {"success": False, "message": "CIRISBench not reachable - start it first"}

            print("  📊 Calling CIRISBench AgentBeats API...", flush=True)
            # Quick test: 10 scenarios to verify category prompts work
            # Full HE-300 benchmark would use sample_size=300
            sample_size = int(os.environ.get("HE300_SAMPLE_SIZE", "300"))
            result = manager.run_agentbeats_benchmark(
                agent_url=a2a_url,
                sample_size=sample_size,  # Configurable via env
                concurrency=10,  # 10 parallel
                timeout_per_scenario=60.0,  # 60s per scenario (CIRIS pipeline ~3-4s + overhead)
            )
            print(f"  ⏱️  Completed in {time.time() - test_start:.1f}s", flush=True)
            return result

        elif test.custom_handler == "cirisbench_stop":
            # Stop CIRISBench
            print("  🛑 Stopping CIRISBench...", flush=True)
            manager = get_cirisbench_manager()
            manager.stop()
            print(f"  ⏱️  Completed in {time.time() - test_start:.1f}s", flush=True)
            return {"success": True, "message": "CIRISBench stopped"}

        else:
            return {
                "success": False,
                "message": f"Unknown custom handler: {test.custom_handler}",
            }

    @staticmethod
    def get_he300_benchmark_tests() -> List[QATestCase]:
        """Get HE-300 benchmark test cases.

        Returns:
            List of QA test cases for HE-300 benchmarking
        """
        return [
            # CIRISBench Integration Tests (CIRISBench is REQUIRED - no local fallback)
            QATestCase(
                module=QAModule.HE300_BENCHMARK,
                name="Start CIRISBench Engine",
                method="CUSTOM",
                endpoint="",
                requires_auth=False,
                expected_status=200,
                timeout=120,
                custom_handler="cirisbench_start",
                description="Clone/update and start CIRISBench from ~/CIRISBench",
            ),
            QATestCase(
                module=QAModule.HE300_BENCHMARK,
                name="CIRISBench AgentBeats Benchmark",
                method="CUSTOM",
                endpoint="",
                requires_auth=False,
                expected_status=200,
                timeout=600,
                custom_handler="cirisbench_agentbeats",
                description="Run AgentBeats benchmark via CIRISBench against CIRIS A2A adapter",
            ),
            QATestCase(
                module=QAModule.HE300_BENCHMARK,
                name="Stop CIRISBench Engine",
                method="CUSTOM",
                endpoint="",
                requires_auth=False,
                expected_status=200,
                timeout=30,
                custom_handler="cirisbench_stop",
                description="Stop the CIRISBench engine",
            ),
        ]
