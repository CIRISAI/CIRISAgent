"""Console-script shim for the ciris-build-verify Rust binary.

See ``_bin_sign.py`` for the rationale; this module is the verify-side
analog and shares its lookup + execv semantics.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


_BIN_NAME = "ciris-build-verify"


def _binary_path() -> Path:
    pkg_dir = Path(__file__).resolve().parent
    candidates = [
        pkg_dir / "_bin" / _BIN_NAME,
        pkg_dir / "_bin" / f"{_BIN_NAME}.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"ciris-build-verify binary not found in {pkg_dir / '_bin'}. "
        "This indicates a packaging defect; please file an issue at "
        "https://github.com/CIRISAI/CIRISVerify/issues with your platform "
        "and the wheel filename you installed."
    )


def main() -> None:
    binary = _binary_path()
    argv = [str(binary), *sys.argv[1:]]
    if os.name == "nt":
        import subprocess

        sys.exit(subprocess.run(argv).returncode)
    os.execv(str(binary), argv)


if __name__ == "__main__":
    main()
