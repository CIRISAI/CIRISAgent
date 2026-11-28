"""The desktop payload builder: pins, payload.json, and refusing a bad download.

The real build and the run-from-another-prefix check are CI's build-desktop-payload
job; these cover what that job cannot show failing.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("build_desktop_payload", ROOT / "tools" / "dev" / "build_desktop_payload.py")
assert _spec
assert _spec.loader
bdp = importlib.util.module_from_spec(_spec)
sys.modules["build_desktop_payload"] = bdp
_spec.loader.exec_module(bdp)

TARGETS = {"windows-x86_64", "macos-arm64", "macos-x86_64", "linux-x86_64", "linux-aarch64"}


def test_every_agreed_target_is_pinned_by_sha256() -> None:
    pins = bdp.load_pins()
    assert set(pins["targets"]) == TARGETS
    for target, pin in pins["targets"].items():
        assert re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]), target
        assert pin["file"].startswith(f"cpython-{pins['python_version']}+{pins['release']}-"), target
        assert pin["file"].endswith("-install_only.tar.gz"), target
        assert pin["interpreter"] == ("python/python.exe" if target.startswith("windows") else "python/bin/python3")
        # A desktop target needs a client wheel to take the JAR from; a headless one has none.
        assert bool(pin["client_platform"]) == pin["desktop"], target


def test_a_download_that_does_not_match_its_pin_is_refused(tmp_path: Path) -> None:
    f = tmp_path / "python.tar.gz"
    f.write_bytes(b"not the pinned build")
    with pytest.raises(SystemExit, match="Refusing"):
        bdp.verify_sha256(f, "0" * 64)
    bdp.verify_sha256(f, bdp.sha256_of(f))  # and the right hash passes


def _manifest(target: str) -> dict:
    pins = bdp.load_pins()
    return bdp.payload_manifest(
        target=target,
        pin=pins["targets"][target],
        pins=pins,
        versions={"ciris-agent": "2.24.0", "ciris-server": "0.5.255", "ciris-client": "0.5.244"},
        wheel=Path("ciris_agent-2.24.0-py3-none-win_amd64.whl"),
        wheel_sha256="a" * 64,
        commit="abc",
        jre=pins["targets"][target]["desktop"],
    )


@pytest.mark.parametrize("target", sorted(TARGETS))
def test_payload_json_argv_is_relative_and_module_form(target: str) -> None:
    m = _manifest(target)
    interp = m["interpreter"]
    assert not Path(interp).is_absolute()
    assert ":" not in interp
    # Module form: console scripts carry the build machine's absolute path.
    assert m["launch_argv"] == [interp, "-m", "ciris_engine.cli"]
    assert m["upgrade_argv"] == [interp, "-m", "ciris_engine.cli", "upgrade"]
    assert m["console_scripts_relocatable"] is False
    assert m["signed"] is False  # Eric 2026-11-27: unsigned for testing
    assert m["desktop"] is (target != "linux-aarch64")
    # A desktop payload carries its own Java at <prefix>/jre; the launcher looks there.
    assert m["jre"] == ("jre" if m["desktop"] else None)


def test_the_jre_modules_match_the_old_windows_installer() -> None:
    """One module list for the desktop JAR, whichever installer bundles the JRE."""
    ps1 = (ROOT / "installers" / "windows" / "bundle-jre.ps1").read_text(encoding="utf-8")
    block = ps1[ps1.index("$modules = @(") : ps1.index(") -join")]
    assert re.findall(r'"([a-z.]+)"', block) == bdp.load_pins()["jre_modules"]


def test_a_desktop_target_without_a_jdk_stops_the_build(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="jlink"):
        bdp.jlink(tmp_path / "no-jdk", ["java.base"], tmp_path / "jre")


def test_the_upgrade_argv_matches_what_the_agent_reports() -> None:
    """payload.json and /v1/system/health must name the same upgrade command."""
    from ciris_engine.upgrade import upgrade_argv

    m = _manifest("linux-x86_64")
    assert m["upgrade_argv"][1:] == upgrade_argv("/x/python3")[1:]


def test_pack_and_unpack_keep_layout_and_symlinks(tmp_path: Path) -> None:
    pytest.importorskip("zstandard")
    prefix = tmp_path / "prefix"
    (prefix / "python" / "bin").mkdir(parents=True)
    (prefix / "python" / "bin" / "python3.12").write_text("interp")
    (prefix / "python" / "bin" / "python3").symlink_to("python3.12")
    (prefix / "payload.json").write_text("{}")
    archive = tmp_path / "p.tar.zst"
    bdp.pack(prefix, archive)
    dest = tmp_path / "moved prefix"
    bdp.unpack(archive, dest)
    assert (dest / "payload.json").read_text() == "{}"
    assert (dest / "python" / "bin" / "python3").is_symlink()
    assert (dest / "python" / "bin" / "python3").read_text() == "interp"


def _probe(tmp_path: Path, guard: bool) -> subprocess.CompletedProcess:
    """Start a Python whose site-packages may carry the guard, with a user site holding a package."""
    userbase = tmp_path / "userbase"
    env = dict(os.environ, PYTHONUSERBASE=str(userbase))
    env.pop("PYTHONNOUSERSITE", None)
    user_site = Path(
        subprocess.run([sys.executable, "-c", "import site; print(site.getusersitepackages())"], env=env, text=True, capture_output=True, check=True).stdout.strip()
    )
    user_site.mkdir(parents=True, exist_ok=True)
    (user_site / "ciris_user_site_probe.py").write_text("", encoding="utf-8")
    sp = tmp_path / "site-packages"
    sp.mkdir()
    if guard:
        bdp.install_user_site_guard(sp)
    code = (
        "import site, sys; site.addsitedir(sys.argv[1]); "
        "import importlib.util; print(importlib.util.find_spec('ciris_user_site_probe') is not None)"
    )
    return subprocess.run([sys.executable, "-c", code, str(sp)], env=env, text=True, capture_output=True, check=True)


def test_the_guard_keeps_the_user_site_out(tmp_path: Path) -> None:
    assert _probe(tmp_path, guard=True).stdout.strip() == "False"


def test_without_the_guard_the_user_site_leaks_in(tmp_path: Path) -> None:
    """Negative control: the probe does see the user site when nothing stops it."""
    if sys.flags.no_user_site:
        pytest.skip("this interpreter runs with the user site off")
    assert _probe(tmp_path, guard=False).stdout.strip() == "True"
