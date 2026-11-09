"""The accord manifest check fails closed, and its files ship in the package (CC; Eric 2026-11-08)."""

import shutil

import pytest

from ciris_engine.logic.utils import constants


def test_the_shipped_manifest_verifies() -> None:
    constants._verify_accord_manifest_signature()


@pytest.mark.parametrize("missing", ["accord_manifest.json", "accord_manifest.sig", "root_pub.json"])
def test_a_missing_file_refuses_to_run(tmp_path, monkeypatch, missing: str) -> None:
    for f in constants.ACCORD_SEED_DIR.iterdir():
        shutil.copy(f, tmp_path / f.name)
    (tmp_path / missing).unlink()
    monkeypatch.setattr(constants, "ACCORD_SEED_DIR", tmp_path)
    with pytest.raises(RuntimeError, match=missing):
        constants._verify_accord_manifest_signature()


def test_a_tampered_manifest_refuses_to_run(tmp_path, monkeypatch) -> None:
    for f in constants.ACCORD_SEED_DIR.iterdir():
        shutil.copy(f, tmp_path / f.name)
    (tmp_path / "accord_manifest.json").write_bytes(b"{}")
    monkeypatch.setattr(constants, "ACCORD_SEED_DIR", tmp_path)
    with pytest.raises(RuntimeError):
        constants._verify_accord_manifest_signature()


def test_the_wheel_ships_the_seed_files() -> None:
    import re
    from pathlib import Path

    setup_py = (Path(__file__).resolve().parents[4] / "setup.py").read_text(encoding="utf-8")
    assert re.search(r'"seed/\*\.json"', setup_py) and re.search(r'"seed/\*\.sig"', setup_py)


def test_an_a1_hybrid_signature_hands_the_check_to_engine_start(tmp_path, monkeypatch) -> None:
    """With A1's file present the WA-root .sig no longer applies (it retires); the engine-start check runs."""
    for f in constants.ACCORD_SEED_DIR.iterdir():
        shutil.copy(f, tmp_path / f.name)
    (tmp_path / "accord_manifest.sig").write_bytes(b"stale root signature")
    (tmp_path / "accord_manifest.hybrid.json").write_text("{}")
    monkeypatch.setattr(constants, "ACCORD_SEED_DIR", tmp_path)
    constants._verify_accord_manifest_signature()
