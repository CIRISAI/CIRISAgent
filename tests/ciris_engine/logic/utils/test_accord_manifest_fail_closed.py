"""The accord manifest check fails closed, and its files ship in the package (CC 3.1.2; Eric 2026-11-08).

2.20.0 ships A1's hybrid signature and retires the 2025 WA root, so there is no
classical fallback: a missing A1 signature stops the agent at import and again
when the engine is wired.
"""

import shutil

import pytest

from ciris_engine.logic.utils import constants
from ciris_engine.logic.utils.accord_manifest_hybrid import verify_accord_manifest_hybrid


def _copy_seed(tmp_path, monkeypatch):
    for f in constants.ACCORD_SEED_DIR.iterdir():
        shutil.copy(f, tmp_path / f.name)
    monkeypatch.setattr(constants, "ACCORD_SEED_DIR", tmp_path)
    return tmp_path


def test_the_shipped_seed_passes_the_import_check() -> None:
    constants._verify_accord_manifest_signature()


@pytest.mark.parametrize("missing", ["accord_manifest.json", "accord_manifest.hybrid.json"])
def test_a_missing_file_refuses_to_run(tmp_path, monkeypatch, missing: str) -> None:
    (_copy_seed(tmp_path, monkeypatch) / missing).unlink()
    with pytest.raises(RuntimeError, match=missing):
        constants._verify_accord_manifest_signature()


def test_the_root_signature_is_retired_and_not_shipped() -> None:
    """No accord_manifest.sig and no root_pub.json: nothing can fall back to the 2025 root."""
    assert not (constants.ACCORD_SEED_DIR / "accord_manifest.sig").exists()
    assert not (constants.ACCORD_SEED_DIR / "root_pub.json").exists()


def test_a_root_signature_alone_does_not_start_the_agent(tmp_path, monkeypatch) -> None:
    seed = _copy_seed(tmp_path, monkeypatch)
    (seed / "accord_manifest.hybrid.json").unlink()
    (seed / "accord_manifest.sig").write_bytes(b"a 2025 root signature")
    with pytest.raises(RuntimeError, match="accord_manifest.hybrid.json"):
        constants._verify_accord_manifest_signature()


def test_engine_start_refuses_a_missing_a1_signature(tmp_path) -> None:
    for f in constants.ACCORD_SEED_DIR.iterdir():
        shutil.copy(f, tmp_path / f.name)
    (tmp_path / "accord_manifest.hybrid.json").unlink()
    with pytest.raises(RuntimeError, match="No A1 hybrid manifest signature"):
        verify_accord_manifest_hybrid(object(), tmp_path)


def test_the_wheel_ships_the_seed_files() -> None:
    import re
    from pathlib import Path

    setup_py = (Path(__file__).resolve().parents[4] / "setup.py").read_text(encoding="utf-8")
    assert re.search(r'"seed/\*\.json"', setup_py)
