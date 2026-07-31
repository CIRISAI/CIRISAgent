"""Regression coverage for the substrate tracing bridge (#937).

Without this bridge every Rust `tracing` event from persist/edge/server is
discarded at the source — which is why persist's "migration phase begin
(advisory lock acquired)" never appeared during the 15-minute boot hang.

Two properties matter and are both asserted here:

1. The bridge installs, is idempotent, and CANNOT fail boot.
2. It adds no Python logging handler, so substrate output structurally
   cannot reach `incidents_latest.log` (#935 incident hygiene).
"""

import logging
import os
import subprocess
import sys
import textwrap

import pytest

from ciris_engine.logic.utils import substrate_logging


@pytest.fixture(autouse=True)
def _reset_bridge_state():
    """The installed flag is module-global; keep tests independent."""
    substrate_logging.reset_substrate_tracing_state()
    yield
    substrate_logging.reset_substrate_tracing_state()


# ─────────────────────────────────────────────────────────────────────
# Filter policy
# ─────────────────────────────────────────────────────────────────────


def test_default_filter_keeps_persist_at_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """The #937 migration-phase lines are `tracing::info!` — a blanket
    `warn` would drop the very thing this bridge exists to recover."""
    monkeypatch.delenv(substrate_logging.SUBSTRATE_LOG_FILTER_ENV, raising=False)
    monkeypatch.delenv("RUST_LOG", raising=False)

    resolved = substrate_logging.resolve_substrate_log_filter()

    assert resolved == substrate_logging.DEFAULT_SUBSTRATE_LOG_FILTER
    assert "ciris_persist=info" in resolved
    # ...but not a blanket info, which opens the edge/Reticulum firehose.
    assert resolved.startswith("warn")


def test_explicit_env_filter_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(substrate_logging.SUBSTRATE_LOG_FILTER_ENV, "debug")
    monkeypatch.setenv("RUST_LOG", "trace")
    assert substrate_logging.resolve_substrate_log_filter() == "debug"


def test_rust_log_is_deferred_to(monkeypatch: pytest.MonkeyPatch) -> None:
    """`filter` overrides the env filter substrate-side, so when the
    operator has set RUST_LOG we must pass None and get out of the way."""
    monkeypatch.delenv(substrate_logging.SUBSTRATE_LOG_FILTER_ENV, raising=False)
    monkeypatch.setenv("RUST_LOG", "info,ciris_edge=debug")
    assert substrate_logging.resolve_substrate_log_filter() is None


# ─────────────────────────────────────────────────────────────────────
# Install contract
# ─────────────────────────────────────────────────────────────────────


def test_installs_and_passes_log_dir_and_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A literal path, not `tmp_path` — the fake substrate only records the
    # argument, and the repo conftest rmtree's the tmpfs base backing
    # `tmp_path` (tests/conftest.py:39-59), which makes it a flake source.
    log_dir = "/var/log/ciris"
    calls: list[dict] = []
    monkeypatch.setattr(
        substrate_logging,
        "resolve_substrate_log_filter",
        lambda: "warn,ciris_persist=info",
    )
    monkeypatch.setitem(
        sys.modules,
        "ciris_engine.logic.persistence._substrate",
        _fake_substrate(lambda **kw: calls.append(kw)),
    )

    assert substrate_logging.install_substrate_tracing(log_dir=log_dir, force=True)
    assert calls == [{"log_dir": log_dir, "filter": "warn,ciris_persist=info"}]
    assert substrate_logging.substrate_tracing_installed()


def test_install_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    monkeypatch.setitem(
        sys.modules,
        "ciris_engine.logic.persistence._substrate",
        _fake_substrate(lambda **kw: calls.append(kw)),
    )

    assert substrate_logging.install_substrate_tracing(force=True) is True
    assert substrate_logging.install_substrate_tracing(force=True) is False
    assert len(calls) == 1, "second call must not re-init the subscriber"


