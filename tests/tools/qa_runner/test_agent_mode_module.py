"""Tests for the ``agent_mode`` QA module.

Pins:
  - QAModule.AGENT_MODE enum exists with the expected wire-up.
  - The module is registered in all 3 required runner.py locations
    (import, module_map entry, sdk_modules list) — missing the sdk_modules
    entry silently skips the module, per QA Runner CLAUDE.md.
  - ``SERVER_MINIMUM_DISK_BYTES`` matches the engine constant so the test
    can't quietly drift away from the gate it asserts against.
  - All seven test methods are declared (regression guard for accidental
    deletions during refactors).
"""

from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestModuleStructure:
    """The module's surface contract."""

    def test_module_importable(self):
        from tools.qa_runner.modules.agent_mode_tests import AgentModeTests

        assert AgentModeTests.__name__ == "AgentModeTests"

    def test_constructs_with_minimal_args(self):
        from tools.qa_runner.modules.agent_mode_tests import AgentModeTests

        instance = AgentModeTests(client=MagicMock(), console=Console())
        assert instance.results == []
        assert instance._original_mode is None

    def test_required_test_methods_present(self):
        """If a refactor accidentally removes a test method, the module would
        silently skip that scenario. Pin the contract."""
        from tools.qa_runner.modules.agent_mode_tests import AgentModeTests

        required = {
            "test_get_requires_auth",
            "test_get_status_shape",
            "test_server_eligibility_consistent",
            "test_put_noop_current_mode",
            "test_put_invalid_mode",
            "test_put_server_disk_gate",
            "test_put_requires_auth",
        }
        missing = required - set(dir(AgentModeTests))
        assert not missing, f"AgentModeTests missing required test methods: {sorted(missing)}"

    def test_server_minimum_disk_bytes_matches_engine_constant(self):
        """The 256 GiB threshold is the contract gate. If engine and qa drift,
        the disk-gate test would silently pass on a misconfigured threshold."""
        from ciris_engine.constants import SERVER_MINIMUM_DISK_BYTES as engine_const
        from tools.qa_runner.modules.agent_mode_tests import SERVER_MINIMUM_DISK_BYTES as qa_const

        assert qa_const == engine_const, (
            f"QA module threshold ({qa_const}) drifted from engine constant "
            f"({engine_const}). Re-sync to keep test_put_server_disk_gate honest."
        )


class TestQARunnerWiring:
    """The module must be wired into the QA runner's three required places.

    Per ``tools/qa_runner/CLAUDE.md``: missing any one of these silently
    skips the module at runtime.
    """

    def test_qamodule_enum_has_agent_mode(self):
        from tools.qa_runner.config import QAModule

        assert hasattr(QAModule, "AGENT_MODE")
        assert QAModule.AGENT_MODE.value == "agent_mode"

    def test_runner_imports_agent_mode_tests(self):
        runner_src = (REPO_ROOT / "tools" / "qa_runner" / "runner.py").read_text()
        assert "from .modules.agent_mode_tests import AgentModeTests" in runner_src
        assert "QAModule.AGENT_MODE: AgentModeTests" in runner_src

    def test_agent_mode_in_sdk_modules_list(self):
        """If the module isn't in the sdk_modules list, _run_sdk_modules silently
        skips it — the QA Runner CLAUDE.md flags this as a CRITICAL pitfall."""
        runner_src = (REPO_ROOT / "tools" / "qa_runner" / "runner.py").read_text()
        # The sdk_modules list block contains entries of the form ``QAModule.NAME,``
        assert "QAModule.AGENT_MODE," in runner_src, (
            "QAModule.AGENT_MODE missing from sdk_modules list — module would be "
            "silently skipped by _run_sdk_modules. See tools/qa_runner/CLAUDE.md."
        )


class TestEndpointShape:
    """The module hits the documented endpoint paths."""

    def test_endpoint_path_matches_route(self):
        """Drift guard against router refactors. If the system router moves the
        path, this test makes the QA module catch up at PR time."""
        from tools.qa_runner.modules.agent_mode_tests import AgentModeTests

        instance = AgentModeTests(client=MagicMock(), console=Console())
        instance.client._transport = MagicMock(_api_key="tkn", base_url="http://x:1")
        instance.client._base_url = "http://x:1"

        # The module composes ``{base}/v1/system/agent-mode`` — assert by sniffing
        # an outbound request via the unittest.mock library.
        import requests

        with _capture_request("get") as captured:
            try:
                instance._get_mode("tkn")
            except Exception:
                # The mocked transport records the request then raises; this test
                # only asserts on the URL it was given, so the raise is expected.
                pass
            assert captured["url"].endswith("/v1/system/agent-mode"), captured["url"]

        with _capture_request("put") as captured:
            try:
                instance._put_mode("tkn", "proxy")
            except Exception:
                # Same as above — assert the request URL, ignore the mock's raise.
                pass
            assert captured["url"].endswith("/v1/system/agent-mode"), captured["url"]
            assert captured["json"] == {"mode": "proxy"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
from contextlib import contextmanager


@contextmanager
def _capture_request(verb: str):
    """Capture the URL/json of the next requests.<verb> call without hitting
    the network. The verb argument selects which requests function to monkey-patch."""
    import requests

    captured: dict = {}
    original = getattr(requests, verb)

    def fake(url, *args, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers")

        class _FakeResp:
            status_code = 599

            def json(self):
                return {}

            text = ""

        return _FakeResp()

    setattr(requests, verb, fake)
    try:
        yield captured
    finally:
        setattr(requests, verb, original)
