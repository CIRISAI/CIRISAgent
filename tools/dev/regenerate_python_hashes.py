#!/usr/bin/env python3
"""Regenerate startup_python_hashes.json from the source tree.

Bridge implementation (option A) while CIRISVerify FFI gains a runtime
tree-walking verifier (option B, tracked in CIRISVerify issue). Algorithm
is byte-for-byte identical to the mobile canonical hashing in
client/androidApp/src/main/python/mobile_main.py (`verify_code_integrity`
+ `_save_hashes_to_file`) so desktop, mobile, and CI all produce the
same total_hash for a given source tree.

Run from CI in `.github/workflows/build.yml` immediately before docker
image bake so:
  - the bundled JSON's `agent_version` matches CIRIS_VERSION at build time
  - the JSON's `total_hash` matches what mobile reports at boot
  - the registry's signed file_manifest_json is the source of truth;
    this JSON is a runtime cache for telemetry/attestation
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGES = ["ciris_engine", "ciris_adapters"]
OUTPUT_FILE = REPO_ROOT / "startup_python_hashes.json"
SCHEMA_VERSION = "1.2"


def get_agent_version() -> str:
    constants = (REPO_ROOT / "ciris_engine" / "constants.py").read_text(encoding="utf-8")
    match = re.search(r'CIRIS_VERSION\s*=\s*"([^"]+)"', constants)
    if not match:
        sys.exit("ERROR: CIRIS_VERSION not found in ciris_engine/constants.py")
    return match.group(1)


def hash_packages() -> dict:
    module_hashes: dict[str, str] = {}
    all_hashes: list[str] = []
    modules_checked = 0
    modules_hashed = 0

    for package_name in PACKAGES:
        package_path = REPO_ROOT / package_name
        if not package_path.is_dir():
            sys.exit(f"ERROR: package directory not found: {package_path}")
        for py_file in package_path.rglob("*.py"):
            modules_checked += 1
            rel_path = str(py_file.relative_to(REPO_ROOT)).replace("\\", "/")
            file_hash = hashlib.sha256(py_file.read_bytes()).hexdigest()
            module_hashes[rel_path] = file_hash
            all_hashes.append(f"{rel_path}:{file_hash}")
            modules_hashed += 1

    combined = "\n".join(sorted(all_hashes))
    total_hash = hashlib.sha256(combined.encode()).hexdigest()

    return {
        "module_hashes": module_hashes,
        "modules_checked": modules_checked,
        "modules_hashed": modules_hashed,
        "total_hash": total_hash,
    }


def main() -> int:
    agent_version = get_agent_version()
    results = hash_packages()

    output_data = {
        "version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "computed_at": int(time.time()),
        "agent_version": agent_version,
        "packages": PACKAGES,
        "modules_checked": results["modules_checked"],
        "modules_hashed": results["modules_hashed"],
        "unavailable_count": 0,
        "total_hash": results["total_hash"],
        "module_hashes": results["module_hashes"],
        "unavailable_modules": [],
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output_data, f, indent=2, sort_keys=True)

    print(
        f"Regenerated {OUTPUT_FILE.relative_to(REPO_ROOT)}: "
        f"agent_version={agent_version}, "
        f"modules={results['modules_hashed']}, "
        f"total_hash={results['total_hash'][:16]}..."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
