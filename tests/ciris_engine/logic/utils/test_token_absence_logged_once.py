"""'No proxy token' warns once per absence, not once per billing check.

read_proxy_token runs on every message's billing check. With no proxy token
(a node on its own LLM key, or any QA run) it logged the same WARNING each
time: 50 in one QA session, which tripped the incidents gate's WARNING-flood
check (run 39684260533).
"""

import io
import logging

import pytest

from ciris_engine.logic.utils import token_handshake as th
from ciris_engine.logic.utils.log_dedup import RepeatCollapsingFilter


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(th, "_absence_reported", False)
    for var in th.PROXY_TOKEN_VARS:
        monkeypatch.delenv(var, raising=False)


def _warnings(caplog):
    """The warnings read_proxy_token itself raised.

    Matched on the emitting function, not just the text. A handler carrying
    RepeatCollapsingFilter (setup_basic_logging installs two, and an earlier
    test in the same xdist worker can leave one behind) re-logs a held streak
    as "<same text>  [repeated N more times]" through this same logger. That
    summary is the dedup filter's line, not a second warning from here, and
    counting it made this file fail on main depending on test order.
    """
    return [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and r.funcName == "read_proxy_token" and "no proxy token" in r.getMessage()
    ]


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


def test_count_ignores_the_dedup_filters_summary(caplog, monkeypatch):
    """A leaked repeat-collapsing handler must not change the count.

    Reproduces the main failure: with such a handler listening at DEBUG, the
    second WARNING is held as a repeat and the DEBUG line that follows flushes
    it as a summary record carrying the same text.
    """
    # Not NullHandler: its handle() is a no-op, so its filters never run.
    leaked = logging.StreamHandler(io.StringIO())
    leaked.setLevel(logging.DEBUG)
    leaked.addFilter(RepeatCollapsingFilter())
    th.logger.addHandler(leaked)
    try:
        test_absence_after_a_token_warns_again(caplog, monkeypatch)
        summaries = [r for r in caplog.records if "repeated" in r.getMessage()]
        assert len(summaries) == 1, "the leaked handler did not produce the summary this test guards against"
    finally:
        th.logger.removeHandler(leaked)
