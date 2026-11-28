"""Build and check a desktop payload: a relocatable Python with CIRIS installed in it.

The agent owns the payload; the per-OS installer shells (ciris-server: Inno now,
dmg and deb next) unpack it into an install prefix and copy ``payload.json`` as
their record of what is installed. Agreed with the server session 2026-11-27.

Archive ``ciris-payload-<version>-<target>.tar.zst`` unpacks straight into the
prefix (no top-level directory):

    python/          python-build-standalone install_only, pinned in installers/payload/python.json
    jre/             desktop targets only: Java 17 jlinked from a JDK (--jdk / JAVA_HOME)
    payload.lock     every dependency with its sha256s (uv pip compile --generate-hashes)
    payload.json     versions, and argv relative to the prefix

Console scripts (``bin/ciris-agent``, ``Scripts\\ciris-agent.exe``) carry the
absolute path of the build machine's interpreter and do NOT survive being moved.
Shells start CIRIS with ``launch_argv`` (module form), never the script. After
the first ``ciris-agent upgrade`` pip rewrites them for the real prefix.

    build_desktop_payload.py stage --target linux-x86_64 --wheel dist/ciris_agent-*.whl --out out/
    build_desktop_payload.py smoke out/ciris-payload-2.24.0-linux-x86_64.tar.zst

Installers ship unsigned for now (Eric, 2026-11-27): ``payload.json`` says so.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
PINS = ROOT / "installers" / "payload" / "python.json"
SCHEMA = 1


def load_pins(path: Path = PINS) -> Dict[str, Any]:
    pins: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return pins


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    got = sha256_of(path)
    if got != expected:
        raise SystemExit(f"{path.name}: sha256 {got} != pinned {expected}. Refusing to use it.")


def payload_manifest(
    *,
    target: str,
    pin: Dict[str, Any],
    pins: Dict[str, Any],
    versions: Dict[str, Optional[str]],
    wheel: Path,
    wheel_sha256: str,
    commit: str,
    jre: bool = False,
) -> Dict[str, Any]:
    """What payload.json says. Paths are relative to the prefix holding payload.json."""
    interp = str(pin["interpreter"])
    return {
        "schema": SCHEMA,
        "target": target,
        "agent_version": versions["ciris-agent"],
        "server_version": versions["ciris-server"],
        "client_version": versions["ciris-client"],
        "python_version": pins["python_version"],
        "desktop": bool(pin["desktop"]),
        "jre": "jre" if jre else None,
        "interpreter": interp,
        "launch_argv": [interp, "-m", "ciris_engine.cli"],
        "upgrade_argv": [interp, "-m", "ciris_engine.cli", "upgrade"],
        "paths_relative_to": "the directory holding payload.json",
        "console_scripts_relocatable": False,
        "user_site": False,
        "agent_wheel": {"file": wheel.name, "sha256": wheel_sha256},
        "python_build": {"release": pins["release"], "file": pin["file"], "sha256": pin["sha256"]},
        "source_commit": commit,
        "signed": False,
    }


def _filter(member: tarfile.TarInfo) -> tarfile.TarInfo:
    member.uid = member.gid = 0
    member.uname = member.gname = ""
    return member


def pack(prefix: Path, archive: Path) -> None:
    """Write prefix's contents to a .tar.zst, entries sorted, owners cleared."""
    import zstandard

    entries = sorted(p for p in prefix.rglob("*"))
    with archive.open("wb") as raw:
        with zstandard.ZstdCompressor(level=19, threads=-1).stream_writer(raw) as zw:
            with tarfile.open(fileobj=zw, mode="w|") as tar:
                for p in entries:
                    tar.add(p, arcname=p.relative_to(prefix).as_posix(), recursive=False, filter=_filter)


def unpack(archive: Path, dest: Path) -> None:
    import zstandard

    dest.mkdir(parents=True, exist_ok=True)
    with archive.open("rb") as raw:
        with zstandard.ZstdDecompressor().stream_reader(raw) as zr:
            with tarfile.open(fileobj=zr, mode="r|") as tar:
                tar.extractall(dest, filter="tar")


def _run(argv: List[str], **kw: Any) -> str:
    print("+", " ".join(argv), flush=True)
    done = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    if done.returncode != 0:
        print(done.stdout, flush=True)
        raise SystemExit(f"exit {done.returncode}: {' '.join(argv)}")
    return done.stdout


GUARD_PTH = "ciris-no-user-site.pth"
# One line: site runs `import` lines of a .pth in site-packages at every start.
GUARD_LINE = (
    "import site, sys; site.ENABLE_USER_SITE = False; "
    "sys.path[:] = [p for p in sys.path if p != site.USER_SITE]\n"
)


