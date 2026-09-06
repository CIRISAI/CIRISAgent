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
    assert node_only.exec_into_node(node_only.NodeOnlyConfig(home="/h", key_id=None)) is True
    assert calls == [(sys.executable, [sys.executable, "-m", "ciris_server", "--headless", "--home", "/h"])]


def test_a_failed_exec_is_named_and_falls_through(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def _boom(path: str, argv: List[str]) -> None:
        raise OSError("exec format error")

    monkeypatch.setattr(os, "execv", _boom)
    assert node_only.exec_into_node(node_only.NodeOnlyConfig(home="/h", key_id="k")) is False
    err = capsys.readouterr().err
    assert "[RUN-WITHOUT-AI]" in err and "exec failed" in err and "next boot" in err


def test_run_desktop_starts_the_node_on_our_identity_then_the_client_then_tears_down(monkeypatch: pytest.MonkeyPatch) -> None:
    events: List[Any] = []

    class _Proc:
        pid = 4321

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


# --- the story is on stdout/stderr, greppable by one prefix -------------------


def test_the_decision_says_where_it_came_from_and_what_it_means(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv(node_only.ENV_FLAG, raising=False)
    monkeypatch.delenv(node_only.ENV_KEY_ID, raising=False)
    home = _home_with_env(tmp_path, "CIRIS_RUN_WITHOUT_AI=true\nCIRIS_NODE_KEY_ID=alias-1\n")
    cfg = node_only.node_only_config(home)
    assert cfg is not None and cfg.source == str(tmp_path / ".env")
    out = capsys.readouterr()
    assert "[RUN-WITHOUT-AI] the owner chose to run without AI" in out.out
    assert f"decided_by={tmp_path / '.env'}" in out.out and "key_id=alias-1" in out.out and "node_logs=" in out.out
    assert out.err == "", "nothing is wrong, so nothing on stderr"


def test_a_missing_alias_is_shouted_on_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv(node_only.ENV_FLAG, raising=False)
    monkeypatch.delenv(node_only.ENV_KEY_ID, raising=False)
    home = _home_with_env(tmp_path, "CIRIS_RUN_WITHOUT_AI=true\n")
    assert node_only.node_only_config(home) is not None
    err = capsys.readouterr().err
    assert "CIRIS_NODE_KEY_ID" in err and "NOT the identity the wizard claimed" in err


def test_the_environment_veto_is_explained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    home = _home_with_env(tmp_path, "CIRIS_RUN_WITHOUT_AI=true\n")
    monkeypatch.setenv(node_only.ENV_FLAG, "false")
    assert node_only.node_only_config(home) is None
    assert "overrides" in capsys.readouterr().out


def test_silence_when_nobody_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv(node_only.ENV_FLAG, raising=False)
    home = _home_with_env(tmp_path, "CIRIS_CONFIGURED=true\n")
    assert node_only.node_only_config(home) is None
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_a_missing_wheel_exits_2_with_the_pip_line(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setitem(sys.modules, "ciris_server", None)  # import raises ImportError
    with pytest.raises(SystemExit) as exc:
        node_only.run_headless(node_only.NodeOnlyConfig(home="/h", key_id="k"))
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "pip install ciris-server" in err and "CIRIS_RUN_WITHOUT_AI=false" in err


def test_run_desktop_narrates_each_step(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    class _Proc:
        pid = 99

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float = 0) -> int:
            return 0

    fake_cli = SimpleNamespace(_spawn_headless_node=lambda args: _Proc(), _wait_for_node_health=lambda url, proc, timeout=60.0: True)
    fake_launcher = SimpleNamespace(launch_desktop_app=lambda server_url: 0)
    monkeypatch.setitem(sys.modules, "ciris_server", SimpleNamespace(cli=fake_cli, desktop_launcher=fake_launcher))
    monkeypatch.setitem(sys.modules, "ciris_server.cli", fake_cli)
    monkeypatch.setitem(sys.modules, "ciris_server.desktop_launcher", fake_launcher)
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert node_only.run_desktop(node_only.NodeOnlyConfig(home="/h", key_id="k")) == 0
    out = capsys.readouterr().out
    for phrase in ("starting the node as a child", "node pid=99", "read API is up", "launching the desktop client against http://localhost:4243", "desktop client exited with code 0", "node stopped"):
        assert phrase in out, phrase


# --- the two sides must agree about the flag, and disagreement must be loud ----


@pytest.mark.parametrize("value", ["true", "TRUE", "True", "1", "yes", "YES", '"true"', " true "])
def test_every_truthy_spelling_the_client_accepts_is_accepted_here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.delenv(node_only.ENV_FLAG, raising=False)
    home = _home_with_env(tmp_path, f"CIRIS_RUN_WITHOUT_AI={value}\n")
    assert node_only.node_only_config(home) is not None, f"{value!r} must mean true on both sides"


@pytest.mark.parametrize("value", ["on", "ON", "enabled", "y", "t", ""])
def test_spellings_the_client_does_not_accept_are_not_accepted_here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """A value one side takes and the other does not is a dead app: agent on one port, client on the other."""
    monkeypatch.delenv(node_only.ENV_FLAG, raising=False)
    home = _home_with_env(tmp_path, f"CIRIS_RUN_WITHOUT_AI={value}\n")
    assert node_only.node_only_config(home) is None, f"{value!r} is not truthy for the client, so it must not be truthy here"


def test_an_environment_veto_warns_that_the_client_will_look_elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    home = _home_with_env(tmp_path, "CIRIS_RUN_WITHOUT_AI=true\n")
    monkeypatch.setenv(node_only.ENV_FLAG, "false")
    assert node_only.node_only_config(home) is None
    err = capsys.readouterr().err
    assert "will serve :8080" in err and "look for :4243" in err and "no client attached" in err


def test_an_environment_opt_in_warns_the_same_way(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    home = _home_with_env(tmp_path, "CIRIS_CONFIGURED=true\n")
    monkeypatch.setenv(node_only.ENV_FLAG, "true")
    assert node_only.node_only_config(home) is not None
    err = capsys.readouterr().err
    assert "will serve :4243" in err and "look for :8080" in err
