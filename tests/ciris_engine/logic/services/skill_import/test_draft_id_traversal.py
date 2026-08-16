"""A draft id is a uuid4, and anything else must not become a filesystem path.

THE BUG. `draft_id` arrives as a raw FastAPI path parameter on
`/v1/system/skills/drafts/{draft_id}` with no validation, and was interpolated
straight into a filename:

    path = self.drafts_dir / f"{draft_id}.json"

`{draft_id}` matches ONE path segment against the RAW url and is
percent-decoded afterwards, so `..%2F..%2Fetc%2Fpasswd` matches as a single
segment and only then becomes `../../etc/passwd`. That reached:

  * `path.unlink()` in `delete_draft` — arbitrary `.json` deletion. The
    deployment's OAuth client secrets live in `oauth.json`; deleting it is how
    you take hosted Google sign-in down without touching a credential.
  * `path.read_text()` in `load_draft`, whose failure branch logged the
    exception — and a pydantic `ValidationError` RENDERS THE INPUT IT REJECTED,
    so an unparseable file's contents were written to the log. Read primitive
    and disclosure sink in the same eight lines.

Admin-gated, so this is not remote-unauthenticated. It is still not something
an admin should be able to do: the drafts directory is the whole of this
service's authority over the filesystem.

WHY VALIDATE RATHER THAN CONTAIN. `SkillDraft.draft_id` is
`default_factory=lambda: str(uuid4())`. There is exactly one legal shape, so
"is this a uuid4" is a total answer — no normalising, no resolve-and-compare
against the parent, no symlink question. The containment check is the right
tool when ids are user-chosen names; here it would be strictly weaker.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from ciris_engine.logic.services.skill_import.builder import SkillBuilder, SkillDraft


@pytest.fixture
def builder(tmp_path: Path) -> SkillBuilder:
    return SkillBuilder(drafts_dir=tmp_path / "drafts")


#: Each of these matches a single FastAPI path segment, either literally or
#: after percent-decoding, which is what made them reachable.
TRAVERSALS = [
    "../../../../etc/passwd",
    "..%2F..%2Fetc%2Fpasswd",
    "../../.ciris/oauth",
    "....//....//oauth",
    "/etc/passwd",
    "..",
    ".",
    "",
    "a/b",
    "\\..\\..\\windows\\system32\\config",
    "draft\x00.json",
]


@pytest.mark.parametrize("draft_id", TRAVERSALS)
def test_traversal_never_yields_a_path(builder: SkillBuilder, draft_id: str) -> None:
    assert builder._draft_path(draft_id) is None


@pytest.mark.parametrize("draft_id", TRAVERSALS)
def test_delete_cannot_reach_outside_the_drafts_dir(
    builder: SkillBuilder, tmp_path: Path, draft_id: str
) -> None:
    """The one that actually destroys something.

    A real file is planted where the traversal points so this fails loudly if
    the guard regresses, rather than passing because nothing was there.
    """
    victim = tmp_path / "oauth.json"
    victim.write_text('{"google": {"client_secret": "REDACTED"}}', encoding="utf-8")

    assert builder.delete_draft(draft_id) is False
    assert victim.exists(), "delete_draft escaped the drafts directory"


@pytest.mark.parametrize("draft_id", TRAVERSALS)
def test_load_cannot_read_outside_the_drafts_dir(builder: SkillBuilder, draft_id: str) -> None:
    assert builder.load_draft(draft_id) is None


def test_a_real_uuid4_still_round_trips(builder: SkillBuilder) -> None:
    """The guard must not break the feature it protects."""
    draft = SkillDraft()
    path = builder.save_draft(draft)

    assert path.exists()
    loaded = builder.load_draft(draft.draft_id)
    assert loaded is not None and loaded.draft_id == draft.draft_id
    assert builder.delete_draft(draft.draft_id) is True
    assert not path.exists()


def test_uppercase_uuid_is_accepted(builder: SkillBuilder) -> None:
    """Case-insensitive hex: a client that upper-cases the id is not an attacker."""
    assert builder._draft_path(str(uuid4()).upper()) is not None


def test_missing_draft_is_none_not_an_error(builder: SkillBuilder) -> None:
    """A well-formed id for a draft that does not exist is a 404, not a rejection."""
    assert builder.load_draft(str(uuid4())) is None
    assert builder.delete_draft(str(uuid4())) is False


def test_save_refuses_a_forged_draft_id(builder: SkillBuilder) -> None:
    """`draft_id` has a default factory but is still an assignable field."""
    draft = SkillDraft()
    draft.draft_id = "../../evil"
    with pytest.raises(ValueError):
        builder.save_draft(draft)


def test_load_failure_does_not_log_the_file_contents(
    builder: SkillBuilder, caplog: pytest.LogCaptureFixture
) -> None:
    """The disclosure half: pydantic errors echo the input they rejected.

    A valid-uuid draft file holding non-SkillDraft JSON must produce a log line
    naming the failure TYPE and nothing from the file.
    """
    draft_id = str(uuid4())
    builder.drafts_dir.mkdir(parents=True, exist_ok=True)
    (builder.drafts_dir / f"{draft_id}.json").write_text(
        '{"client_secret": "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"}', encoding="utf-8"
    )

    with caplog.at_level("ERROR"):
        assert builder.load_draft(draft_id) is None

    assert "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" not in caplog.text
    assert "ValidationError" in caplog.text


def test_rejection_log_does_not_echo_the_id(
    builder: SkillBuilder, caplog: pytest.LogCaptureFixture
) -> None:
    """CWE-117: the rejected id is attacker-controlled and must not reach the log."""
    with caplog.at_level("WARNING"):
        builder._draft_path("../../../etc/passwd\n[FAKE] forged log line")

    assert "etc/passwd" not in caplog.text
    assert "forged log line" not in caplog.text
