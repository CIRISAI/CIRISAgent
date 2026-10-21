"""The bundled ciris-server wheel must actually carry a Google client id.

We do not compile the wheel — `BUILTIN_GOOGLE_DESKTOP_CLIENT_ID` is `option_env!`
in the Rust, baked by whoever ran maturin — so the only thing we can check is the
ARTIFACT we ship. That distinction is the whole lesson of CIRISServer#387:

  * 0.5.165 and .166 published wheels with the credential blank, because
    `publish-pypi.yml` called `build-wheels.yml` without `secrets: inherit`. A
    reusable workflow receives no secrets unless the caller passes them, and the
    missing ones resolve to the empty string with no warning and no failure. The
    injection was correct in the file the entire time; it was handed nothing.
  * The upstream gate that should have caught it iterated a hardcoded list of the
    two files already fixed and asserted they were still fixed — denominator
    equal to numerator, green by construction.
  * Local verification built a wheel with the env exported, which proves the
    mechanism and nothing about what users install. One box builds one target, so
    that check was structurally incapable of finding a per-platform gap.

What a node without it does is worse than failing: `/v1/auth/oauth/google/login`
307'd to accounts.google.com with `client_id=` blank, so the user met Google's
error page rather than a typed refusal.

Two self-inspecting meta-tests were tried here and removed: one grepped this
file for `.yml` while containing that literal, and one scanned this file for a
client-id shape while carrying a fabricated one as its own fixture. Both are the
same trap the upstream fix hit — a check satisfied by its own text. The subject
of a check must be the artifact, never the check.

CHECK BY SHAPE, NEVER BY VALUE. Asserting the literal id would put a credential
in committed source — the exact thing the compile-time injection exists to avoid —
and would also break every time the client is rotated. The shape is enough: a
blank injection produces no match at all.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

# `<digits>-<token>.apps.googleusercontent.com`. Matches any Google client id
# without encoding which one, so rotating the credential does not touch this file.
CLIENT_ID_SHAPE = re.compile(rb"[0-9]{8,}-[a-z0-9]{10,}\.apps\.googleusercontent\.com")

ANDROID_WHEELS = sorted(Path("apps/android/wheels").glob("ciris_server-*.whl"))


def _native_so_bytes(wheel: Path) -> bytes:
    with zipfile.ZipFile(wheel) as z:
        name = next((n for n in z.namelist() if n.endswith("_native.abi3.so")), None)
        assert name, f"{wheel.name} contains no _native.abi3.so"
        return z.read(name)


@pytest.mark.skipif(not ANDROID_WHEELS, reason="no vendored android wheels in this checkout")
@pytest.mark.parametrize("wheel", ANDROID_WHEELS, ids=lambda p: p.name.split("-")[-1])
def test_vendored_android_wheel_carries_a_client_id(wheel: Path) -> None:
    """The artifact we ship, not the workflow that was supposed to build it."""
    blob = _native_so_bytes(wheel)
    assert CLIENT_ID_SHAPE.search(blob), (
        f"{wheel.name} has NO Google client id baked in. A node from this wheel "
        f"advertises google with an empty client_id and redirects sign-in to "
        f"accounts.google.com with `client_id=` blank, which Google rejects "
        f"(CIRISServer#387). Re-vendor from a wheel built WITH the secrets."
    )


def test_shape_matcher_accepts_a_real_id_and_rejects_a_blank_injection() -> None:
    """Both directions, so a matcher that can never fail is caught."""
    assert CLIENT_ID_SHAPE.search(b"prefix 265812345678-abcdefghij0k.apps.googleusercontent.com suffix")
    # What a blank injection actually leaves behind: the constant is None, so the
    # string is simply absent. A bare domain with no id must not satisfy it.
    assert not CLIENT_ID_SHAPE.search(b"apps.googleusercontent.com")
    assert not CLIENT_ID_SHAPE.search(b"client_id=&redirect_uri=http")
