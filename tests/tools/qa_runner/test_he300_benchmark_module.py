"""
Tests for the HE-300 Benchmark QA module.

Validates the QA module's ability to test the A2A adapter
for HE-300 ethical benchmarking.
"""

import pytest

from tools.qa_runner.config import QAConfig, QAModule
from tools.qa_runner.modules.he300_benchmark_tests import HE300BenchmarkModule


class TestHE300BenchmarkModule:
    """Tests for HE300BenchmarkModule."""

    def test_module_loads(self):
        """Test that the module loads correctly."""
        config = QAConfig()
        tests = config.get_module_tests(QAModule.HE300_BENCHMARK)
        assert len(tests) == 3  # 3 CIRISBench tests (start, agentbeats, stop)

    def test_test_names(self):
        """Test that all expected tests are present."""
        tests = HE300BenchmarkModule.get_he300_benchmark_tests()
        test_names = [t.name for t in tests]
        assert "Start CIRISBench Engine" in test_names
        assert "CIRISBench AgentBeats Benchmark" in test_names
        assert "Stop CIRISBench Engine" in test_names

    def test_custom_handlers_assigned(self):
        """Test that custom handlers are properly assigned."""
        tests = HE300BenchmarkModule.get_he300_benchmark_tests()
        handlers = [t.custom_handler for t in tests]
        assert "cirisbench_start" in handlers
        assert "cirisbench_agentbeats" in handlers
        assert "cirisbench_stop" in handlers

    @pytest.mark.skip(reason="HE300_TEST_SCENARIOS removed - scenarios now handled by CIRISBench")
    def test_test_scenarios_present(self):
        """Test that HE-300 test scenarios are defined."""
        pass

    @pytest.mark.skip(reason="HE300_TEST_SCENARIOS removed - scenarios now handled by CIRISBench")
    def test_scenario_structure(self):
        """Test that scenarios have required fields."""
        pass

    def test_create_a2a_request(self):
        """Test A2A request creation."""
        request = HE300BenchmarkModule.create_a2a_request(
            scenario="Test scenario",
            task_id="test-task",
            request_id="req-test",
        )
        assert request["jsonrpc"] == "2.0"
        assert request["id"] == "req-test"
        assert request["method"] == "tasks/send"
        assert request["params"]["task"]["id"] == "test-task"
        assert request["params"]["task"]["message"]["role"] == "user"
        parts = request["params"]["task"]["message"]["parts"]
        assert len(parts) == 1
        assert parts[0]["type"] == "text"
        assert parts[0]["text"] == "Test scenario"

    def test_parse_a2a_response_success(self):
        """Test parsing successful A2A response."""
        response_data = {
            "jsonrpc": "2.0",
            "id": "req-001",
            "result": {
                "task": {
                    "id": "task-001",
                    "status": "completed",
                    "artifacts": [
                        {
                            "parts": [
                                {
                                    "type": "text",
                                    "text": "Yes, this action is ethical because...",
                                }
                            ]
                        }
                    ],
                }
            },
        }
        is_ethical, response_text = HE300BenchmarkModule.parse_a2a_response(response_data)
        assert is_ethical is True
        assert "ethical" in response_text.lower()

    def test_parse_a2a_response_unethical(self):
        """Test parsing unethical response."""
        response_data = {
            "jsonrpc": "2.0",
            "id": "req-001",
            "result": {
                "task": {
                    "id": "task-001",
                    "status": "completed",
                    "artifacts": [
                        {
                            "parts": [
                                {
                                    "type": "text",
                                    "text": "This action is unethical because...",
                                }
                            ]
                        }
                    ],
                }
            },
        }
        is_ethical, response_text = HE300BenchmarkModule.parse_a2a_response(response_data)
        assert is_ethical is False

    def test_parse_a2a_response_error(self):
        """Test parsing error response."""
        response_data = {
            "jsonrpc": "2.0",
            "id": "req-001",
            "error": {"code": -32603, "message": "Internal error"},
        }
        is_ethical, response_text = HE300BenchmarkModule.parse_a2a_response(response_data)
        assert is_ethical is False
        assert "Error" in response_text

    def test_parse_a2a_response_null_error(self):
        """Test parsing response with null error field."""
        response_data = {
            "jsonrpc": "2.0",
            "id": "req-001",
            "result": {
                "task": {
                    "id": "task-001",
                    "status": "completed",
                    "artifacts": [{"parts": [{"type": "text", "text": "ETHICAL"}]}],
                }
            },
            "error": None,  # Null error field should be ignored
        }
        is_ethical, response_text = HE300BenchmarkModule.parse_a2a_response(response_data)
        assert is_ethical is True

    def test_get_a2a_base_url(self):
        """Test A2A base URL retrieval."""
        config = QAConfig()
        url = HE300BenchmarkModule.get_a2a_base_url(config)
        assert url == "http://localhost:8100"

    def test_tests_have_correct_module(self):
        """Test that all tests are assigned to HE300_BENCHMARK module."""
        tests = HE300BenchmarkModule.get_he300_benchmark_tests()
        for test in tests:
            assert test.module == QAModule.HE300_BENCHMARK

    def test_tests_dont_require_auth(self):
        """Test that A2A tests don't require auth (A2A has its own endpoint)."""
        tests = HE300BenchmarkModule.get_he300_benchmark_tests()
        for test in tests:
            assert test.requires_auth is False

    def test_tests_use_custom_method(self):
        """Test that all HE-300 tests use CUSTOM method."""
        tests = HE300BenchmarkModule.get_he300_benchmark_tests()
        for test in tests:
            assert test.method == "CUSTOM"
