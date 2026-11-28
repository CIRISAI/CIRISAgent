"""A desktop payload's JRE (<prefix>/jre) is found from the payload's own interpreter."""

from __future__ import annotations

from pathlib import Path

import pytest

from ciris_engine import desktop_launcher as dl


def _payload(tmp_path: Path, windows: bool, jre: bool = True) -> Path:
    interp = tmp_path / ("python/python.exe" if windows else "python/bin/python3")
    interp.parent.mkdir(parents=True)
    interp.write_text("")
    (tmp_path / "payload.json").write_text("{}")
    if jre:
        java = tmp_path / "jre" / "bin" / dl._java_exe_name()
        java.parent.mkdir(parents=True)
        java.write_text("")
        java.chmod(0o755)
    return interp


@pytest.mark.parametrize("windows", [False, True], ids=["posix-layout", "windows-layout"])
def test_the_payload_jre_is_found_from_its_interpreter(tmp_path: Path, windows: bool) -> None:
    interp = _payload(tmp_path, windows)
    assert dl.payload_prefix(str(interp)) == tmp_path
    assert dl.find_payload_jre(str(interp)) == str(tmp_path / "jre" / "bin" / dl._java_exe_name())


def test_no_payload_json_means_no_payload_jre(tmp_path: Path) -> None:
    interp = _payload(tmp_path, windows=False)
    (tmp_path / "payload.json").unlink()
    assert dl.payload_prefix(str(interp)) is None
    assert dl.find_payload_jre(str(interp)) is None


def test_a_headless_payload_has_no_jre(tmp_path: Path) -> None:
    interp = _payload(tmp_path, windows=False, jre=False)
    assert dl.find_payload_jre(str(interp)) is None


def test_find_java_prefers_the_payload_jre_over_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    interp = _payload(tmp_path, windows=False)
    monkeypatch.setattr(dl.sys, "executable", str(interp))
    monkeypatch.setattr(dl, "find_bundled_jre", lambda: None)
    monkeypatch.setenv("JAVA_HOME", str(tmp_path / "elsewhere"))
    assert dl.find_java() == str(tmp_path / "jre" / "bin" / dl._java_exe_name())
