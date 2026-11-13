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
