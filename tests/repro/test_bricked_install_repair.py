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


# ---------------------------------------------------------------------------
# THE NEAR-MISS: the repair moved a CI checkout.
#
# get_ciris_home() falls back to "current directory if in git repo
# (development)". In CI, CIRIS_HOME is unset and the workspace IS a git repo, so
# `home` resolved to the checkout and the repair renamed
# /home/runner/work/CIRISAgent/CIRISAgent out from under the running job. The
# next step failed with "Can't find 'action.yml' … under .github/actions/…"
# because the whole tree had moved.
#
# The tests above never caught it: every one of them passes an explicit tmp_path
# that looks like a data home. None asked what happens when the resolved home is
# something else entirely — which is the only situation where a destructive
# repair can do real harm.
# ---------------------------------------------------------------------------


def test_a_source_checkout_is_never_moved(tmp_path) -> None:
    """The exact CI shape: a git repo that is not a CIRIS home."""
    repo = tmp_path / "CIRISAgent"
    (repo / ".git").mkdir(parents=True)
    (repo / "ciris_engine").mkdir()
    (repo / ".github" / "actions").mkdir(parents=True)

    assert br.repair_if_bricked(repo, RuntimeError(FIELD_ERROR), VERSION) is None
    assert (repo / ".github" / "actions").exists(), "the checkout was moved"


@pytest.mark.parametrize("marker", [".git", "pyproject.toml", "ciris_engine", "setup.py", ".github"])
def test_any_source_marker_blocks_the_move(tmp_path, marker) -> None:
    """One marker is enough. A data home has none of these."""
    d = tmp_path / "looks-like-source"
    (d / "identity").mkdir(parents=True)  # also looks like a home — source still wins
    target = d / marker
    target.mkdir() if "." not in marker or marker in (".git", ".github") else target.write_text("x")

    assert br.refuse_reason(d) is not None


def test_the_current_working_directory_is_never_moved(tmp_path, monkeypatch) -> None:
    """Moving the CWD out from under a running process is not a repair."""
    d = tmp_path / "home"
    (d / "identity").mkdir(parents=True)
    monkeypatch.chdir(d)

    assert br.refuse_reason(d) is not None


def test_an_unrecognisable_directory_is_never_moved(tmp_path) -> None:
    """No home markers at all — we have no evidence this is ours to move."""
    d = tmp_path / "somebody-elses-folder"
    d.mkdir()
    (d / "holiday-photos").mkdir()

    assert br.refuse_reason(d) is not None


def test_a_real_home_is_still_repairable(home) -> None:
    """The gate must not be so tight that it never fires on the actual bug."""
    assert br.refuse_reason(home) is None
    assert br.repair_if_bricked(home, RuntimeError(FIELD_ERROR), VERSION) is not None


def test_a_home_identified_only_by_its_marker_is_repairable(tmp_path) -> None:
    """A home wiped down to its stamp is still a home."""
    d = tmp_path / "ciris"
    d.mkdir()
    br.record_install_version(d, "2.9.44-stable")

    assert br.refuse_reason(d) is None


# THE NEAR-MISS: this repair moved a CI checkout.
#
# get_ciris_home() falls back to "current directory if in git repo
# (development)". CIRIS_HOME is unset in CI and the workspace IS a git repo, so
# `home` resolved to the checkout and the repair renamed it mid-run. The next
# step died on "Can't find 'action.yml' … under .github/actions/…".
#
# Every test above passes an explicit tmp_path that already looks like a data
# home, so none of them asked the only question that matters for a destructive
# operation: what if the path we resolved is not ours to move?


def test_a_source_checkout_is_never_moved(tmp_path) -> None:
    repo = tmp_path / "CIRISAgent"
    (repo / ".git").mkdir(parents=True)
    (repo / ".github" / "actions").mkdir(parents=True)

    assert br.repair_if_bricked(repo, RuntimeError(FIELD_ERROR), VERSION) is None
    assert (repo / ".github" / "actions").exists(), "the checkout was moved"


def test_the_current_working_directory_is_never_moved(tmp_path, monkeypatch) -> None:
    d = tmp_path / "home"
    (d / "identity").mkdir(parents=True)
    monkeypatch.chdir(d)
    assert br.refuse_reason(d) is not None


def test_an_unrecognisable_directory_is_never_moved(tmp_path) -> None:
    d = tmp_path / "somebody-elses-folder"
    (d / "holiday-photos").mkdir(parents=True)
    assert br.refuse_reason(d) is not None


def test_a_real_home_is_still_repairable(home) -> None:
    """The guard must not be so tight that it never fires on the actual bug."""
    assert br.refuse_reason(home) is None
    assert br.repair_if_bricked(home, RuntimeError(FIELD_ERROR), VERSION) is not None