def install_user_site_guard(site_packages: Path) -> Path:
    """Keep the user site (~/.local/lib/pythonX.Y, %APPDATA%\\Python) out of this interpreter.

    The payload's Python is the same version as many system Pythons, so their
    user packages would load into CIRIS, and pip would treat them as installed
    and UNINSTALL them when an upgrade wants another version. That happened on
    the first local build (2026-11-27): 57 packages left ~/.local. Editing
    site.py does nothing (3.11+ runs a frozen copy), and -s / PYTHONNOUSERSITE
    would have to be passed by every launcher and the upgrade relaunch. A .pth in
    our own site-packages runs at every start, whatever started the process.
    """
    guard = site_packages / GUARD_PTH
    guard.write_text(GUARD_LINE, encoding="utf-8")
    return guard


def jlink(jdk: Path, modules: List[str], dest: Path) -> None:
    """A trimmed Java runtime for the desktop JAR, at dest (the prefix's jre/)."""
    exe = jdk / "bin" / ("jlink.exe" if sys.platform == "win32" else "jlink")
    if not exe.is_file():
        raise SystemExit(f"no jlink at {exe}: a desktop payload needs a JDK 17 (--jdk or JAVA_HOME)")
    _run([str(exe), "--add-modules", ",".join(modules), "--output", str(dest), "--strip-debug", "--no-man-pages", "--no-header-files", "--compress=2"])


def _versions(python: Path, isolated: bool = False) -> Dict[str, Optional[str]]:
    code = (
        "import json; from importlib import metadata as m\n"
        "def v(n):\n"
        "    try: return m.version(n)\n"
        "    except Exception: return None\n"
        "print(json.dumps({n: v(n) for n in ('ciris-agent', 'ciris-server', 'ciris-client')}))"
    )
    argv = [str(python), *(["-I"] if isolated else []), "-c", code]
    out: Dict[str, Optional[str]] = json.loads(_run(argv).strip().splitlines()[-1])
    return out


