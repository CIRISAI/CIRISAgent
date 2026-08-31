"""Materialising the iOS bundle must never destroy work in the tree.

`Resources.zip` is a committed artifact whose tree is mostly gitignored build
output, so the updater unpacks it before editing. The archive also contains
STALE copies of files that git tracks, and an early version of this unpacked
everything and then ran `git checkout -- <tracked>` to put the committed copies
back.

That is a data-loss bug. `git checkout --` does not restore "the committed copy
over the archive copy" — it restores the committed copy over WHATEVER IS THERE,
including edits the caller has not committed yet. Running the updater in a normal
checkout with local work under `apps/ios/Resources` (2,512 tracked files) silently
discarded it. No prompt, no backup, no undo.

The fix is not to detect the dirty tree and refuse — it is to never write to a
tracked path at all, so the question does not arise. These tests pin that: the
archive supplies only what git does not track.
"""

from __future__ import annotations

import pathlib
import subprocess
import zipfile

import pytest

import tools.update_substrate_libs as usl


def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def ios_repo(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """A repo shaped like ours: a tracked resource, plus an archive holding a
    stale copy of it and some untracked build output."""
    repo = tmp_path / "repo"
    resources = repo / "apps" / "ios" / "Resources"
    resources.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")

    # Tracked, and committed with its correct content.
    (resources / "en.json").write_text('{"hello": "committed"}', encoding="utf-8")
    _git(repo, "add", "apps/ios/Resources/en.json")
    _git(repo, "commit", "-qm", "resource")

    # The archive carries a STALE en.json plus the build output that is the whole
    # reason materialisation exists. Padding entries make it "fuller" than the
    # tree so the idempotence check does not short-circuit.
    with zipfile.ZipFile(repo / "apps" / "ios" / "Resources.zip", "w") as z:
        z.writestr("en.json", '{"hello": "STALE-FROM-ARCHIVE"}')
        z.writestr("app_packages/mod.py", "# build output")
        for i in range(10):
            z.writestr(f"python/pad{i}.py", "")

    monkeypatch.setattr(usl, "REPO_ROOT", repo)
    monkeypatch.setattr(usl, "IOS_APP_DIR", repo / "apps" / "ios")
    monkeypatch.setattr(usl, "IOS_RESOURCES_DIR", resources)
    return repo


def test_uncommitted_edits_survive(ios_repo: pathlib.Path) -> None:
    """THE BUG. An edit that exists only in the working tree must still be there.

    Under the `git checkout --` version this assertion fails with the committed
    content: the caller's unsaved work is simply gone.
    """
    live = ios_repo / "apps" / "ios" / "Resources" / "en.json"
    live.write_text('{"hello": "MY UNCOMMITTED WORK"}', encoding="utf-8")

    usl.materialize_resources_tree()

    assert live.read_text(encoding="utf-8") == '{"hello": "MY UNCOMMITTED WORK"}'


def test_committed_content_is_not_reverted_to_the_archive(ios_repo: pathlib.Path) -> None:
    """The original defect, which must stay fixed: the stale archive copy of a
    tracked file must not win over the tree."""
    live = ios_repo / "apps" / "ios" / "Resources" / "en.json"

    usl.materialize_resources_tree()

    assert "STALE-FROM-ARCHIVE" not in live.read_text(encoding="utf-8")


def test_untracked_build_output_is_still_supplied(ios_repo: pathlib.Path) -> None:
    """Skipping tracked paths must not break the job the function exists to do."""
    usl.materialize_resources_tree()

    assert (ios_repo / "apps" / "ios" / "Resources" / "app_packages" / "mod.py").exists()


def test_a_deleted_tracked_file_is_reported_not_silently_replaced(
    ios_repo: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A deletion is working-tree state too.

    Restoring it from the archive would put stale content back under a path the
    caller deliberately emptied. Say so and let them decide.
    """
    (ios_repo / "apps" / "ios" / "Resources" / "en.json").unlink()

    usl.materialize_resources_tree()

    out = capsys.readouterr().out
    assert "missing from the working tree" in out
    assert not (ios_repo / "apps" / "ios" / "Resources" / "en.json").exists()
