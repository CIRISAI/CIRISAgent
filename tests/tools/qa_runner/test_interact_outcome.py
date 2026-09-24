"""QA honesty for interact() timeouts (#1059) and module SERVER_ENV precedence.

A timed-out interact() is HTTP 200 whose `response` is the localized
still-processing placeholder. The safety battery recorded that as
success=true, error=null, and model_eval/air/vision matched only the English
placeholder text.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.qa_runner.modules.interact_outcome import (
    LOCALIZED_DIR,
    InteractNonReply,
    interact_non_reply,
    interact_timed_out,
    is_still_processing_text,
    still_processing_placeholders,
)
from tools.qa_runner.server import apply_module_server_env

pytestmark = pytest.mark.timeout(60)

ROOT = Path(__file__).resolve().parents[3]


def _placeholder(lang: str) -> str:
    return json.loads((ROOT / "ciris_engine/data/localized" / f"{lang}.json").read_text(encoding="utf-8"))["agent"][
        "still_processing"
    ]


class TestPlaceholders:
    def test_loaded_from_the_servers_string_tables(self):
        assert LOCALIZED_DIR == ROOT / "ciris_engine" / "data" / "localized"
        placeholders = still_processing_placeholders()
        manifest = json.loads((ROOT / "ciris_engine/data/localized" / "manifest.json").read_text(encoding="utf-8"))
        langs = manifest.get("languages") or manifest.get("supported_languages") or {}
        codes = list(langs.keys()) if isinstance(langs, dict) else [
            entry["code"] if isinstance(entry, dict) else entry for entry in langs
        ]
        assert codes, "manifest lists no languages"
        for code in codes:
            path = ROOT / "ciris_engine/data/localized" / f"{code}.json"
            if path.exists():
                assert _placeholder(code) in placeholders, code

    @pytest.mark.parametrize("lang", ["en", "am", "zh", "ar", "fr"])
    def test_any_locale_matches(self, lang):
        assert is_still_processing_text(_placeholder(lang))

    def test_real_replies_do_not_match(self):
        assert not is_still_processing_text("Still here! How can I help?")
        assert not is_still_processing_text("")
        assert not is_still_processing_text(None)


class TestNonReply:
    def test_outcome_timeout(self):
        data = {"response": "whatever", "task_id": "t1", "outcome": "timeout"}
        assert interact_non_reply(data) is InteractNonReply.TIMEOUT
        assert interact_timed_out(data)

    def test_outcome_paused(self):
        assert interact_non_reply({"response": "x", "outcome": "paused"}) is InteractNonReply.PAUSED

    def test_outcome_complete_trusts_the_server_even_if_text_looks_like_the_placeholder(self):
        assert interact_non_reply({"response": _placeholder("en"), "task_id": "t1", "outcome": "complete"}) is None

    def test_old_server_placeholder_without_task_is_a_timeout(self):
        assert interact_timed_out({"response": _placeholder("am"), "task_id": None})

    def test_old_server_real_reply(self):
        assert interact_non_reply({"response": "ሰላም", "task_id": None}) is None


class _FakeHttp:
    """httpx.AsyncClient stand-in that answers every POST with `body`."""

    def __init__(self, body):
        self._body = body

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        response = MagicMock(status_code=200)
        response.json.return_value = self._body
        return response


class TestSafetyBatteryGrading:
    @pytest.mark.parametrize(
        "data,expected_success,expected_error",
        [
            ({"response": "a real answer", "task_id": "t1", "outcome": "complete"}, True, None),
            ({"response": _placeholder("en"), "task_id": "t1", "outcome": "timeout"}, False, "interact timeout"),
            # Pre-#1186 server, non-English agent: no outcome, no task, Amharic placeholder.
            ({"response": _placeholder("am"), "task_id": None}, False, "interact timeout"),
            ({"response": "x", "task_id": None, "outcome": "paused"}, False, "interact paused"),
            ({"response": "", "task_id": "t1", "outcome": "complete"}, False, "empty response body"),
        ],
    )
    def test_timeout_is_not_success(self, data, expected_success, expected_error):
        import asyncio

        from tools.qa_runner.modules import safety_battery as sb

        module = sb.SafetyBatteryTests.__new__(sb.SafetyBatteryTests)
        module.per_question_timeout_s = 5.0
        module._locale_token = "tok"
        module._locale_username = "u"
        module.client = None
        module.api_port = 8080
        question = {"question_id": "q1", "question_version": 1, "stage": "s1", "category": "c",
                    "translations": {"en": "hello"}}
        manifest = {"battery_id": "b", "battery_version": 1, "cell": {"domain": "d", "language": "en"}}

        with patch.object(sb.httpx, "AsyncClient", _FakeHttp({"data": data})):
            result = asyncio.run(module._run_question(question, manifest, "chan"))

        assert result.success is expected_success
        assert result.error == expected_error


class TestModuleServerEnvPrecedence:
    def test_module_beats_runner_default(self):
        env = {"CIRIS_API_INTERACTION_TIMEOUT": "180"}  # runner's generic default
        apply_module_server_env(env, {"CIRIS_API_INTERACTION_TIMEOUT": "1740"}, operator_env={})
        assert env["CIRIS_API_INTERACTION_TIMEOUT"] == "1740"

    def test_operator_export_beats_module(self):
        env = {"CIRIS_API_INTERACTION_TIMEOUT": "77"}
        apply_module_server_env(
            env, {"CIRIS_API_INTERACTION_TIMEOUT": "1740"}, operator_env={"CIRIS_API_INTERACTION_TIMEOUT": "77"}
        )
        assert env["CIRIS_API_INTERACTION_TIMEOUT"] == "77"

    @pytest.mark.parametrize("exported", [None, "77"])
    def test_through_server_start(self, monkeypatch, exported):
        """End to end through APIServerManager.start(): the safety battery's
        declared deadline reaches the agent process unless the operator
        exported one."""
        from tools.qa_runner.config import QAConfig, QAModule
        from tools.qa_runner.modules.safety_battery import SERVER_ENV
        from tools.qa_runner.server import APIServerManager

        if exported is None:
            monkeypatch.delenv("CIRIS_API_INTERACTION_TIMEOUT", raising=False)
        else:
            monkeypatch.setenv("CIRIS_API_INTERACTION_TIMEOUT", exported)

        config = QAConfig(base_url="http://localhost:8080", api_port=8080, mock_llm=True)
        manager = APIServerManager(config, modules=[QAModule.SAFETY_BATTERY])
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=12345)
            with patch.object(manager, "_wait_for_server", return_value=True):
                with patch.object(manager, "_is_server_running", return_value=False):
                    with patch("builtins.open", MagicMock()):
                        manager.start()
        env = mock_popen.call_args.kwargs.get("env", {})
        want = exported if exported is not None else SERVER_ENV["CIRIS_API_INTERACTION_TIMEOUT"]
        assert env.get("CIRIS_API_INTERACTION_TIMEOUT") == want
