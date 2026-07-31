"""Regression coverage for #937 — bounded, loud database init.

The failure being locked down: agent boot blocked for 15 minutes inside
persist's Engine constructor (connect + migrations) on a shared Postgres,
logging nothing, while docker reported the container running.

What must hold forever after:

* the bootstrap is wall-clock bounded and raises with diagnostics
* it logs progress while it waits (silence is the bug)
* Postgres startup connections carry `lock_timeout` / `statement_timeout`
* SQLite connections carry neither
* nothing ever logs a raw DSN (they carry passwords)
"""

import logging
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from ciris_engine.logic.persistence.db import core


# ─────────────────────────────────────────────────────────────────────
# DSN redaction
# ─────────────────────────────────────────────────────────────────────


def test_redact_dsn_strips_password() -> None:
    redacted = core._redact_dsn("postgresql://ciris:hunter2@db.host:5432/ciris_db")
    assert "hunter2" not in redacted
    assert redacted == "postgresql://ciris:***@db.host:5432/ciris_db"


def test_redact_dsn_drops_query_string() -> None:
    """The query string can carry credentials too (e.g. sslpassword)."""
    redacted = core._redact_dsn("postgresql://u:p@h/db?sslpassword=secret")
    assert "secret" not in redacted
    assert "?" not in redacted


def test_redact_dsn_passes_sqlite_through() -> None:
    assert core._redact_dsn("sqlite:////var/lib/ciris/engine.db") == (
        "sqlite:////var/lib/ciris/engine.db"
    )


# ─────────────────────────────────────────────────────────────────────
# Startup session timeouts — Postgres only
# ─────────────────────────────────────────────────────────────────────


def test_lock_timeout_applied_for_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(core.DB_INIT_LOCK_TIMEOUT_ENV, raising=False)
    monkeypatch.delenv(core.DB_INIT_STATEMENT_TIMEOUT_ENV, raising=False)

    dsn = core._with_startup_timeouts("postgresql://ciris:pw@db:5432/ciris_db")
    options = parse_qs(urlsplit(dsn).query)["options"][0]

    assert options == f"-c lock_timeout={core.DB_INIT_LOCK_TIMEOUT_DEFAULT}"


def test_options_are_percent_encoded_never_form_encoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`+` must never appear — it is the whole ballgame.

    tokio-postgres decodes URL query values with `percent_decode` only
    (tokio-postgres config.rs:1162), so a form-encoded space would arrive
    at the server as a literal `+` and corrupt the options string into
    `-c+lock_timeout=120s`, which Postgres rejects.
    """
    monkeypatch.setenv(core.DB_INIT_LOCK_TIMEOUT_ENV, "30s")
    monkeypatch.setenv(core.DB_INIT_STATEMENT_TIMEOUT_ENV, "600s")

    dsn = core._with_startup_timeouts("postgresql://ciris:pw@db:5432/ciris_db")

    assert "+" not in dsn
    assert "%20" in dsn
    assert parse_qs(urlsplit(dsn).query)["options"][0] == (
        "-c lock_timeout=30s -c statement_timeout=600s"
    )


def test_statement_timeout_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(core.DB_INIT_LOCK_TIMEOUT_ENV, raising=False)
    monkeypatch.delenv(core.DB_INIT_STATEMENT_TIMEOUT_ENV, raising=False)

    assert core.DB_INIT_STATEMENT_TIMEOUT_DEFAULT == "0"
    assert "statement_timeout" not in core._with_startup_timeouts(
        "postgresql://ciris:pw@db/ciris_db"
    )


@pytest.mark.parametrize(
    "sqlite_dsn",
    [
        "sqlite:////var/lib/ciris/engine.db",
        "sqlite:///relative/engine.db",
        "sqlite::memory:",
    ],
)
def test_timeouts_never_applied_for_sqlite(
    sqlite_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SQLite has no session GUCs; persist would reject the parameter."""
    monkeypatch.setenv(core.DB_INIT_LOCK_TIMEOUT_ENV, "30s")
    monkeypatch.setenv(core.DB_INIT_STATEMENT_TIMEOUT_ENV, "600s")

    assert core._with_startup_timeouts(sqlite_dsn) == sqlite_dsn


