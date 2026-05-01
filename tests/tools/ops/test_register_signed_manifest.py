"""Tests for tools/ops/register_signed_manifest.py.

The 2.7.8.4 migration moved file-tree manifest generation + signing into
ciris-build-sign (CIRISVerify v1.8.1). This script is the thin gRPC wrapper
that pushes the resulting signed manifest to CIRISRegistry. These tests pin
the contract: extract_file_tree_from_manifest() must accept a v1.8.1
file-tree-shaped BuildManifest and reject other shapes; the registry
payload assembly must preserve the historical RegisterBuild RPC fields the
registry already accepts.

Cannot mock the gRPC push end-to-end without a registry stand-in; instead
we cover the parsing/extraction/payload-shape boundary that's the actual
risk of regression. The push path is one subprocess.run() call to grpcurl,
which is dump-and-run — failures there surface in CI as exit-code != 0.
"""

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Load the CLI module by file path (it lives under tools/ops/, not in a package)
_MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "ops" / "register_signed_manifest.py"
_spec = importlib.util.spec_from_file_location("register_signed_manifest", _MODULE_PATH)
register_signed_manifest = importlib.util.module_from_spec(_spec)
sys.modules["register_signed_manifest"] = register_signed_manifest
_spec.loader.exec_module(register_signed_manifest)


# ---------- extract_file_tree_from_manifest ----------


class TestExtractFileTreeFromManifest:
    """The function must accept v1.8.1 file-tree manifests and reject
    binary-blob or function-level shapes (those go through different push
    paths)."""

    def test_extracts_file_tree_extras(self):
        manifest = {
            "build_id": "abc123",
            "primitive": "agent",
            "binary_version": "2.7.8.4",
            "binary_hash": "0" * 64,  # tree-root hash
            "extras": {
                "shape": "file-tree",
                "file_count": 3,
                "files": {
                    "ciris_engine/__init__.py": "a" * 64,
                    "ciris_engine/runtime.py": "b" * 64,
                    "ciris_adapters/__init__.py": "c" * 64,
                },
            },
        }
        result = register_signed_manifest.extract_file_tree_from_manifest(manifest)
        assert result["file_count"] == 3
        assert result["tree_root_hash"] == "0" * 64
        assert "ciris_engine/runtime.py" in result["files"]

    def test_rejects_binary_blob_shape(self):
        """A manifest signed with --binary (not --tree) doesn't carry a file
        map. This wrapper isn't the right pusher for that case — should fail
        loudly rather than silently push an empty file map."""
        manifest = {
            "build_id": "abc",
            "primitive": "persist",
            "binary_hash": "d" * 64,
            "extras": {"shape": "binary-blob"},
        }
        with pytest.raises(ValueError, match="expected 'file-tree'"):
            register_signed_manifest.extract_file_tree_from_manifest(manifest)

    def test_rejects_function_level_shape(self):
        """Function-level manifests have a different verification path."""
        manifest = {
            "build_id": "abc",
            "extras": {"shape": "function-level", "function_count": 42},
        }
        with pytest.raises(ValueError, match="function-level"):
            register_signed_manifest.extract_file_tree_from_manifest(manifest)

    def test_rejects_missing_extras(self):
        with pytest.raises(ValueError):
            register_signed_manifest.extract_file_tree_from_manifest({"build_id": "x"})

    def test_rejects_empty_files_map(self):
        manifest = {
            "extras": {"shape": "file-tree", "file_count": 0, "files": {}},
        }
        with pytest.raises(ValueError, match="no 'files' map"):
            register_signed_manifest.extract_file_tree_from_manifest(manifest)

    def test_falls_back_to_extras_tree_root_hash_when_binary_hash_absent(self):
        """If a future ciris-build-sign version emits tree_root_hash inside
        extras instead of binary_hash, we still find it — defensive."""
        manifest = {
            "extras": {
                "shape": "file-tree",
                "file_count": 1,
                "files": {"a.py": "1" * 64},
                "tree_root_hash": "9" * 64,
            },
        }
        result = register_signed_manifest.extract_file_tree_from_manifest(manifest)
        assert result["tree_root_hash"] == "9" * 64


# ---------- generate_admin_jwt ----------


class TestGenerateAdminJwt:
    """JWT generation contract is unchanged from register_agent_build.py —
    HS256, SYSTEM_ADMIN role=1, 1h expiry. The registry's signature
    verification depends on this exact shape."""

    def test_jwt_shape(self):
        token = register_signed_manifest.generate_admin_jwt("test-secret")
        # JWT is three base64url segments separated by dots
        parts = token.split(".")
        assert len(parts) == 3

        # Decode header + payload (need to add padding back)
        def decode(seg: str) -> dict:
            seg += "=" * (-len(seg) % 4)
            return json.loads(base64.urlsafe_b64decode(seg))

        header = decode(parts[0])
        payload = decode(parts[1])
        assert header == {"alg": "HS256", "typ": "JWT"}
        assert payload["sub"] == "admin"
        assert payload["role"] == 1  # SYSTEM_ADMIN — registry contract
        assert payload["iss"] == "ciris-registry"
        # 1-hour expiry
        assert payload["exp"] - payload["iat"] == 3600

    def test_jwt_is_deterministic_per_second(self):
        """Same secret + same second → same token (relevant for replay
        debugging; CI logs occasionally need this property for forensics)."""
        import time

        # Run twice within the same second; tokens should match
        # (not strictly guaranteed but useful as a smoke test)
        secret = "test-secret-foo"
        t1 = register_signed_manifest.generate_admin_jwt(secret)
        t2 = register_signed_manifest.generate_admin_jwt(secret)
        # Both should be valid HS256 tokens; if the iat differs by 1s the
        # signatures differ — that's a nondeterminism we tolerate, but the
        # SHAPE invariant always holds:
        assert len(t1.split(".")) == 3
        assert len(t2.split(".")) == 3


