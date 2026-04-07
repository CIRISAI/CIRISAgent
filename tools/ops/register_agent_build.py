#!/usr/bin/env python3
"""
Register a CIRISAgent build with the CIRIS Registry.

This script:
1. Hashes the agent build artifact (Docker image digest or wheel file)
2. Creates a RegisterAgentRequest payload
3. Calls the RegistryAdminService/RegisterAgent gRPC endpoint

For build registration with file manifests:
  # Register a build with full file manifest
  python tools/ops/register_agent_build.py --build /path/to/CIRISAgent

Usage:
  # Register a test agent
  python tools/ops/register_agent_build.py --test

  # Register from Docker image
  python tools/ops/register_agent_build.py --docker ghcr.io/cirisai/ciris-agent:latest

  # Register from wheel file
  python tools/ops/register_agent_build.py --wheel dist/ciris_agent-1.8.0-py3-none-any.whl

Environment:
  REGISTRY_JWT_SECRET: Required. The JWT secret for Registry API (same as in registry .env).
  REGISTRY_GRPC_ADDR: Optional. Defaults to 207.148.13.157:50051
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# File extensions exempt from integrity checking (must match CIRISVerify)
EXEMPT_EXTENSIONS = {".env", ".log", ".audit", ".db", ".sqlite", ".sqlite3", ".pyc", ".pyo"}

# Build-time generated file hashes (not in repo, but included in release builds)
# These are hardcoded because the files are generated from local secrets at build time
# and verified against the manifest at runtime for code integrity.
# To update: run `sha256sum ciris_adapters/wallet/providers/_build_secrets.py` after
# generating the file with `python tools/generate_ios_secrets.py`
BUILD_SECRETS_HASHES = {
    "ciris_adapters/wallet/providers/_build_secrets.py": "45bf41f0408206b39f04257d456e9d346efcb20799c89b694e6149518dd2fb6b",
}

# Directory names exempt from integrity checking (must match CIRISVerify)
# Note: "data" was removed - runtime files (.db, .log) are covered by EXEMPT_EXTENSIONS
# and we need ciris_engine/data/__init__.py etc. in the manifest for mobile verification
EXEMPT_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "logs",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".ruff_cache",
    ".coverage",
    ".tox",
    ".nox",
}


def is_exempt(relative_path: str) -> bool:
    """
    Check if a file path is exempt from integrity checking.
    Must match CIRISVerify's is_exempt logic exactly.
    """
    path = Path(relative_path)

    # Check exempt extensions
    if path.suffix in EXEMPT_EXTENSIONS:
        return True

    # Check if filename itself is exempt (e.g., ".env")
    if path.name in EXEMPT_EXTENSIONS:
        return True

    # Check exempt directories
    for part in path.parts:
        if part in EXEMPT_DIRS:
            return True
        # Wildcard suffix match for *.egg-info
        if part.endswith(".egg-info"):
            return True

    return False


def generate_file_manifest(
    agent_root: Path,
    subdirs: list[str] | None = None,
    extra_hashes: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Generate a file manifest by walking the agent directory and hashing all non-exempt files.
    Returns a dict of {relative_path: sha256_hex_hash} sorted alphabetically by path.
    Must match CIRISVerify's generate_manifest logic exactly.

    Args:
        agent_root: The root directory of the agent (e.g., /path/to/CIRISAgent)
        subdirs: Optional list of subdirectories to include (e.g., ["ciris_engine"]).
                 If None, includes all non-exempt files from agent_root.
        extra_hashes: Optional dict of {relative_path: sha256_hex_hash} to inject into manifest.
                      Used for build-time generated files like _build_secrets.py that aren't
                      in the repo but are included in release builds.
    """
    files: dict[str, str] = {}

    # Inject extra hashes first (e.g., _build_secrets.py)
    if extra_hashes:
        files.update(extra_hashes)

    # Determine which directories to scan
    if subdirs:
        scan_dirs = [agent_root / subdir for subdir in subdirs if (agent_root / subdir).exists()]
    else:
        scan_dirs = [agent_root]

    for scan_dir in scan_dirs:
        for root, dirs, filenames in os.walk(scan_dir):
            # Prune exempt directories from walk
            dirs[:] = [d for d in dirs if d not in EXEMPT_DIRS and not d.endswith(".egg-info")]

            for filename in filenames:
                file_path = Path(root) / filename
                # Always use path relative to agent_root (not scan_dir)
                relative = str(file_path.relative_to(agent_root)).replace("\\", "/")

                if is_exempt(relative):
                    continue

                # Hash the file
                sha256 = hashlib.sha256()
                try:
                    with open(file_path, "rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            sha256.update(chunk)
                    files[relative] = sha256.hexdigest()
                except (PermissionError, IOError) as e:
                    print(f"Warning: Skipping {relative}: {e}")

    # Return sorted dict (BTreeMap equivalent - alphabetical order by path)
    return dict(sorted(files.items()))


def compute_manifest_hash(manifest: dict[str, str]) -> str:
    """
    Compute the manifest hash by concatenating all file hashes in sorted path order.
    Must match CIRISVerify's hash computation exactly:
      SHA256(hash1 || hash2 || ...) where hashes are hex strings in alphabetical path order.
    """
    hasher = hashlib.sha256()
    # Manifest is already sorted, just concatenate hex hashes
    for file_hash in manifest.values():
        hasher.update(file_hash.encode("ascii"))  # Hash the hex string bytes
    return hasher.hexdigest()


def register_build(
    agent_root: Path,
    version: str,
    source_repo: str = "",
    source_commit: str = "",
    modules: list[str] | None = None,
    notes: str = "",
    include_dirs: list[str] | None = None,
) -> bool:
    """Register a build with file manifest via Registry gRPC."""
    jwt_secret = os.environ.get("REGISTRY_JWT_SECRET")
    if not jwt_secret:
        print("Error: REGISTRY_JWT_SECRET environment variable required")
        return False

    addr = os.environ.get("REGISTRY_GRPC_ADDR", "207.148.13.157:50051")

    # Generate file manifest
    if include_dirs:
        print(f"Generating file manifest from: {agent_root} (subdirs: {include_dirs})")
    else:
        print(f"Generating file manifest from: {agent_root}")
    # Include build-time generated secrets file hash (not in repo but in release builds)
    manifest = generate_file_manifest(agent_root, subdirs=include_dirs, extra_hashes=BUILD_SECRETS_HASHES)
    manifest_hash = compute_manifest_hash(manifest)
    manifest_json = json.dumps({"files": manifest}, separators=(",", ":"))

    # Compute build_hash (same as manifest_hash for now, identifies the build)
    build_hash = manifest_hash

    print(f"  Files in manifest: {len(manifest)}")
    print(f"  Manifest hash: {manifest_hash[:16]}...")

    # Generate admin JWT
    token = generate_admin_jwt(jwt_secret)

    # Build the request payload
    payload = {
        "build": {
            "build_id": str(uuid.uuid4()),
            "version": version,
            "build_hash": build_hash,
            "file_manifest_hash": manifest_hash,
            "file_manifest_count": len(manifest),
            "file_manifest_json": base64.b64encode(manifest_json.encode()).decode("ascii"),
            "includes_modules": modules or ["core"],
            "source_repo": source_repo,
            "source_commit": source_commit,
            "registered_at": int(datetime.now(timezone.utc).timestamp()),
            "registered_by": "register_agent_build.py",
            "status": "active",
            "notes": notes,
        }
    }

    print(f"\nRegistering build with Registry at {addr}")
    print(f"  Version: {version}")
    print(f"  Build hash: {build_hash[:16]}...")
    print(f"  Modules: {modules or ['core']}")

    # Serialize payload
    payload_json = json.dumps(payload)

    try:
        # Call grpcurl with stdin input (payload too large for command line)
        cmd = [
            "grpcurl",
            "-plaintext",
            "-H",
            f"Authorization: Bearer {token}",
            "-d",
            "@",  # Read from stdin
            addr,
            "ciris.registry.v1.RegistryAdminService/RegisterBuild",
        ]

        result = subprocess.run(cmd, input=payload_json, capture_output=True, text=True)
        output = result.stdout or result.stderr
        print("\nResponse:")
        print(output)

        # Handle duplicate key as success (build already registered)
        if result.returncode != 0 and "duplicate key" in output:
            print(f"\n✓ Build {version} already registered (skipping)")
            return True

        return result.returncode == 0
    except FileNotFoundError:
        print("Error: grpcurl not found. Install with: go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest")
        return False


def get_docker_digest(image: str) -> str:
    """Get SHA256 digest from Docker image."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", image],
            capture_output=True,
            text=True,
            check=True,
        )
        # Docker ID is sha256:abc123...
        digest = result.stdout.strip()
        if digest.startswith("sha256:"):
            return digest[7:]  # Return just the hex
        return digest
    except subprocess.CalledProcessError:
        # Try pulling first
        subprocess.run(["docker", "pull", image], check=True)
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", image],
            capture_output=True,
            text=True,
            check=True,
        )
        digest = result.stdout.strip()
        return digest[7:] if digest.startswith("sha256:") else digest


def get_file_hash(path: Path) -> str:
    """Get SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_git_info() -> tuple[str, str]:
    """Get current git repo and commit."""
    try:
        repo = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return repo, commit
    except subprocess.CalledProcessError:
        return "https://github.com/CIRISAI/CIRISAgent", "unknown"


def get_version() -> tuple[int, int, int]:
    """Extract version from constants.py."""
    try:
        constants_path = Path(__file__).parent.parent.parent / "ciris_engine" / "constants.py"
        with open(constants_path) as f:
            for line in f:
                if line.startswith("CIRIS_VERSION ="):
                    # Parse: CIRIS_VERSION = "2.0.0-stable" or "1.8.0"
                    version_str = line.split('"')[1]
                    # Strip suffix like -stable, -beta, -rc1
                    version_str = version_str.split("-")[0]
                    parts = version_str.split(".")
                    return int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0
    except Exception:
        pass
    return 0, 0, 1


def generate_admin_jwt(jwt_secret: str, jwt_issuer: str = "ciris-registry") -> str:
    """Generate an admin JWT for Registry authentication."""
    import hmac

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": "admin",
        "iss": jwt_issuer,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "role": 1,  # SYSTEM_ADMIN
        "org_id": "",
    }

    def b64url_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    header_b64 = b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    payload_b64 = b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())

    # Sign using secret string as UTF-8 bytes (NOT base64 decoded)
    message = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(jwt_secret.encode("utf-8"), message, hashlib.sha256).digest()
    signature_b64 = b64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def register_agent(
    agent_hash: str,
    agent_type: int = 99,  # CUSTOM
    version: tuple[int, int, int] = (0, 0, 1),
    capabilities: list[str] | None = None,
    autonomy_tier: int = 1,  # A0_ADVISORY
    source_repo: str = "",
    source_commit: str = "",
    identity_template: str = "default",
    is_test: bool = False,
    test_tag: str = "",
) -> bool:
    """Register agent with Registry via gRPC."""
    jwt_secret = os.environ.get("REGISTRY_JWT_SECRET")
    if not jwt_secret:
        print("Error: REGISTRY_JWT_SECRET environment variable required")
        return False

    addr = os.environ.get("REGISTRY_GRPC_ADDR", "207.148.13.157:50051")

    # Generate admin JWT
    token = generate_admin_jwt(jwt_secret)

    # Convert hash to base64 for protobuf bytes field
    hash_bytes = bytes.fromhex(agent_hash)
    hash_b64 = base64.b64encode(hash_bytes).decode("ascii")

    # Build the request payload
    payload = {
        "agent": {
            "agent_hash": hash_b64,
            "agent_hash_hex": agent_hash,
            "agent_type": agent_type,
            "version": {
                "major": version[0],
                "minor": version[1],
                "patch": version[2],
            },
            "base_capabilities": capabilities or ["domain:general"],
            "max_autonomy_tier": autonomy_tier,
            "build_timestamp": int(datetime.now(timezone.utc).timestamp()),
            "source_repo": source_repo,
            "source_commit": source_commit,
            "identity_template": identity_template,
            "is_test_record": is_test,
            "test_tag": test_tag,
        }
    }

    print(f"Registering agent with Registry at {addr}")
    print(f"  Hash: {agent_hash[:16]}...")
    print(f"  Version: {version[0]}.{version[1]}.{version[2]}")
    print(f"  Type: {agent_type}")
    print(f"  Autonomy Tier: {autonomy_tier}")
    print(f"  Template: {identity_template}")
    print(f"  Test Record: {is_test}")

    # Call grpcurl
    cmd = [
        "grpcurl",
        "-plaintext",
        "-H",
        f"Authorization: Bearer {token}",
        "-d",
        json.dumps(payload),
        addr,
        "ciris.registry.v1.RegistryAdminService/RegisterAgent",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        print("\nResponse:")
        print(result.stdout or result.stderr)
        return result.returncode == 0
    except FileNotFoundError:
        print("Error: grpcurl not found. Install with: go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest")
        return False


def main():
    parser = argparse.ArgumentParser(description="Register CIRISAgent build with Registry")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--docker", help="Docker image to register (e.g., ghcr.io/cirisai/ciris-agent:latest)")
    group.add_argument("--wheel", help="Python wheel file to register")
    group.add_argument("--hash", help="Direct SHA256 hash (hex) to register")
    group.add_argument("--test", action="store_true", help="Register a test agent with random hash")
    group.add_argument(
        "--build", help="Register a build with file manifest from agent directory (e.g., ./ciris_engine)"
    )

    parser.add_argument("--type", type=int, default=99, help="Agent type (1=CIRISCare, 2=CIRISMedical, 99=Custom)")
    parser.add_argument("--autonomy", type=int, default=1, help="Autonomy tier (1=A0_Advisory, 2=A1_Limited, etc)")
    parser.add_argument("--template", default="default", help="Identity template name")
    parser.add_argument("--capabilities", nargs="+", default=["domain:general"], help="Base capabilities")
    parser.add_argument("--test-tag", default="", help="Test tag for cleanup (auto-set for --test)")
    parser.add_argument("--modules", nargs="+", default=["core"], help="Modules included in build (for --build)")
    parser.add_argument("--notes", default="", help="Build notes (for --build)")
    parser.add_argument(
        "--include-dirs",
        nargs="+",
        default=["ciris_engine", "ciris_adapters", "ciris_sdk"],
        help="Directories to include in manifest (for --build), default: ciris_engine ciris_adapters ciris_sdk",
    )

    args = parser.parse_args()

    # Get git info
    repo, commit = get_git_info()
    version = get_version()

    # Handle --build mode separately (uses RegisterBuild endpoint)
    if args.build:
        agent_root = Path(args.build)
        if not agent_root.exists():
            print(f"Error: Agent directory not found: {agent_root}")
            sys.exit(1)

        version_str = f"{version[0]}.{version[1]}.{version[2]}"
        success = register_build(
            agent_root=agent_root,
            version=version_str,
            source_repo=repo,
            source_commit=commit,
            modules=args.modules,
            notes=args.notes,
            include_dirs=args.include_dirs,
        )
        sys.exit(0 if success else 1)

    # Determine hash for RegisterAgent mode
    if args.test:
        # Generate deterministic test hash
        test_data = f"test-agent-{datetime.now(timezone.utc).isoformat()}"
        agent_hash = hashlib.sha256(test_data.encode()).hexdigest()
        is_test = True
        test_tag = args.test_tag or f"test-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        print(f"Generating test agent hash: {agent_hash[:16]}...")
    elif args.docker:
        print(f"Getting digest from Docker image: {args.docker}")
        agent_hash = get_docker_digest(args.docker)
        is_test = bool(args.test_tag)
        test_tag = args.test_tag
    elif args.wheel:
        wheel_path = Path(args.wheel)
        if not wheel_path.exists():
            print(f"Error: Wheel file not found: {wheel_path}")
            sys.exit(1)
        print(f"Hashing wheel file: {wheel_path}")
        agent_hash = get_file_hash(wheel_path)
        is_test = bool(args.test_tag)
        test_tag = args.test_tag
    else:
        agent_hash = args.hash
        is_test = bool(args.test_tag)
        test_tag = args.test_tag

    # Register
    success = register_agent(
        agent_hash=agent_hash,
        agent_type=args.type,
        version=version,
        capabilities=args.capabilities,
        autonomy_tier=args.autonomy,
        source_repo=repo,
        source_commit=commit,
        identity_template=args.template,
        is_test=is_test,
        test_tag=test_tag,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