def test_bare_sqlite_path_resolution_carries_no_options(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(core.DB_INIT_LOCK_TIMEOUT_ENV, "30s")
    dsn, _sentinel = core._persist_dsn_and_sentinel(str(tmp_path / "engine.db"))
    assert "options" not in dsn


def test_operator_supplied_options_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(core.DB_INIT_LOCK_TIMEOUT_ENV, "30s")
    original = "postgresql://u:p@h/db?options=-c%20lock_timeout%3D1s"
    assert core._with_startup_timeouts(original) == original


def test_existing_query_params_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(core.DB_INIT_LOCK_TIMEOUT_ENV, "30s")
    monkeypatch.delenv(core.DB_INIT_STATEMENT_TIMEOUT_ENV, raising=False)

    dsn = core._with_startup_timeouts("postgresql://u:p@h/db?sslmode=require")
    query = parse_qs(urlsplit(dsn).query)

    assert query["sslmode"] == ["require"]
    assert query["options"] == ["-c lock_timeout=30s"]


def test_zero_disables_both_knobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(core.DB_INIT_LOCK_TIMEOUT_ENV, "0")
    monkeypatch.setenv(core.DB_INIT_STATEMENT_TIMEOUT_ENV, "0")
    original = "postgresql://u:p@h/db"
    assert core._with_startup_timeouts(original) == original


def test_dsn_resolution_is_stable_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The idempotent-skip in `_bootstrap_persist_engine` and persist's
    process-singleton fingerprint both compare DSN strings. If the options
    decoration were non-deterministic, a second `initialize_database()`
    call in one process would trip `EngineConfigMismatch`.
    """
    monkeypatch.setenv(core.DB_INIT_LOCK_TIMEOUT_ENV, "45s")
    url = "postgresql://ciris:pw@db:5432/ciris_db"
    first, _ = core._persist_dsn_and_sentinel(url)
    second, _ = core._persist_dsn_and_sentinel(url)
    assert first == second
    assert "lock_timeout" in first


# ─────────────────────────────────────────────────────────────────────
# Wall-clock budget
# ─────────────────────────────────────────────────────────────────────


def test_timeout_budget_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(core.DB_INIT_TIMEOUT_ENV, raising=False)
    assert core._db_init_timeout_seconds() == core.DB_INIT_TIMEOUT_SECONDS_DEFAULT

    monkeypatch.setenv(core.DB_INIT_TIMEOUT_ENV, "42")
    assert core._db_init_timeout_seconds() == 42.0

    monkeypatch.setenv(core.DB_INIT_TIMEOUT_ENV, "not-a-number")
    assert core._db_init_timeout_seconds() == core.DB_INIT_TIMEOUT_SECONDS_DEFAULT


@pytest.fixture
def fast_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the #937 bounds so a simulated hang resolves in test time."""
    monkeypatch.setenv(core.DB_INIT_TIMEOUT_ENV, "0.3")
    monkeypatch.setattr(core, "DB_INIT_PROGRESS_INTERVAL_SECONDS", 0.05)


def test_simulated_hang_times_out_instead_of_hanging(
    fast_bounds: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blocked bootstrap raises — it does not hang the caller."""
    release = threading.Event()
    monkeypatch.setattr(core, "_blocker_hint", lambda dsn: " HINT.")

    def _hang() -> object:
        release.wait(timeout=30)
        return object()

    started = time.monotonic()
    try:
        with pytest.raises(core.DatabaseInitializationTimeout) as excinfo:
            core._construct_engine_bounded(
                _hang, "postgresql://ciris:hunter2@db.host:5432/ciris_db"
            )
    finally:
        release.set()

    assert time.monotonic() - started < 10, "the bound must actually bound"

    message = str(excinfo.value)
    # Names the phase + budget + elapsed
    assert "persist Engine construction exceeded" in message
    assert "elapsed" in message
    # Names the target, credentials redacted
    assert "db.host:5432/ciris_db" in message
    assert "hunter2" not in message
    # Carries the diagnostic and the escape hatch
    assert "HINT." in message
    assert core.DB_INIT_TIMEOUT_ENV in message


def test_simulated_hang_emits_progress_logs(
    fast_bounds: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """15 minutes of silence must be impossible."""
    release = threading.Event()
    monkeypatch.setattr(core, "_blocker_hint", lambda dsn: "")

    def _hang() -> object:
        release.wait(timeout=30)
        return object()

    with caplog.at_level(logging.WARNING, logger=core.__name__):
        try:
            with pytest.raises(core.DatabaseInitializationTimeout):
                core._construct_engine_bounded(
                    _hang, "postgresql://ciris:hunter2@db.host:5432/ciris_db"
                )
        finally:
            release.set()

    progress = [r for r in caplog.records if "phase=engine-construct" in r.getMessage()]
    assert progress, "no progress log emitted while the bootstrap was blocked"
    rendered = progress[0].getMessage()
    assert "still running after" in rendered
    assert "hunter2" not in rendered
    # The operator needs to recognise the shared-database shape immediately.
    assert "advisory lock" in rendered


def test_blocker_hint_names_the_diagnostic_query() -> None:
    """Production ships no Postgres driver, so the hint must at minimum
    hand the operator the exact query to run."""
    hint = core._blocker_hint("postgresql://u:p@127.0.0.1:1/definitely_not_a_db")
    assert "pg_stat_activity" in hint
    assert "pg_blocking_pids" in hint


def test_blocker_hint_is_empty_for_sqlite() -> None:
    assert core._blocker_hint("sqlite:////tmp/engine.db") == ""


def test_bounded_construction_returns_the_engine() -> None:
    sentinel = object()
    assert core._construct_engine_bounded(lambda: sentinel, "sqlite::memory:") is sentinel


def test_bounded_construction_reraises_worker_exception() -> None:
    def _boom() -> object:
        raise RuntimeError("connect: could not translate host name")

    with pytest.raises(RuntimeError, match="could not translate host name"):
        core._construct_engine_bounded(_boom, "postgresql://u:p@h/db")


def test_non_positive_budget_disables_the_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Escape hatch for an operator with a genuinely multi-hour migration."""
    monkeypatch.setenv(core.DB_INIT_TIMEOUT_ENV, "0")
    monkeypatch.setattr(core, "DB_INIT_PROGRESS_INTERVAL_SECONDS", 0.02)

    slow = threading.Event()

    def _slow() -> str:
        slow.wait(timeout=0.1)
        return "engine"

    assert core._construct_engine_bounded(_slow, "sqlite::memory:") == "engine"


# ─────────────────────────────────────────────────────────────────────
# initialize_database phase logging + failure propagation
# ─────────────────────────────────────────────────────────────────────


def test_initialize_database_logs_phase_begin_and_complete(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(core, "_bootstrap_persist_engine", lambda db_path: None)
    # Bound to a name so the caller-stack dump (which renders source lines)
    # does not itself contain the literal password.
    dsn = "postgresql://ciris:hunter2@db.host:5432/ciris_db"

    with caplog.at_level(logging.INFO, logger=core.__name__):
        core.initialize_database(dsn)

    messages = [r.getMessage() for r in caplog.records]
    assert any("phase=bootstrap begin" in m for m in messages)
    assert any("phase=bootstrap complete" in m for m in messages)
    assert any("elapsed=" in m for m in messages)
    assert not any("hunter2" in m for m in messages), "DSN password leaked to logs"


def test_initialize_database_propagates_timeout(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The DATABASE init phase must FAIL, not pretend to boot."""

    def _timeout(db_path: str) -> None:
        raise core.DatabaseInitializationTimeout("simulated shared-DB lock wait")

    monkeypatch.setattr(core, "_bootstrap_persist_engine", _timeout)
    dsn = "postgresql://ciris:hunter2@db.host:5432/ciris_db"

    with caplog.at_level(logging.ERROR, logger=core.__name__):
        with pytest.raises(core.DatabaseInitializationTimeout):
            core.initialize_database(dsn)

    messages = [r.getMessage() for r in caplog.records]
    assert any("phase=bootstrap FAILED" in m for m in messages)
    assert not any("hunter2" in m for m in messages)


def test_timeout_is_a_timeout_error() -> None:
    """Callers (and the initialization service) may catch TimeoutError."""
    assert issubclass(core.DatabaseInitializationTimeout, TimeoutError)


def test_timeout_is_not_retried_by_the_stale_lockfile_heuristic(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A timeout must never be misread as a stale lockfile.

    The iOS stale-lockfile retry in `_bootstrap_persist_engine` is a
    substring match on "lock", and the timeout message says "blocked" /
    "pg_blocking_pids" — both of which CONTAIN "lock". Without the
    dedicated `except DatabaseInitializationTimeout: raise` clause ordered
    first, a timeout would be retried, doubling the outage. Assert the
    constructor is attempted exactly once.
    """
    from ciris_engine.logic.persistence.models import graph as graph_persistence

    # Force the iOS branch — that is the only arm where the heuristic can fire.
    monkeypatch.setattr(core.sys, "platform", "ios")

    attempts: list[str] = []

    def _always_timeout(construct, dsn, bump_stack=False):  # type: ignore[no-untyped-def]
        attempts.append(dsn)
        raise core.DatabaseInitializationTimeout(
            "the agent is blocked in persist's connect + migration phase; "
            "run pg_blocking_pids(...)"
        )

    monkeypatch.setattr(core, "_construct_engine_bounded", _always_timeout)

    prev_engine = graph_persistence._engine
    prev_dsn = graph_persistence._engine_dsn
    try:
        with pytest.raises(core.DatabaseInitializationTimeout):
            core._bootstrap_persist_engine(str(tmp_path / "engine.db"))
    finally:
        graph_persistence._engine = prev_engine
        graph_persistence._engine_dsn = prev_dsn

    assert len(attempts) == 1, f"timeout was retried: {attempts}"