def stage(target: str, wheel: Path, out: Path, requirements: Path, jdk: Optional[Path] = None) -> Path:
    pins = load_pins()
    if target not in pins["targets"]:
        raise SystemExit(f"unknown target {target!r}; known: {sorted(pins['targets'])}")
    pin = pins["targets"][target]
    if wheel.is_dir():
        found = sorted(wheel.glob("ciris_agent-*.whl"))
        if len(found) != 1:
            raise SystemExit(f"expected one ciris_agent wheel in {wheel}, found {[p.name for p in found]}")
        wheel = found[0]
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="ciris-payload-"))
    prefix = work / "prefix"
    prefix.mkdir()

    tarball = work / pin["file"]
    url = pins["base_url"] + pin["file"].replace("+", "%2B")
    print(f"Downloading {url}", flush=True)
    # Pinned https URL, hash-checked next.
    urllib.request.urlretrieve(url, tarball)  # noqa: S310
    verify_sha256(tarball, pin["sha256"])
    with tarfile.open(tarball, "r:gz") as tar:
        tar.extractall(prefix, filter="tar")  # install_only unpacks to python/
    python = prefix / pin["interpreter"]
    if not python.exists():
        raise SystemExit(f"{pin['interpreter']} missing after unpacking {pin['file']}")
    # -I from here on: the build must never see (or uninstall) this machine's user site.
    install_user_site_guard(Path(_run([str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"]).strip()))

    lock = prefix / "payload.lock"
    _run(
        [
            "uv", "pip", "compile", str(requirements),
            "--python", str(python),
            "--generate-hashes", "--no-header", "--no-annotate",
            "-o", str(lock),
        ]
    )  # fmt: skip
    _run([str(python), "-I", "-m", "pip", "install", "--no-deps", "--require-hashes", "--no-warn-script-location", "-r", str(lock)])
    _run([str(python), "-I", "-m", "pip", "install", "--no-deps", "--no-index", "--no-warn-script-location", str(wheel)])
    _run([str(python), "-I", "-m", "pip", "check"])

    if pin["desktop"]:
        jdk = jdk or (Path(os.environ["JAVA_HOME"]) if os.environ.get("JAVA_HOME") else None)
        if jdk is None:
            raise SystemExit(f"{target} is a desktop target and needs a JDK for its jre/ (--jdk or JAVA_HOME)")
        jlink(jdk, list(pins["jre_modules"]), prefix / "jre")

    versions = _versions(python, isolated=True)
    if not all(versions.values()):
        raise SystemExit(f"payload is missing a CIRIS distribution: {versions}")
    manifest = payload_manifest(
        target=target,
        pin=pin,
        pins=pins,
        versions=versions,
        wheel=wheel,
        wheel_sha256=sha256_of(wheel),
        commit=os.environ.get("GITHUB_SHA", "local"),
        jre=bool(pin["desktop"]),
    )
    (prefix / "payload.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    stem = f"ciris-payload-{versions['ciris-agent']}-{target}"
    archive = out / f"{stem}.tar.zst"
    pack(prefix, archive)
    shutil.copyfile(prefix / "payload.json", out / f"{stem}.payload.json")
    shutil.copyfile(lock, out / f"{stem}.payload.lock")
    sums = "".join(f"{sha256_of(p)}  {p.name}\n" for p in sorted(out.glob(f"{stem}*")) if p.name != f"{stem}.SHA256SUMS")
    (out / f"{stem}.SHA256SUMS").write_text(sums, encoding="utf-8")
    print(f"Wrote {archive} ({archive.stat().st_size // (1 << 20)} MiB)")
    shutil.rmtree(work, ignore_errors=True)
    return archive


def smoke(archive: Path) -> None:
    """Unpack somewhere other than where it was built and check it runs from there."""
    dest = Path(tempfile.mkdtemp(prefix="ciris-payload-smoke-")) / "moved prefix"  # a space, as in Program Files
    unpack(archive, dest)
    manifest = json.loads((dest / "payload.json").read_text(encoding="utf-8"))
    python = dest / manifest["interpreter"]
    # A user site with a package in it, so the guard has something to keep out.
    userbase = dest.parent / "userbase"
    env = dict(os.environ, CIRIS_HOME=str(dest.parent / "home"), CIRIS_TRACE_RUN_KIND="qa", PYTHONUSERBASE=str(userbase))
    env.pop("PYTHONNOUSERSITE", None)
    user_site = Path(_run([str(python), "-I", "-c", "import site; print(site.getusersitepackages())"], env=env).strip())
    user_site.mkdir(parents=True, exist_ok=True)
    (user_site / "ciris_user_site_probe.py").write_text("", encoding="utf-8")
    _run([str(python), "-m", "pip", "check"], env=env)
    got = _versions(python)
    want = {k: manifest[f"{k.split('-')[1]}_version"] for k in ("ciris-agent", "ciris-server", "ciris-client")}
    if got != want:
        raise SystemExit(f"installed {got} != payload.json {want}")
    _run([str(python), "-c", "import ciris_engine.constants, ciris_server"], env=env)
    probe = (
        "import importlib.util, site, sys; "
        "assert site.ENABLE_USER_SITE is False, site.ENABLE_USER_SITE; "
        "assert site.USER_SITE not in sys.path, sys.path; "
        "assert importlib.util.find_spec('ciris_user_site_probe') is None, 'user site leaked in'"
    )
    _run([str(python), "-c", probe], env=env)
    upgrade = [str(dest / manifest["upgrade_argv"][0]), *manifest["upgrade_argv"][1:], "--help"]
    _run(upgrade, env=env)
    if manifest["jre"]:
        java = dest / manifest["jre"] / "bin" / ("java.exe" if sys.platform == "win32" else "java")
        _run([str(java), "-version"], env=env)
        # The launcher must pick the payload's own JRE, not the runner's Java.
        code = "import sys; from ciris_engine.desktop_launcher import find_java; j = find_java(); print(j); assert j and j.startswith(sys.argv[1]), j"
        _run([str(python), "-c", code, str(dest / manifest["jre"])], env=env)
    if manifest["desktop"]:
        code = "import ciris_engine, pathlib; p = pathlib.Path(ciris_engine.__file__).parent / 'desktop_app'; jars = sorted(p.glob('CIRIS-*.jar')); print(jars); assert jars"
        _run([str(python), "-c", code], env=env)
    print(f"OK: {archive.name} runs from {dest}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stage")
    s.add_argument("--target", required=True)
    s.add_argument("--wheel", required=True, type=Path)
    s.add_argument("--out", required=True, type=Path)
    s.add_argument("--requirements", type=Path, default=ROOT / "requirements.txt")
    s.add_argument("--jdk", type=Path, help="JDK whose jlink builds jre/ (default: JAVA_HOME)")
    k = sub.add_parser("smoke")
    k.add_argument("archive", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "stage":
        stage(args.target, args.wheel, args.out, args.requirements, args.jdk)
    else:
        smoke(args.archive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
