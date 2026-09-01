"""The repair must fire on the damage, and on nothing else.

A repair that wipes a home is only safe if its gate is exact. These tests exist
because the failure mode of getting this wrong is destroying a working install —
strictly worse than the bug it is meant to cure.
"""

from __future__ import annotations

import json

import pytest

from ciris_engine.logic.setup import bricked_install as br

VERSION = "2.9.47-stable"

FIELD_ERROR = (
    "node fold failed to start (node-fails ⇒ agent-fails): RuntimeError: re-author "
    "consent ciris-node-bootstrap-3nclwiulun -> ciris-canonical-1-d7bdeu223k: refusing "
    'to emit a consent grant naming "ciris-node-bootstrap-3nclwiulun": this engine signs '
    'as "ciris-agent-bootstrap-jbdibklyfz", and a consent grant is self-attested '
    "(CEG 1.0-RC29 §5.6.8.15)"
)


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "ciris"
    (h / "identity").mkdir(parents=True)
    (h / "data").mkdir()
    (h / "data" / "ciris_engine.db").write_text("not really a db")
    return h


def test_the_field_failure_is_recognised() -> None:
    """Verbatim from the user's log — if this stops matching, repair stops firing."""
    assert br.is_fatal_identity_failure(FIELD_ERROR)


@pytest.mark.parametrize(
    "other",
    [
        "Connection refused",
        "sqlite3.OperationalError: database is locked",
        "LLM call failed (InstructorRetryException): HTTP 402 requires more credits",
        "no /health from http://localhost:9091 within 120s",
    ],
)
def test_unrelated_failures_are_not_repaired(other) -> None:
    """THE DANGEROUS DIRECTION. Wiping a home to cure a network blip is worse
    than the blip. Anything we do not positively recognise is left alone."""
    assert not br.is_fatal_identity_failure(other)


def test_an_unstamped_home_is_eligible(home) -> None:
    """No build before 2.9.47 wrote a marker — absence IS the signal."""
    assert br.install_predates_fix(home)


@pytest.mark.parametrize("stamped", ["2.9.44-stable", "2.9.46", "2.8.0", "1.0.0"])
def test_homes_from_bricking_builds_are_eligible(home, stamped) -> None:
    br.record_install_version(home, stamped)
    assert br.install_predates_fix(home)


@pytest.mark.parametrize("stamped", ["2.9.47-stable", "2.9.48", "2.10.0", "3.0.0"])
def test_homes_from_fixed_builds_are_not(home, stamped) -> None:
    """A fixed build that fails this way has a DIFFERENT fault.

    Repairing would destroy a sound install without curing anything, and would
    loop: wipe, re-create, fail again, wipe again.
    """
    br.record_install_version(home, stamped)
    assert not br.install_predates_fix(home)


def test_a_corrupt_marker_is_treated_as_eligible(home) -> None:
    (home / br.INSTALL_MARKER).write_text("{not json")
    assert br.install_predates_fix(home)


def test_repair_archives_rather_than_deletes(home) -> None:
    """Nothing is destroyed. The identity is unusable but it is also the evidence."""
    db = home / "data" / "ciris_engine.db"
    archive = br.repair_if_bricked(home, RuntimeError(FIELD_ERROR), VERSION)

    assert archive is not None and archive.exists()
    assert (archive / "data" / "ciris_engine.db").read_text() == "not really a db"
    assert not db.exists(), "the damaged home must be out of the way"
    assert home.exists(), "a fresh home must be ready for the next boot"


def test_the_fresh_home_is_stamped_so_repair_cannot_loop(home) -> None:
    br.repair_if_bricked(home, RuntimeError(FIELD_ERROR), VERSION)

    assert not br.install_predates_fix(home)
    stamped = json.loads((home / br.INSTALL_MARKER).read_text())["version"]
    assert stamped == VERSION


def test_a_fixed_home_is_never_wiped(home) -> None:
    br.record_install_version(home, "2.9.47-stable")
    assert br.repair_if_bricked(home, RuntimeError(FIELD_ERROR), VERSION) is None
    assert (home / "data" / "ciris_engine.db").exists()


def test_an_unrelated_failure_never_wipes(home) -> None:
    assert br.repair_if_bricked(home, RuntimeError("Connection refused"), VERSION) is None
    assert (home / "data" / "ciris_engine.db").exists()


def test_the_operator_can_refuse(home, monkeypatch) -> None:
    """Opt-out matters for anyone debugging the damaged state deliberately."""
    monkeypatch.setenv("CIRIS_NO_AUTO_REPAIR", "1")
    assert br.repair_if_bricked(home, RuntimeError(FIELD_ERROR), VERSION) is None
    assert (home / "data" / "ciris_engine.db").exists()