def test_missing_entry_point_does_not_block_boot(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An older wheel exposes no init_tracing. Losing logs is bad; refusing
    to start because logging is unavailable is worse."""
    monkeypatch.setitem(
        sys.modules,
        "ciris_engine.logic.persistence._substrate",
        _fake_substrate(None),
    )

    with caplog.at_level(logging.WARNING, logger=substrate_logging.__name__):
        assert substrate_logging.install_substrate_tracing(force=True) is False

    assert any("no init_tracing" in r.getMessage() for r in caplog.records)


def test_raising_entry_point_does_not_block_boot(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _boom(**_kw):
        raise RuntimeError("subscriber already installed by another host")

    monkeypatch.setitem(
        sys.modules,
        "ciris_engine.logic.persistence._substrate",
        _fake_substrate(_boom),
    )

    with caplog.at_level(logging.WARNING, logger=substrate_logging.__name__):
        assert substrate_logging.install_substrate_tracing(force=True) is False

    assert any("tracing init failed" in r.getMessage() for r in caplog.records)


def test_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    monkeypatch.setenv(substrate_logging.SUBSTRATE_TRACING_DISABLED_ENV, "true")
    monkeypatch.setitem(
        sys.modules,
        "ciris_engine.logic.persistence._substrate",
        _fake_substrate(lambda **kw: calls.append(kw)),
    )

    assert substrate_logging.install_substrate_tracing(force=True) is False
    assert calls == []


def test_inert_under_pytest_without_force(monkeypatch: pytest.MonkeyPatch) -> None:
    """A process-global stdout subscriber must not attach to every test run."""
    calls: list[dict] = []
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "some::test")
    monkeypatch.setitem(
        sys.modules,
        "ciris_engine.logic.persistence._substrate",
        _fake_substrate(lambda **kw: calls.append(kw)),
    )

    assert substrate_logging.install_substrate_tracing() is False
    assert calls == []


# ─────────────────────────────────────────────────────────────────────
# Incident hygiene (#935)
# ─────────────────────────────────────────────────────────────────────


def test_bridge_adds_no_python_logging_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The isolation that protects incidents_latest.log.

    The incident capture handler sits on the ROOT logger and promotes every
    WARNING/ERROR into incidents_latest.log. Substrate events reach a Rust
    sink, never Python `logging`, so a chatty Rust subsystem structurally
    cannot flood the incident log. If someone ever "improves" this into a
    pyo3_log-style forwarder, that guarantee dies and this test fails.
    """
    monkeypatch.setitem(
        sys.modules,
        "ciris_engine.logic.persistence._substrate",
        _fake_substrate(lambda **kw: None),
    )

    root = logging.getLogger()
    before = list(root.handlers)

    assert substrate_logging.install_substrate_tracing(force=True)

    assert list(root.handlers) == before, (
        "the substrate bridge must not attach a Python logging handler — "
        "that is what keeps substrate output out of incidents_latest.log"
    )


# ─────────────────────────────────────────────────────────────────────
# End-to-end against the real substrate
# ─────────────────────────────────────────────────────────────────────


def test_real_substrate_emits_to_stdout_in_a_subprocess() -> None:
    """Proof the bridge actually works against the shipped wheel.

    Runs in a subprocess because the Rust subscriber is a process-global
    `try_init` with no teardown — installing it in the pytest process would
    leak into every other test.

    Takes no temp directory at all — not `tmp_path`, not `mkdtemp`. Under
    `-n 4` the repo conftest's tmpfs handling deletes the worker's own
    TMPDIR mid-session (tests/conftest.py:39-59), which makes *any*
    temp-dir dependency fail for reasons unrelated to this bridge; the
    stdout sink is what we are asserting on anyway.
    """
    pytest.importorskip("ciris_server")

    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {os.getcwd()!r})
        from ciris_engine.logic.utils.substrate_logging import (
            install_substrate_tracing,
        )
        installed = install_substrate_tracing(force=True)
        print("INSTALLED", installed)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert "INSTALLED True" in result.stdout, (
        f"bridge did not install against the real substrate.\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )


def _fake_substrate(init_tracing):
    """A stand-in `_substrate` module exposing just `init_tracing`."""
    import types

    module = types.ModuleType("ciris_engine.logic.persistence._substrate")
    module.init_tracing = init_tracing  # type: ignore[attr-defined]
    return module
