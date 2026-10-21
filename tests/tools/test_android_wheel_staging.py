"""The shipped Android wheel set must never be left partial.

`apps/android/wheels` is a SHIPPED directory in the checkout, not a cache. There
are two ways a refresh used to leave it broken, and staging alone only closes one:

  1. TRANSIENT FAILURE. It pruned the old wheels first and downloaded the new
     ones one at a time, so a blip on the second of three ABIs deleted the usable
     set and left a partial one, with no recovery path from inside the tool.

  2. INCOMPLETE UPSTREAM RELEASE. The published set is checked with `if not
     android` — nonempty, not complete. A release that ships one ABI of three
     passes that check, and the subset gets installed, pinned, and reported as
     success. The APK then builds fine and fails at import on the devices whose
     ABI is missing, which is a much later and much worse place to find out.

Both must leave `WHEELS_DIR` untouched and report failure.
"""

from __future__ import annotations

import io
import json
import pathlib
import urllib.request

import pytest

import tools.update_substrate_libs as usl

ABIS = ["arm64-v8a", "x86_64", "armeabi-v7a"]


def _meta(version: str, abis: list[str], pkg: str = "ciris_server") -> bytes:
    return json.dumps(
        {
            "urls": [
                {
                    "filename": f"{pkg}-{version}-cp310-abi3-android_24_{a.replace('-', '_')}.whl",
                    "url": f"https://example.invalid/{a}.whl",
                    "size": 10,
                }
                for a in abis
            ]
        }
    ).encode()


@pytest.fixture()
def wheels(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """A live wheels dir holding a COMPLETE older set, as a checkout has."""
    d = tmp_path / "wheels"
    d.mkdir()
    for a in ABIS:
        (d / f"ciris_server-0.5.100-cp310-abi3-android_24_{a.replace('-', '_')}.whl").write_bytes(b"OLD")
    monkeypatch.setattr(usl, "WHEELS_DIR", d)
    monkeypatch.setattr(usl, "REPO_ROOT", tmp_path)
    return d


@pytest.fixture()
def lib() -> usl.SubstrateLib:
    return usl.LIBS["server"]


def _survivors(d: pathlib.Path) -> set[str]:
    return {p.name for p in d.glob("*.whl")}


def test_an_incomplete_release_is_refused_and_nothing_is_pruned(
    wheels: pathlib.Path, lib: usl.SubstrateLib, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One ABI missing upstream. The old complete set must survive intact."""
    before = _survivors(wheels)
    calls = {"n": 0}

    def partial(url, *a, **k):
        # Metadata first, then wheel payloads of exactly the advertised size, so
        # every OTHER check in the function succeeds. If this test can only fail
        # on the ABI guard, it is testing the ABI guard.
        #
        # It is written this way because the first version was NOT: its mock
        # returned the metadata JSON for the download too, so the size check
        # rejected it and the test passed with the guard deleted.
        calls["n"] += 1
        return io.BytesIO(_meta("0.5.200", ["arm64-v8a", "x86_64"]) if calls["n"] == 1 else b"0123456789")

    monkeypatch.setattr(urllib.request, "urlopen", partial)

    assert usl._install_android_wheels_from_pypi(lib, "0.5.200") is False
    assert _survivors(wheels) == before, "the live wheels were modified for a partial release"


def test_a_download_failure_leaves_the_live_set_intact(
    wheels: pathlib.Path, lib: usl.SubstrateLib, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metadata lists every ABI, then the transfer dies. Nothing may be pruned."""
    before = _survivors(wheels)
    calls = {"n": 0}

    def flaky(url, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return io.BytesIO(_meta("0.5.200", ABIS))
        raise OSError("connection reset")

    monkeypatch.setattr(urllib.request, "urlopen", flaky)

    assert usl._install_android_wheels_from_pypi(lib, "0.5.200") is False
    assert _survivors(wheels) == before, "a mid-download failure pruned the usable set"


def test_a_truncated_wheel_is_caught_before_it_ships(
    wheels: pathlib.Path, lib: usl.SubstrateLib, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A short read is a valid file of the wrong length; Chaquopy would only
    fail on it at APK build time."""
    before = _survivors(wheels)
    calls = {"n": 0}

    def short(url, *a, **k):
        calls["n"] += 1
        return io.BytesIO(_meta("0.5.200", ABIS) if calls["n"] == 1 else b"xx")  # size says 10

    monkeypatch.setattr(urllib.request, "urlopen", short)

    assert usl._install_android_wheels_from_pypi(lib, "0.5.200") is False
    assert _survivors(wheels) == before


def test_a_complete_release_replaces_the_set(
    wheels: pathlib.Path, lib: usl.SubstrateLib, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard must not block the good path, or it just stops refreshes."""
    calls = {"n": 0}

    def ok(url, *a, **k):
        calls["n"] += 1
        return io.BytesIO(_meta("0.5.200", ABIS) if calls["n"] == 1 else b"0123456789")  # size 10

    monkeypatch.setattr(urllib.request, "urlopen", ok)

    assert usl._install_android_wheels_from_pypi(lib, "0.5.200") is True
    got = _survivors(wheels)
    assert all("0.5.200" in n for n in got), f"stale wheels survived: {got}"
    assert len(got) == len(ABIS)