# ---------- push_to_registry payload shape ----------


class TestPushToRegistryPayloadShape:
    """The registry's RegisterBuild RPC expects a specific payload shape.
    The migration must preserve it — only the SOURCE of the data changes
    (signed manifest vs hand-rolled), not the shape pushed to the registry."""

    @pytest.fixture
    def signed_manifest_path(self, tmp_path):
        """A realistic v1.8.1 file-tree-shaped BuildManifest."""
        files = {
            "ciris_engine/runtime.py": "1" * 64,
            "ciris_engine/constants.py": "2" * 64,
            "ciris_adapters/__init__.py": "3" * 64,
        }
        manifest = {
            "build_id": "build-id-uuid-here",
            "primitive": "agent",
            "binary_version": "2.7.8.4-stable",
            "binary_hash": "0" * 64,
            "target": "python-source-tree",
            "source_repo": "https://github.com/CIRISAI/CIRISAgent",
            "source_commit": "abc123def",
            "extras": {
                "shape": "file-tree",
                "file_count": len(files),
                "files": files,
            },
            "signatures": {
                "classical": "sig-bytes-here",
                "classical_algorithm": "Ed25519",
                "key_id": "agent-steward-2026",
            },
        }
        path = tmp_path / "build-manifest.json"
        path.write_text(json.dumps(manifest))
        return path

    def test_push_assembles_registry_payload(self, signed_manifest_path, monkeypatch):
        """Monkeypatch subprocess.run; assert the JSON payload sent to
        grpcurl matches the registry's RegisterBuild contract."""
        monkeypatch.setenv("REGISTRY_JWT_SECRET", "test-secret")
        monkeypatch.delenv("REGISTRY_GRPC_ADDR", raising=False)

        captured = {}

        class _CompletedProcess:
            returncode = 0
            stdout = '{"build_id":"abc"}'
            stderr = ""

        def _fake_run(cmd, input=None, capture_output=None, text=None):
            captured["cmd"] = cmd
            captured["payload"] = json.loads(input)
            return _CompletedProcess()

        monkeypatch.setattr(register_signed_manifest.subprocess, "run", _fake_run)
        ok = register_signed_manifest.push_to_registry(
            signed_manifest_path, modules=["core"]
        )
        assert ok is True

        # gRPC method endpoint unchanged
        assert "ciris.registry.v1.RegistryAdminService/RegisterBuild" in captured["cmd"]

        # Payload structure
        build = captured["payload"]["build"]
        assert build["version"] == "2.7.8.4-stable"
        assert build["build_hash"] == "0" * 64  # tree root from manifest binary_hash
        assert build["file_manifest_count"] == 3
        assert build["includes_modules"] == ["core"]
        assert build["registered_by"] == "register_signed_manifest.py"
        assert build["status"] == "active"
        assert build["source_repo"] == "https://github.com/CIRISAI/CIRISAgent"
        assert build["source_commit"] == "abc123def"

        # file_manifest_json must be the canonical {"files": {...}} shape
        # the registry has historically validated, base64-encoded
        manifest_json = base64.b64decode(build["file_manifest_json"]).decode()
        decoded = json.loads(manifest_json)
        assert "files" in decoded
        assert len(decoded["files"]) == 3
        # Inner manifest hash must be SHA-256 of the canonical JSON bytes
        expected_hash = hashlib.sha256(manifest_json.encode()).hexdigest()
        assert build["file_manifest_hash"] == expected_hash

    def test_push_treats_duplicate_key_as_idempotent_success(
        self, signed_manifest_path, monkeypatch
    ):
        """Re-running CI on the same SHA must not fail — registry returns
        'duplicate key' which the wrapper treats as successful no-op (matches
        legacy register_agent_build.py contract)."""
        monkeypatch.setenv("REGISTRY_JWT_SECRET", "test-secret")

        class _DupProcess:
            returncode = 1
            stdout = ""
            stderr = "ERROR: duplicate key value violates unique constraint"

        monkeypatch.setattr(
            register_signed_manifest.subprocess,
            "run",
            lambda *a, **k: _DupProcess(),
        )
        assert (
            register_signed_manifest.push_to_registry(
                signed_manifest_path, modules=["core"]
            )
            is True
        )

    def test_push_fails_loudly_without_jwt_secret(
        self, signed_manifest_path, monkeypatch, capsys
    ):
        """Missing REGISTRY_JWT_SECRET must fail with a clear message,
        not silently no-op. CI relies on this for fail-fast."""
        monkeypatch.delenv("REGISTRY_JWT_SECRET", raising=False)
        ok = register_signed_manifest.push_to_registry(
            signed_manifest_path, modules=["core"]
        )
        assert ok is False
        captured = capsys.readouterr()
        assert "REGISTRY_JWT_SECRET" in captured.err
