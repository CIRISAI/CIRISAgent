"""The CEG seal-tee is opt-in, and its default-off state is load-bearing.

`_tee_ceg_on_seal` reads the sealed carriers by opening a SECOND SQLite
connection — Python's `sqlite3` — against the database the Rust persist
engine already holds open for writing, inside the same process. Those are
two independently-linked copies of the SQLite library, and WAL's
shared-memory index assumes one per process. Staged QA reproduced the
consequence twice: the sqlite leg died mid-log-line inside the 7th tee with
no traceback, taking the API server with it and failing 55 downstream tests,
while the postgres leg — where the connect fails fast because there is no
SQLite file to open — ran clean to 45 seals.

The trigger was that the tee rode along on `local_copy_dir`, which the QA
runner sets on EVERY run (accord_metrics_tests reads the lens-batch files it
governs). That var means "tee the batches lens-core hands us" — a pure
write. Reading the live persist DB is a different act and now needs its own
opt-in, which only tools/research/capture_traces.sh sets.

So: local_copy_dir alone must NOT be enough to open that second handle.
"""

from typing import Any, Dict, Optional

import pytest

from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

TEE_ENV = "CIRIS_ACCORD_METRICS_CEG_SEAL_TEE"
COPY_DIR_ENV = "CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR"


def _svc(config: Optional[Dict[str, Any]] = None) -> AccordMetricsService:
    base: Dict[str, Any] = {
        "consent_given": True,
        "consent_timestamp": "2026-01-01T00:00:00Z",
        "trace_level": "generic",
    }
    base.update(config or {})
    svc = AccordMetricsService(config=base)
    svc._agent_id_hash = "testhash0000000"
    return svc


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither knob leaks in from the ambient environment."""
    monkeypatch.delenv(TEE_ENV, raising=False)
    monkeypatch.delenv(COPY_DIR_ENV, raising=False)
    monkeypatch.delenv("CIRIS_COVENANT_METRICS_CEG_SEAL_TEE", raising=False)
    monkeypatch.delenv("CIRIS_COVENANT_METRICS_LOCAL_COPY_DIR", raising=False)


class TestCegSealTeeGate:
    def test_off_by_default(self) -> None:
        assert _svc()._ceg_seal_tee_enabled is False

    def test_local_copy_dir_alone_does_not_enable_it(self, tmp_path, monkeypatch) -> None:
        """The regression itself: the QA runner sets this on every run."""
        monkeypatch.setenv(COPY_DIR_ENV, str(tmp_path))
        svc = _svc()
        assert svc._local_copy_dir is not None, "local_copy_dir should still resolve"
        assert svc._ceg_seal_tee_enabled is False

    @pytest.mark.parametrize("raw", ["true", "TRUE", "True", "1", "yes", "on", " true "])
    def test_env_opt_in_accepted(self, raw: str, monkeypatch) -> None:
        monkeypatch.setenv(TEE_ENV, raw)
        assert _svc()._ceg_seal_tee_enabled is True

    @pytest.mark.parametrize("raw", ["false", "0", "no", "off", "", "  "])
    def test_env_non_affirmative_stays_off(self, raw: str, monkeypatch) -> None:
        monkeypatch.setenv(TEE_ENV, raw)
        assert _svc()._ceg_seal_tee_enabled is False

    def test_config_opt_in_accepted(self) -> None:
        assert _svc({"ceg_seal_tee": True})._ceg_seal_tee_enabled is True

    def test_config_takes_precedence_over_env(self, monkeypatch) -> None:
        """Matches how local_copy_dir / trace_level resolve: config wins."""
        monkeypatch.setenv(TEE_ENV, "true")
        assert _svc({"ceg_seal_tee": False})._ceg_seal_tee_enabled is False

    def test_disabled_tee_opens_no_database_handle(self, tmp_path, monkeypatch) -> None:
        """The whole point: with the tee off, sqlite3.connect is never reached.

        Guards the crash directly rather than the flag — a future refactor
        that moves the gate below the connect would still be caught here.
        """
        monkeypatch.setenv(COPY_DIR_ENV, str(tmp_path))
        svc = _svc()

        import sqlite3

        def _boom(*a: Any, **k: Any) -> Any:
            raise AssertionError("sqlite3.connect reached with the CEG seal-tee disabled")

        monkeypatch.setattr(sqlite3, "connect", _boom)
        svc._tee_ceg_on_seal("th_test", "trace_test")
