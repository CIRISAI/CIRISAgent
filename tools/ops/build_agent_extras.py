#!/usr/bin/env python3
"""Emit build-secrets.json for ciris-build-sign --tree-extra-hashes-file.

The agent's release builds inject secrets at build time (e.g. wallet
provider keys) into files that don't exist in the source repo. Those files
must still appear in the file-tree manifest so runtime integrity checks
can verify the deployment matches what was signed at build time.

Historical home for this dict: register_agent_build.py BUILD_SECRETS_HASHES.
Now lives here so the data survives the migration to ciris-build-sign while
keeping a single, version-controlled source of truth for the hashes.

Usage in CI:
    python tools/ops/build_agent_extras.py > build-secrets.json
    ciris-build-sign sign --primitive agent --tree . \\
        --tree-extra-hashes-file build-secrets.json ...

To update a hash:
    sha256sum ciris_adapters/wallet/providers/_build_secrets.py
    # paste new hex into BUILD_SECRETS_HASHES below

The shape matches what ciris-build-sign expects: {relative_path: sha256_hex}.
"""

from __future__ import annotations

import json
import sys
from typing import Dict


# Build-time generated file hashes (not in repo, but included in release builds).
# These are hardcoded because the files are generated from local secrets at
# build time and verified against the manifest at runtime for code integrity.
#
# ⚠️ OPERATOR NOTE — 2.7.8.4: the iOS generator (tools/generate_ios_secrets.py)
# was unified with the Android Gradle template (mobile/androidApp/build.gradle
# `generatePythonSecrets` task) so both platforms produce byte-identical output.
# After unifying, this hash WILL drift from real-secret regeneration. To
# update:
#   1. Generate with real secrets:    python tools/generate_ios_secrets.py
#   2. Compute the new hash:          sha256sum ciris_adapters/wallet/providers/_build_secrets.py
#   3. Paste the hex into the dict below.
# The runtime integrity check fails closed if the hash here doesn't match the
# deployed file's hash — so an operator MUST re-pin after secret rotation OR
# any change to the generator template (whichever Python or Gradle).
#
# Test enforcement: tests/tools/test_generate_ios_secrets.py pins the iOS
# generator output to the Android-canonical shape so future drift fails CI.
BUILD_SECRETS_HASHES: Dict[str, str] = {
    "ciris_adapters/wallet/providers/_build_secrets.py": (
        "45bf41f0408206b39f04257d456e9d346efcb20799c89b694e6149518dd2fb6b"
    ),
}


def main() -> int:
    # ciris-build-sign --tree-extra-hashes-file requires the multihash-style
    # `sha256:<hex>` prefix, not bare hex. Cross-fleet convention: see
    # CIRISPersist/tools/legacy/ciris_manifest.py + that repo's CI which
    # emits `sha256:$(sha256sum ...)`. Prefix at emit time so
    # BUILD_SECRETS_HASHES stays a clean {path: hex} dict for human editing
    # while the wire format ships the canonical multihash form.
    prefixed = {path: f"sha256:{hex_hash}" for path, hex_hash in BUILD_SECRETS_HASHES.items()}
    json.dump(prefixed, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
