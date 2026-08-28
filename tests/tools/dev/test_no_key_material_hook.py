"""The path-based key-material gate, pinned against the files it failed to stop.

124 files under ``identity/`` were tracked in this repo and 122 reached main —
61 raw 32-byte ``master.key`` files and 61 sealed ``ed25519.seed.blob`` files.
Three protections were live and none could see them:

  * ``detect-private-key`` matches PEM armor; these have no header at all
  * ``check-added-large-files`` fires at 250 KB; a master key is 32 bytes
  * ``.gitignore`` had no rule — and is inert for already-tracked files anyway

Each of those tests a FORMAT or a SIZE. The invariant is a PATH, which is what
these tests assert, using the real filenames from the incident.
"""

from __future__ import annotations

import pytest

from tools.dev.check_no_key_material import main, offending_paths

# Verbatim from `git ls-files identity/` before the removal.
REAL_TRACKED = [
    "identity/ciris-agent-bootstrap-2cp274ds35.master.key",
    "identity/ciris-agent-bootstrap-2cp274ds35.ed25519.seed.blob",
    "identity/ciris-agent-bootstrap-2cp274ds35-substrate.master.key",
    "identity/ciris-agent-bootstrap-2wib7skvcz-substrate.ed25519.seed.blob",
]


@pytest.mark.parametrize("path", REAL_TRACKED)
def test_blocks_the_files_that_actually_got_committed(path: str) -> None:
    assert offending_paths([path]) == [path]
    assert main([path]) == 1


def test_blocks_key_material_moved_out_of_the_identity_directory() -> None:
    """Matching only on the directory would let a rename carry the exposure."""
    moved = "build/staging/node.ed25519.seed.blob"
    assert offending_paths([moved]) == [moved]


def test_blocks_the_whole_keys_directory() -> None:
    assert offending_paths(["keys/anything-at-all"]) == ["keys/anything-at-all"]


def test_blocks_even_when_forced_past_gitignore() -> None:
    """The reason a .gitignore rule alone is not enough.

    `git add -f identity/x.master.key` stages the file regardless of ignore
    rules, and a file that is already tracked ignores .gitignore entirely —
    which is exactly how these survived release after release. The hook sees
    staged paths, so it refuses both.
    """
    assert main(["identity/x.master.key"]) == 1


@pytest.mark.parametrize(
    "path",
    [
        "ciris_engine/constants.py",
        "apps/android/build.gradle",
        "tools/dev/check_no_key_material.py",
        "README.md",
    ],
)
def test_allows_ordinary_files(path: str) -> None:
    assert offending_paths([path]) == []
    assert main([path]) == 0


@pytest.mark.parametrize(
    "path",
    ["tests/fixtures/fake.master.key", "docs/identity/example.master.key"],
)
def test_allows_fixtures_and_docs(path: str) -> None:
    """Tests and docs must be able to NAME these shapes without being blocked."""
    assert offending_paths([path]) == []


def test_reports_every_offender_not_just_the_first(capsys: pytest.CaptureFixture[str]) -> None:
    """A commit sweeping in 61 keys should not be fixed one error at a time."""
    assert main(REAL_TRACKED) == 1
    out = capsys.readouterr().out
    for path in REAL_TRACKED:
        assert path in out


def test_message_says_why_detect_private_key_missed_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Whoever trips this will ask the question the incident raised."""
    main(["identity/x.master.key"])
    out = capsys.readouterr().out
    assert "PEM armor" in out
    assert "history" in out, "must say deleting the file later does not undo it"
    assert "git restore --staged" in out, "must state the remedy"
