"""Run without AI: the process is ciris-server and the client, nothing else (CIRISAgent#1149)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import patch

import pytest

from ciris_engine import node_only


def _home_with_env(tmp_path: Path, text: str) -> str:
    (tmp_path / ".env").write_text(text)
    return str(tmp_path)


def test_no_flag_means_no_node_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(node_only.ENV_FLAG, raising=False)
    home = _home_with_env(tmp_path, "CIRIS_CONFIGURED=true\nCIRIS_SERVICES_DISABLED=true\n")
    assert node_only.node_only_config(home) is None, "services-disabled alone is a degraded brain, not a node-only boot"


def test_the_wizard_flag_selects_node_only_with_the_claimed_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(node_only.ENV_FLAG, raising=False)
    monkeypatch.delenv(node_only.ENV_KEY_ID, raising=False)
    home = _home_with_env(tmp_path, 'CIRIS_CONFIGURED=true\nCIRIS_RUN_WITHOUT_AI="true"\nCIRIS_NODE_KEY_ID=ciris-agent-bootstrap\n')
    cfg = node_only.node_only_config(home)
    assert cfg is not None and cfg.home == home and cfg.key_id == "ciris-agent-bootstrap"
    assert cfg.node_args() == ["--home", home, "--key-id", "ciris-agent-bootstrap"]
    assert cfg.server_url == "http://localhost:4243"


def test_the_environment_overrides_the_file_both_ways(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = _home_with_env(tmp_path, "CIRIS_RUN_WITHOUT_AI=true\n")
    monkeypatch.setenv(node_only.ENV_FLAG, "false")
    assert node_only.node_only_config(home) is None, "an operator can bring the brain back for one run"
    home2 = _home_with_env(tmp_path / "b", "CIRIS_CONFIGURED=true\n") if (tmp_path / "b").mkdir() is None else ""
    monkeypatch.setenv(node_only.ENV_FLAG, "1")
    cfg = node_only.node_only_config(home2)
    assert cfg is not None and cfg.key_id is None and cfg.node_args() == ["--home", home2]


def test_env_file_parser_skips_noise_and_strips_quotes(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("# comment\n\nA=1\nB='two'\nC=\"three=3\"\nnot a pair\n =x\n")
    assert node_only.read_env_file(str(p)) == {"A": "1", "B": "two", "C": "three=3"}
    assert node_only.read_env_file(str(tmp_path / "missing")) == {}


def test_node_command_is_the_wheel_module_with_our_home_and_key() -> None:
    cfg = node_only.NodeOnlyConfig(home="/h", key_id="k")
    assert node_only.node_command(cfg) == [sys.executable, "-m", "ciris_server", "--headless", "--home", "/h", "--key-id", "k"]


def test_run_headless_hands_argv_to_the_wheel_and_never_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: List[List[str]] = []
    fake_cli = SimpleNamespace(main=lambda: seen.append(list(sys.argv)))
    monkeypatch.setitem(sys.modules, "ciris_server", SimpleNamespace(cli=fake_cli))
    monkeypatch.setitem(sys.modules, "ciris_server.cli", fake_cli)
    with pytest.raises(SystemExit):
        node_only.run_headless(node_only.NodeOnlyConfig(home="/h", key_id="k"))
    assert seen == [["ciris-server", "--headless", "--home", "/h", "--key-id", "k"]]


def test_exec_into_node_replaces_the_process_with_the_node(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Any] = []
    monkeypatch.setattr(os, "execv", lambda path, argv: calls.append((path, argv)))
    node_only.exec_into_node(node_only.NodeOnlyConfig(home="/h", key_id=None))
    assert calls == [(sys.executable, [sys.executable, "-m", "ciris_server", "--headless", "--home", "/h"])]


def test_run_desktop_starts_the_node_on_our_identity_then_the_client_then_tears_down(monkeypatch: pytest.MonkeyPatch) -> None:
    events: List[Any] = []

    class _Proc:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            events.append("terminate")

        def wait(self, timeout: float = 0) -> int:
            events.append("wait")
            return 0

        def kill(self) -> None:
            events.append("kill")

    fake_cli = SimpleNamespace(
        _spawn_headless_node=lambda args: (events.append(("spawn", list(args))), _Proc())[1],
        _wait_for_node_health=lambda url, proc, timeout=60.0: (events.append(("health", url)), True)[1],
    )
    fake_launcher = SimpleNamespace(launch_desktop_app=lambda server_url: (events.append(("client", server_url)), 0)[1])
    monkeypatch.setitem(sys.modules, "ciris_server", SimpleNamespace(cli=fake_cli, desktop_launcher=fake_launcher))
    monkeypatch.setitem(sys.modules, "ciris_server.cli", fake_cli)
    monkeypatch.setitem(sys.modules, "ciris_server.desktop_launcher", fake_launcher)
    monkeypatch.setattr("time.sleep", lambda s: None)
    rc = node_only.run_desktop(node_only.NodeOnlyConfig(home="/h", key_id="k"))
    assert rc == 0
    assert events == [
        ("spawn", ["--home", "/h", "--key-id", "k"]),
        ("health", "http://localhost:4243"),
        ("client", "http://localhost:4243"),
        "terminate",
        "wait",
    ]
