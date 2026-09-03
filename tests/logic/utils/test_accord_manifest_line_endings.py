"""Signed artifacts must survive a Windows checkout unchanged.

THE BUG. `seed/accord_manifest.json` is Ed25519-signed over its EXACT BYTES and
contains 19 newlines. Nothing in the repo marked it byte-exact:

    $ git check-attr text eol -- seed/accord_manifest.json
    text: unspecified    eol: unspecified

so on Windows — where `core.autocrlf` defaults to true, including on GitHub's
runners — checkout rewrote those 19 LFs to CRLF. Nineteen bytes changed:

    7c7c7e3a24d89b4b82893849c4077b96   as committed (LF)
    296b6b32bb137c5f5d1560fff60b89b9   after autocrlf

and the agent aborted at startup:

    [ACCORD] SIGNATURE VERIFICATION FAILED: InvalidSignature
    This indicates possible tampering with ACCORD files or the comprehensive guide.

Nothing was tampered with. The message sends whoever reads it hunting a security
incident instead of a checkout setting, which is its own defect.

It breaks TWICE, and the second is easy to miss: the manifest also HASHES four
content files, so those are CRLF'd too and fail their hash check independently of
the signature failing on the manifest.

WHY THESE TESTS RUN EVERYWHERE, NOT JUST ON WINDOWS. The corruption happens at
CHECKOUT, so a test that merely reads the working tree on Linux sees a clean file
and passes — which is exactly how this shipped. These simulate the rewrite
instead: apply LF->CRLF in memory and assert the bytes change, then assert the
repo declares the attribute that prevents it. Both hold on any platform, so the
invariant is protected without needing a Windows runner to notice.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
MANIFEST = REPO / "seed" / "accord_manifest.json"

#: Every artifact whose bytes are signed, hashed, or otherwise authenticated.
BYTE_EXACT = [
    "seed/accord_manifest.json",
    "seed/accord_manifest.sig",
    "ciris_engine/data/accord_1.2b_POLYGLOT.txt",
    "ciris_engine/data/accord_1.2b_POLYGLOT_compressed.txt",
    # The guides moved to localized/*.txt in 2.8.5; the .md paths named here
    # (and in the manifest) had not existed since.
    "ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt",
    "ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_MOBILE.txt",
] + sorted(
    # The 29 localized accord texts. These are what the action-selection DMAs
    # put in front of the model, and they are now in the signed manifest, so
    # they must be byte-exact too -- .gitattributes covers them by the
    # `ciris_engine/data/localized/** -text` rule.
    str(p.relative_to(REPO)) for p in (REPO / "ciris_engine/data/localized").glob("accord_1.2b_*.txt")
)


def _git_text_attr(rel: str) -> str:
    out = subprocess.run(
        ["git", "check-attr", "text", "--", rel],
        cwd=REPO, capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    return out.rsplit(": ", 1)[-1] if out else "?"


@pytest.mark.parametrize("rel", BYTE_EXACT)
def test_signed_artifacts_are_not_eligible_for_eol_translation(rel: str) -> None:
    """`text` must be `unset`/`-text` so git copies the bytes verbatim.

    This is the assertion that would have prevented the bug: it fails on Linux,
    today, with no Windows runner involved.
    """
    path = REPO / rel
    if not path.exists():
        pytest.skip(f"{rel} not in this checkout")
    attr = _git_text_attr(rel)
    assert attr == "unset", (
        f"{rel} has git text attribute {attr!r}; on a Windows checkout "
        "core.autocrlf will rewrite its line endings and invalidate the "
        "signature/hash. Pin it with `-text` in .gitattributes."
    )


@pytest.mark.parametrize("rel", BYTE_EXACT)
def test_a_crlf_rewrite_would_actually_corrupt_them(rel: str) -> None:
    """Prove the hazard is real for each file, rather than assuming it.

    If a file has no bare LF the rewrite is a no-op and pinning it is harmless
    belt-and-braces; if it does, this documents exactly what was at stake.
    """
    path = REPO / rel
    if not path.exists():
        pytest.skip(f"{rel} not in this checkout")
    raw = path.read_bytes()
    assert b"\r\n" not in raw, f"{rel} already contains CRLF in the repo — it was committed corrupted"
    rewritten = raw.replace(b"\n", b"\r\n")
    if raw == rewritten:
        pytest.skip(f"{rel} has no bare LF; pinning is precautionary")
    assert hashlib.sha256(raw).digest() != hashlib.sha256(rewritten).digest()


def test_the_manifest_covers_only_files_we_have_pinned() -> None:
    """A fifth file added to the manifest must not silently go unpinned.

    The manifest is the authority on what is hashed. If it grows an entry that
    is not in BYTE_EXACT (and therefore not in .gitattributes), Windows breaks
    again in exactly the same way — so fail here, at the moment it is added.
    """
    import json

    if not MANIFEST.exists():
        pytest.skip("manifest not in this checkout")
    covered = set(json.loads(MANIFEST.read_text(encoding="utf-8")).get("files", {}))
    pinned = {pathlib.PurePosixPath(p).name for p in BYTE_EXACT}
    missing = sorted(covered - pinned)
    assert not missing, (
        f"manifest hashes {missing} but they are not pinned byte-exact; a Windows "
        "checkout will CRLF them and the hash check will fail"
    )


def test_gitattributes_exists_at_all() -> None:
    """The root cause was its absence, so name that directly."""
    ga = REPO / ".gitattributes"
    assert ga.exists(), (
        "no .gitattributes — without one, core.autocrlf on Windows rewrites every "
        "file git considers text, including signed artifacts"
    )
    body = ga.read_text(encoding="utf-8")
    assert "seed/" in body and "-text" in body


def test_shell_scripts_are_pinned_to_lf() -> None:
    """A CRLF shebang is an unrunnable script with a baffling error.

    Not part of the ACCORD failure, but the same mechanism one step over, and
    cheap to hold while we are here.
    """
    for rel in ("gradlew",):
        if (REPO / rel).exists():
            out = subprocess.run(
                ["git", "check-attr", "eol", "--", rel],
                cwd=REPO, capture_output=True, text=True, timeout=30,
            ).stdout.strip()
            assert out.endswith("lf"), f"{rel} is not pinned to LF: {out}"
