"""latest.log must exist on Windows, where symlinks need a privilege users lack.

THE BUG. Both log handlers created their "latest" pointer with

    latest_link.symlink_to(log_filename.name)

inside `except Exception: pass`. Creating a symlink on Windows requires
Developer Mode or elevation; an ordinary user gets

    OSError: [WinError 1314] A required privilege is not held by the client

which was swallowed, so no latest.log and no incidents_latest.log were created.
Nothing crashed -- and the most-used debugging entry point we have silently did
not exist. Our runbook opens with "ALWAYS check incidents_latest.log FIRST", and
every Windows bug report so far arrived without it.

WinError 1314 is simulated here by making symlink_to raise, so the fallback
chain is exercised on any platform rather than only where it is needed.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from ciris_engine.logic.utils.latest_link import link_latest


def _win1314(*a, **k):
    raise OSError(1314, "A required privilege is not held by the client")


@pytest.fixture
def logdir(tmp_path: pathlib.Path) -> pathlib.Path:
    target = tmp_path / "ciris_2026-08-16.log"
    target.write_text("first line\n", encoding="utf-8")
    return tmp_path


def test_symlink_is_preferred_where_it_works(logdir: pathlib.Path) -> None:
    """It survives rotation, because it points at a name rather than a file."""
    link = logdir / "latest.log"
    kind = link_latest(link, logdir / "ciris_2026-08-16.log")
    if kind == "symlink":
        assert link.is_symlink()
        assert link.read_text(encoding="utf-8") == "first line\n"
    else:
        pytest.skip(f"symlinks unavailable here (got {kind})")


def test_falls_back_to_hardlink_when_symlinks_are_forbidden(
    logdir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE WINDOWS PATH. Hardlinks need no privilege on NTFS, same volume."""
    monkeypatch.setattr(pathlib.Path, "symlink_to", _win1314, raising=True)

    link = logdir / "latest.log"
    kind = link_latest(link, logdir / "ciris_2026-08-16.log")

    assert kind == "hardlink"
    assert link.exists()
    assert link.read_text(encoding="utf-8") == "first line\n"


def test_the_hardlink_is_a_live_view(logdir: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stale copy would be worse than useless -- `tail` has to follow writes."""
    monkeypatch.setattr(pathlib.Path, "symlink_to", _win1314, raising=True)
    target = logdir / "ciris_2026-08-16.log"
    link = logdir / "latest.log"
    assert link_latest(link, target) == "hardlink"

    with open(target, "a", encoding="utf-8") as f:
        f.write("second line\n")

    assert link.read_text(encoding="utf-8") == "first line\nsecond line\n"


def test_falls_back_to_a_pointer_file_when_neither_link_works(
    logdir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAT32, a network share, a bind mount. Names the file, which is the question."""
    monkeypatch.setattr(pathlib.Path, "symlink_to", _win1314, raising=True)
    monkeypatch.setattr(os, "link", _win1314, raising=True)

    link = logdir / "latest.log"
    kind = link_latest(link, logdir / "ciris_2026-08-16.log")

    assert kind == "pointer"
    body = link.read_text(encoding="utf-8")
    assert "ciris_2026-08-16.log" in body
    assert "POINTER FILE" in body, "must not be mistaken for the log itself"


def test_a_dangling_symlink_is_replaced(logdir: pathlib.Path) -> None:
    """exists() is False for a broken link, so it survives unless is_symlink() is checked.

    Without that, yesterday's dead link persists and every later attempt fails
    with FileExistsError -- latest.log stays permanently broken.
    """
    link = logdir / "latest.log"
    try:
        link.symlink_to("gone-2026-01-01.log")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable here")

    assert not link.exists()  # dangling
    assert link.is_symlink()

    kind = link_latest(link, logdir / "ciris_2026-08-16.log")
    assert kind in ("symlink", "hardlink", "pointer")
    assert link.read_text(encoding="utf-8").startswith("first line")


def test_it_never_raises_even_when_everything_fails(logdir: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Logging setup must not be able to stop the process from starting."""
    monkeypatch.setattr(pathlib.Path, "symlink_to", _win1314, raising=True)
    monkeypatch.setattr(os, "link", _win1314, raising=True)
    monkeypatch.setattr(pathlib.Path, "write_text", _win1314, raising=True)

    assert link_latest(logdir / "latest.log", logdir / "ciris_2026-08-16.log") == "failed"


def test_repeated_calls_are_idempotent(logdir: pathlib.Path) -> None:
    """It runs on every start, and on every incident-log roll."""
    link = logdir / "latest.log"
    kinds = {link_latest(link, logdir / "ciris_2026-08-16.log") for _ in range(3)}
    assert kinds != {"failed"}
    assert link.read_text(encoding="utf-8").startswith("first line")


def test_both_handlers_route_through_the_helper() -> None:
    """Neither may go back to calling symlink_to directly and swallowing failure."""
    repo = pathlib.Path(__file__).resolve().parents[3]
    for rel in (
        "ciris_engine/logic/utils/logging_config.py",
        "ciris_engine/logic/utils/incident_capture_handler.py",
    ):
        text = (repo / rel).read_text(encoding="utf-8")
        assert "link_latest" in text, f"{rel} does not use the shared helper"
        assert ".symlink_to(" not in text, f"{rel} still calls symlink_to directly; it fails unprivileged on Windows"
