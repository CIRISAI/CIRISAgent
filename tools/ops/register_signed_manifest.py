#!/usr/bin/env python3
"""Push a ciris-build-sign signed manifest to CIRISRegistry.

This is the thin gRPC wrapper that complements `ciris-build-sign sign --tree`
for the agent's CI build registration flow. Replaces the signing+pushing logic
in tools/legacy/register_agent_build.py with a focused 80-line script that
ONLY handles the registry push.

Why split: ciris-build-sign (CIRISVerify v1.8.1+) handles file-tree manifest
generation and Ed25519 + ML-DSA-65 signing. What it does NOT do is push to
the agent-specific CIRISRegistry gRPC endpoint — registry push is a
registry-client concern, not a substrate-primitive concern. This script is
that registry-client wrapper.

Usage:
    ciris-build-sign sign --primitive agent --tree . \\
        --tree-include ciris_engine ciris_adapters ciris_sdk \\
        --tree-exempt-dir __pycache__ .venv \\
        --tree-exempt-ext pyc \\
        --tree-extra-hashes-file build-secrets.json \\
        --binary-version "$VERSION" \\
        --build-id "$GIT_SHA" \\
        --target x86_64-unknown-linux-gnu \\
        --ed25519-seed "$CIRIS_BUILD_ED25519_SEED" \\
        --mldsa-secret "$CIRIS_BUILD_MLDSA_SECRET" \\
        --key-id agent-steward-2026 \\
        --output build-manifest.json

    python tools/ops/register_signed_manifest.py build-manifest.json --modules core

Environment:
    REGISTRY_JWT_SECRET: Required. JWT secret for Registry admin auth.
    REGISTRY_GRPC_ADDR:  Optional. Defaults to 207.148.13.157:50051.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def generate_admin_jwt(jwt_secret: str, jwt_issuer: str = "ciris-registry") -> str:
    """Generate an admin JWT for Registry authentication.

    Identical to the historical implementation in register_agent_build.py
    (HS256, role=1 SYSTEM_ADMIN, 1h expiry) — registry contract unchanged.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": "admin",
        "iss": jwt_issuer,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "role": 1,
        "org_id": "",
    }

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    header_b64 = b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    payload_b64 = b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    message = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(jwt_secret.encode("utf-8"), message, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{b64url(signature)}"


def extract_file_tree_from_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the file-tree extras from a ciris-build-sign signed manifest.

    The CIRISVerify v1.8.1 BuildManifest carries FileTreeExtras when
    `--tree` was passed. Shape:
        {
          "build_id": "...",
          "primitive": "agent",
          "binary_version": "2.7.8.4",
          "build_id": "...",
          "binary_hash": "...",       # tree-root hash
          "extras": {
            "shape": "file-tree",
            "file_count": 1234,
            "files": {"path/to/file.py": "sha256hex", ...},
            "exempt_rules": {...},
          },
          "signatures": {...},
        }

    Returns dict with: file_count, files (the per-file map), tree_root_hash.
    Raises ValueError if the manifest is binary-blob-shaped (no file tree).
    """
    extras = manifest.get("extras") or {}
    if extras.get("shape") != "file-tree":
        raise ValueError(
            f"Manifest extras shape is {extras.get('shape')!r}, expected 'file-tree'. "
            f"Did you pass --tree to ciris-build-sign?"
        )
    files = extras.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("file-tree extras has no 'files' map")
    return {
        "file_count": extras.get("file_count", len(files)),
        "files": files,
        "tree_root_hash": manifest.get("binary_hash") or extras.get("tree_root_hash"),
    }


def push_to_registry(
    manifest_path: Path,
    modules: List[str],
    notes: str = "",
) -> bool:
    """Push a signed manifest to CIRISRegistry via grpcurl.

    Reads the file-tree extras from the signed BuildManifest and packages
    into the registry's existing RegisterBuild RPC payload shape, preserving
    the registry contract while delegating signing to ciris-build-sign.
    """
    jwt_secret = os.environ.get("REGISTRY_JWT_SECRET")
    if not jwt_secret:
        print("Error: REGISTRY_JWT_SECRET environment variable required", file=sys.stderr)
        return False

    addr = os.environ.get("REGISTRY_GRPC_ADDR", "207.148.13.157:50051")

    manifest = json.loads(manifest_path.read_text())
    tree = extract_file_tree_from_manifest(manifest)

    # Manifest hash for the registry — over the canonical {"files": {...}} shape
    # the registry already expects. ciris-build-sign signs the same canonical
    # bytes plus metadata, so the inner hash matches what the registry has
    # historically validated.
    manifest_json = json.dumps({"files": tree["files"]}, separators=(",", ":"))
    manifest_hash = hashlib.sha256(manifest_json.encode()).hexdigest()

    version = manifest.get("binary_version", "")
    build_hash = tree["tree_root_hash"] or manifest_hash

    payload = {
        "build": {
            "build_id": manifest.get("build_id") or str(uuid.uuid4()),
            "version": version,
            "build_hash": build_hash,
            "file_manifest_hash": manifest_hash,
            "file_manifest_count": tree["file_count"],
            "file_manifest_json": base64.b64encode(manifest_json.encode()).decode("ascii"),
            "includes_modules": modules or ["core"],
            "source_repo": manifest.get("source_repo", ""),
            "source_commit": manifest.get("source_commit", "") or manifest.get("build_id", ""),
            "registered_at": int(datetime.now(timezone.utc).timestamp()),
            "registered_by": "register_signed_manifest.py",
            "status": "active",
            "notes": notes,
        }
    }

    print(f"Registering signed build manifest with Registry at {addr}")
    print(f"  Version: {version}")
    print(f"  Build hash: {build_hash[:16]}…")
    print(f"  Files: {tree['file_count']}")
    print(f"  Modules: {payload['build']['includes_modules']}")

    token = generate_admin_jwt(jwt_secret)
    payload_json = json.dumps(payload)

    cmd = [
        "grpcurl",
        "-plaintext",
        "-H",
        f"Authorization: Bearer {token}",
        "-d",
        "@",
        addr,
        "ciris.registry.v1.RegistryAdminService/RegisterBuild",
    ]
    try:
        result = subprocess.run(cmd, input=payload_json, capture_output=True, text=True)
    except FileNotFoundError:
        print(
            "Error: grpcurl not found. Install with: "
            "go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest",
            file=sys.stderr,
        )
        return False

    output = result.stdout or result.stderr
    print("\nResponse:")
    print(output)

    # Duplicate-key (build already registered) is a successful no-op,
    # mirroring the historical register_agent_build.py contract.
    if result.returncode != 0 and "duplicate key" in output:
        print(f"\n✓ Build {version} already registered (idempotent skip)")
        return True
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Push a ciris-build-sign signed manifest to CIRISRegistry.",
    )
    parser.add_argument(
        "manifest_path",
        type=Path,
        help="Path to the signed build-manifest.json from ciris-build-sign --tree.",
    )
    parser.add_argument(
        "--modules",
        nargs="+",
        default=["core"],
        help="Modules included in this build (default: core).",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Optional notes to record with the build.",
    )
    args = parser.parse_args()

    if not args.manifest_path.exists():
        print(f"Error: manifest not found: {args.manifest_path}", file=sys.stderr)
        return 2

    ok = push_to_registry(args.manifest_path, modules=args.modules, notes=args.notes)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
