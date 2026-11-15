"""A fresh-home harness node's identities carry a signed end (ciris-server >= 0.5.247)."""

import inspect

from tools.qa_runner import server
from tools.qa_runner.run_kind import (
    HARNESS_IDENTITY_TTL_S,
    IDENTITY_TTL_ENV_VAR,
    MIN_IDENTITY_TTL_S,
    declare_identity_ttl,
)


def test_fresh_home_gets_the_harness_ttl():
    env = {}
    assert declare_identity_ttl(env, fresh_home=True) is None
    assert env[IDENTITY_TTL_ENV_VAR] == str(HARNESS_IDENTITY_TTL_S)


def test_reused_home_gets_no_end():
    env = {}
    assert declare_identity_ttl(env, fresh_home=False) is None
    assert IDENTITY_TTL_ENV_VAR not in env


def test_explicit_valid_ttl_is_kept():
    env = {IDENTITY_TTL_ENV_VAR: str(MIN_IDENTITY_TTL_S)}
    assert declare_identity_ttl(env, fresh_home=True) is None
    assert env[IDENTITY_TTL_ENV_VAR] == str(MIN_IDENTITY_TTL_S)


def test_below_minimum_or_garbage_is_replaced_with_warning():
    for bad in (str(MIN_IDENTITY_TTL_S - 1), "0", "a day"):
        env = {IDENTITY_TTL_ENV_VAR: bad}
        warning = declare_identity_ttl(env, fresh_home=True)
        assert warning and IDENTITY_TTL_ENV_VAR in warning
        assert env[IDENTITY_TTL_ENV_VAR] == str(HARNESS_IDENTITY_TTL_S)


def test_qa_runner_launch_declares_it_from_wipe_data():
    source = inspect.getsource(server)
    assert "declare_identity_ttl(env, fresh_home=bool(self.config.wipe_data))" in source


class _Launched(Exception):
    pass


def _desktop_backend_env(monkeypatch, tmp_path, **cfg):
    """The env the web_ui ServerManager hands the desktop backend (the node, on the no-AI answer)."""
    from tools.qa_runner.modules.web_ui import server_manager as sm

    seen = {}

    def _popen(*_a, **kw):
        seen.update(kw["env"])
        raise _Launched

    monkeypatch.delenv(IDENTITY_TTL_ENV_VAR, raising=False)
    monkeypatch.setenv("CIRIS_HOME", str(tmp_path))
    monkeypatch.setattr(sm.subprocess, "Popen", _popen)
    manager = sm.ServerManager(sm.ServerConfig(project_root=str(tmp_path), wipe_data=False, **cfg))
    monkeypatch.setattr(manager, "is_running", lambda: False)
    try:
        manager.start()
    except _Launched:
        pass
    return seen


def test_desktop_backend_on_a_home_this_run_wiped_gets_the_ttl(monkeypatch, tmp_path):
    env = _desktop_backend_env(monkeypatch, tmp_path, run_home=True)
    assert env[IDENTITY_TTL_ENV_VAR] == str(HARNESS_IDENTITY_TTL_S)


def test_desktop_backend_on_a_kept_home_gets_no_end(monkeypatch, tmp_path):
    env = _desktop_backend_env(monkeypatch, tmp_path)
    assert env and IDENTITY_TTL_ENV_VAR not in env


def test_every_desktop_bring_up_that_wipes_marks_its_run_home():
    from tools.qa_runner.modules.web_ui import __main__ as web_ui

    for fn in (web_ui.run_desktop_up, web_ui.run_desktop_first_run_up):
        source = inspect.getsource(fn)
        assert "_wipe_dev_data()" in source
        assert source.count("ServerConfig(") == source.count("run_home=True")
