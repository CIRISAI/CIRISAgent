"""A requested template must reach the AGENT, not just the setup wizard.

The defect this locks down: `--<module>-template X` set `setup_template_id`,
which reached only the setup wizard. `CIRIS_TEMPLATE` — the variable the agent's
`EssentialConfig` and `component_builder` actually read — was exported only when
the module happened to be `he300_benchmark`. So a run launched with an explicit
template completed setup under it and then booted the agent under `default`.

It is the worst shape of failure: the run REPORTS the template it was asked for,
so logs, result keys and reports all name a configuration that never took effect.
Concretely it cost `cognitive_state_behaviors.wakeup.enabled: false` being
ignored (~10 min of wakeup on every boot of every arm) and
`EpistemicHumilityConscience` staying live in benchmark arms that exist
specifically to disable it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import List, Optional

import pytest

from tools.qa_runner.config import QAModule


class _Cfg(SimpleNamespace):
    """Minimal stand-in for QAConfig — only what the resolver touches."""

    def __init__(self, setup_template_id: Optional[str] = None) -> None:
        super().__init__(setup_template_id=setup_template_id)


def _server(template: Optional[str], modules: Optional[List[QAModule]] = None):
    """An APIServerManager with just enough state for template resolution."""
    from tools.qa_runner.server import APIServerManager

    s = APIServerManager.__new__(APIServerManager)  # bypass __init__ (it starts real machinery)
    s.config = _Cfg(setup_template_id=template)
    s.modules = modules or [QAModule.SAFETY_BATTERY]
    return s


class TestResolveTemplateId:
    def test_explicit_template_wins_for_any_module(self) -> None:
        """The flag used to be honoured only for safety_battery."""
        for mod in (QAModule.SAFETY_BATTERY, QAModule.MODEL_EVAL, QAModule.ACCORD_METRICS):
            s = _server("he-300-benchmark", [mod])
            assert s.resolve_template_id() == "he-300-benchmark", f"ignored for {mod}"

    def test_module_implied_default_when_unset(self) -> None:
        s = _server(None, [QAModule.HE300_BENCHMARK])
        assert s.resolve_template_id() == "he-300-benchmark"

    def test_plain_run_is_default(self) -> None:
        assert _server(None, [QAModule.SAFETY_BATTERY]).resolve_template_id() == "default"

    def test_explicit_overrides_module_implication(self) -> None:
        s = _server("sage", [QAModule.HE300_BENCHMARK])
        assert s.resolve_template_id() == "sage", "an explicit request must not be overridden"

    def test_one_resolver_feeds_wizard_and_env(self) -> None:
        """Wizard and server env must not be able to disagree.

        Both call `resolve_template_id`; asserting the source has exactly one
        read of `setup_template_id` keeps a second answer from reappearing.
        """
        import inspect

        from tools.qa_runner import server as server_mod

        src = inspect.getsource(server_mod)
        reads = src.count('getattr(self.config, "setup_template_id"')
        assert reads == 1, (
            f"setup_template_id is read {reads}x; it must be read ONLY inside "
            "resolve_template_id() so the wizard and the agent cannot diverge"
        )


class TestBenchmarkModeDerivation:
    def test_benchmark_mode_keys_off_template_not_module(self) -> None:
        """component_builder double-locks on (env AND template == he-300-benchmark).

        Deriving the env from the resolved template is what makes the two agree
        by construction. Keying off the module list is what let a benchmark
        template run with safety consciences live.
        """
        import inspect

        from tools.qa_runner import server as server_mod

        src = inspect.getsource(server_mod)
        idx = src.find('env["CIRIS_BENCHMARK_MODE"]')
        assert idx != -1, "CIRIS_BENCHMARK_MODE is no longer set"
        window = src[max(0, idx - 700) : idx]
        assert "is_benchmark" in window, "benchmark mode must derive from the resolved template"
        assert "QAModule.HE300_BENCHMARK for m in self.modules" not in window, (
            "benchmark mode is gated on the module list again — it must key off "
            "the resolved template so an explicit --template gets it too"
        )

    def test_template_env_is_set_unconditionally(self) -> None:
        import inspect

        from tools.qa_runner import server as server_mod

        src = inspect.getsource(server_mod)
        assert 'env["CIRIS_TEMPLATE"] = template_id' in src, (
            "CIRIS_TEMPLATE must be exported from the resolved template on every "
            "run — the agent reads it, and an unset value is an invisible default"
        )


class TestTemplateVerification:
    """An unknown is not a pass."""

    def _srv(self, tmp_path, want: str, log_text: Optional[str]):
        s = _server(want)
        s.database_backend = "sqlite"
        s.console = SimpleNamespace(messages=[], print=lambda m: s.console.messages.append(str(m)))
        if log_text is not None:
            d = tmp_path / "logs" / "sqlite"
            d.mkdir(parents=True, exist_ok=True)
            (d / "latest.log").write_text(log_text, encoding="utf-8")
        return s

    def test_match_verifies(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._srv(
            tmp_path,
            "he-300-benchmark",
            "Successfully loaded template 'HE300' from /x/ciris_templates/he-300-benchmark.yaml\n",
        )
        monkeypatch.chdir(tmp_path)
        assert s._verify_template_took_effect() is True
        assert any("VERIFIED" in m for m in s.console.messages)

    def test_mismatch_is_loud(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The exact production failure: asked for benchmark, booted default."""
        s = self._srv(
            tmp_path,
            "he-300-benchmark",
            "Successfully loaded template 'Ally' from /x/ciris_templates/default.yaml\n",
        )
        monkeypatch.chdir(tmp_path)
        assert s._verify_template_took_effect() is False
        assert any("TEMPLATE MISMATCH" in m for m in s.console.messages)

    def test_absent_line_is_unverified_not_ok(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._srv(tmp_path, "sage", "nothing useful here\n")
        monkeypatch.chdir(tmp_path)
        assert s._verify_template_took_effect() is False
        assert any("UNVERIFIED" in m for m in s.console.messages)

    def test_missing_log_is_unverified_not_ok(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._srv(tmp_path, "sage", None)
        monkeypatch.chdir(tmp_path)
        assert s._verify_template_took_effect() is False
        assert any("UNVERIFIED" in m for m in s.console.messages)

    def test_display_name_is_not_used_for_comparison(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`default.yaml` declares the name 'Ally' — comparing names never matches."""
        s = self._srv(
            tmp_path,
            "default",
            "Successfully loaded template 'Ally' from /x/ciris_templates/default.yaml\n",
        )
        monkeypatch.chdir(tmp_path)
        assert s._verify_template_took_effect() is True
