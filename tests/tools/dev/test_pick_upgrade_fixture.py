"""The long-jump job must never boot a fixture captured by a newer version."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[3] / "tools" / "dev" / "pick_upgrade_fixture.py"
_spec = importlib.util.spec_from_file_location("pick_upgrade_fixture", _PATH)
assert _spec and _spec.loader
picker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(picker)


def _artifact(name, created, expired=False):
    return {"name": name, "created_at": created, "expired": expired}


def test_a_newer_fixture_is_never_chosen_even_when_oldest():
    artifacts = [
        _artifact("upgrade-fixture-2.16.3-stable-memory-burst", "2026-10-20T00:00:00Z"),
        _artifact("upgrade-fixture-2.16.2-stable-qa-full", "2026-10-22T04:09:16Z"),
    ]
    assert picker.pick(artifacts, (2, 16, 2)) == "upgrade-fixture-2.16.2-stable-qa-full"


def test_the_oldest_eligible_fixture_wins():
    artifacts = [
        _artifact("upgrade-fixture-2.16.2-stable-qa-full", "2026-10-22T04:09:16Z"),
        _artifact("upgrade-fixture-2.15.0-stable-qa-full", "2026-10-01T00:00:00Z"),
        _artifact("upgrade-fixture-2.14.0-stable-qa-full", "2026-09-01T00:00:00Z", expired=True),
    ]
    assert picker.pick(artifacts, (2, 16, 2)) == "upgrade-fixture-2.15.0-stable-qa-full"


def test_versions_compare_numerically_not_lexically():
    artifacts = [_artifact("upgrade-fixture-2.9.14-stable-qa-full", "2026-06-01T00:00:00Z")]
    assert picker.pick(artifacts, (2, 16, 2)) == "upgrade-fixture-2.9.14-stable-qa-full"
    assert picker.pick(artifacts, (2, 9, 13)) is None


def test_nothing_eligible_yields_none():
    artifacts = [
        _artifact("upgrade-fixture-2.17.0-stable-qa-full", "2026-10-01T00:00:00Z"),
        _artifact("unrelated-artifact", "2026-01-01T00:00:00Z"),
    ]
    assert picker.pick(artifacts, (2, 16, 2)) is None


def test_reads_the_repo_version():
    major, minor, patch = picker.current_version()
    assert (major, minor, patch) >= (2, 16, 0)
