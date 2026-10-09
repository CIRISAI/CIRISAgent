"""The QA runner refuses a remote trace sink under the mock LLM (CIRISAgent#1244).

Mock is the runner's default (no --live, no --no-mock-llm), so ``--live-lens``
or ``--federation-delivery`` on their own are mock-LLM runs that ask for the
production lens or canonical. That must fail before anything is wiped or
started, with a message that says why.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

from tools.qa_runner.__main__ import trace_sink_flag_error

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "mock,live_lens,fed,refused",
    [
        (True, True, False, True),
        (True, False, True, True),
        (True, True, True, True),
        (True, False, False, False),
        (False, True, False, False),
        (False, True, True, False),
    ],
)
def test_flag_matrix(mock: bool, live_lens: bool, fed: bool, refused: bool) -> None:
    error = trace_sink_flag_error(mock, live_lens, fed)
    assert (error is not None) is refused
    if error:
        assert "CIRISAgent#1244" in error and "mock LLM" in error


@pytest.mark.parametrize(
    "argv",
    [
        ["auth", "--live-lens"],
        ["auth", "--mock-llm", "--live-lens"],
        ["auth", "--federation-delivery"],
    ],
)
def test_cli_exits_before_doing_anything(tmp_path: Path, argv: List[str]) -> None:
    # Run from an empty dir so a regression that got past the check could not
    # wipe or touch the checkout's data/ directory.
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    proc = subprocess.run(
        [sys.executable, "-m", "tools.qa_runner", *argv],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 2, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert "cannot be combined with the mock LLM" in proc.stdout
    assert list(tmp_path.iterdir()) == []


def test_mock_llm_flag_conflicts_with_live(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    proc = subprocess.run(
        [sys.executable, "-m", "tools.qa_runner", "auth", "--mock-llm", "--no-mock-llm"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 2
    assert "--mock-llm conflicts" in proc.stdout


class _Reached(Exception):
    """Raised by the stand-in runner: main() got past every flag check."""


def test_auto_live_module_is_not_rejected_as_mock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex P2: a REQUIRES_LIVE_LLM module auto-enables --live, so --live-lens is legitimate."""
    import tools.qa_runner.__main__ as qa_main
    from tools.qa_runner.modules import _module_metadata

    key = tmp_path / "key"
    key.write_text("not-a-real-key")
    defaults = {"key_file": str(key), "base_url": "http://127.0.0.1:9/v1", "model": "m", "provider": "openai"}
    monkeypatch.setattr(
        _module_metadata,
        "get_metadata",
        lambda _m: _module_metadata.ModuleMetadata(requires_live_llm=True, live_llm_defaults=defaults),
    )

    class _Runner:
        def __init__(self, *_: object, **__: object) -> None:
            raise _Reached()

    monkeypatch.setattr(qa_main, "QARunner", _Runner)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["qa_runner", "auth", "--live-lens"])
    with pytest.raises(_Reached):
        qa_main.main()


def test_mock_llm_flag_refuses_an_auto_live_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.qa_runner.__main__ as qa_main
    from tools.qa_runner.modules import _module_metadata

    monkeypatch.setattr(
        _module_metadata, "get_metadata", lambda _m: _module_metadata.ModuleMetadata(requires_live_llm=True)
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["qa_runner", "auth", "--mock-llm"])
    with pytest.raises(SystemExit) as exc:
        qa_main.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("live_lens,fed", [(True, False), (False, True)])
@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_programmatic_config_is_refused_before_any_side_effect(
    monkeypatch: pytest.MonkeyPatch, live_lens: bool, fed: bool, backend: str
) -> None:
    """Codex P2: QAConfig(mock_llm=True, live_lens=True) must touch nothing."""
    from tools.qa_runner import server as server_mod
    from tools.qa_runner.config import QAConfig

    touched: List[str] = []

    def _record(name: str):  # type: ignore[no-untyped-def]
        return lambda *a, **k: touched.append(name) or True

    monkeypatch.setattr(server_mod, "_ensure_env_file", _record("env_file"))
    monkeypatch.setattr(server_mod, "_start_postgres_container", _record("postgres"))
    monkeypatch.setattr(server_mod, "_wipe_postgres_databases", _record("wipe_postgres"))
    manager = server_mod.APIServerManager(
        QAConfig(mock_llm=True, live_lens=live_lens, federation_delivery=fed, wipe_data=True), database_backend=backend
    )
    for method in ("_is_server_running", "_clear_trace_files", "_clear_wakeup_state"):
        monkeypatch.setattr(manager, method, _record(method))

    assert manager.start() is False
    assert touched == []
