"""'No proxy token' warns once per absence, not once per billing check.

read_proxy_token runs on every message's billing check. With no proxy token
(a node on its own LLM key, or any QA run) it logged the same WARNING each
time: 50 in one QA session, which tripped the incidents gate's WARNING-flood
check (run 39684260533).
"""

import logging

import pytest

from ciris_engine.logic.utils import token_handshake as th


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(th, "_absence_reported", False)
    for var in th.PROXY_TOKEN_VARS:
        monkeypatch.delenv(var, raising=False)


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno == logging.WARNING and "no proxy token" in r.getMessage()]


def test_absence_warns_once(caplog):
    with caplog.at_level(logging.DEBUG, logger=th.logger.name):
        for _ in range(60):
            assert th.read_proxy_token() == ("", "")
    assert len(_warnings(caplog)) == 1


def test_absence_after_a_token_warns_again(caplog, monkeypatch):
    var = th.PROXY_TOKEN_VARS[0]
    with caplog.at_level(logging.DEBUG, logger=th.logger.name):
        th.read_proxy_token()
        monkeypatch.setenv(var, "opaque-token")
        assert th.read_proxy_token()[0] == "opaque-token"
        monkeypatch.delenv(var)
        th.read_proxy_token()
        th.read_proxy_token()
    assert len(_warnings(caplog)) == 2
