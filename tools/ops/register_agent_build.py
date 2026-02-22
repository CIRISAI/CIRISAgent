#!/usr/bin/env python3
"""
Register a CIRISAgent build with the CIRIS Registry.

This script:
1. Hashes the agent build artifact (Docker image digest or wheel file)
2. Creates a RegisterAgentRequest payload
3. Calls the RegistryAdminService/RegisterAgent gRPC endpoint

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
from datetime import datetime, timezone
from pathlib import Path


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
        "org_id": ""
    }

    def b64url_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

    header_b64 = b64url_encode(json.dumps(header, separators=(',', ':'), sort_keys=True).encode())
    payload_b64 = b64url_encode(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode())

    # Sign using secret string as UTF-8 bytes (NOT base64 decoded)
    message = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(jwt_secret.encode('utf-8'), message, hashlib.sha256).digest()
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
        "-H", f"Authorization: Bearer {token}",
        "-d", json.dumps(payload),
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

    parser.add_argument("--type", type=int, default=99, help="Agent type (1=CIRISCare, 2=CIRISMedical, 99=Custom)")
    parser.add_argument("--autonomy", type=int, default=1, help="Autonomy tier (1=A0_Advisory, 2=A1_Limited, etc)")
    parser.add_argument("--template", default="default", help="Identity template name")
    parser.add_argument("--capabilities", nargs="+", default=["domain:general"], help="Base capabilities")
    parser.add_argument("--test-tag", default="", help="Test tag for cleanup (auto-set for --test)")

    args = parser.parse_args()

    # Get git info
    repo, commit = get_git_info()
    version = get_version()

    # Determine hash
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
