"""Coverage tests for ``tree_verify`` (Algorithm A wrapper).

The actual verifier lives in the ciris-server wheel's C-ABI
(``ciris_verify_tree``) and goes out to the registry, so each test mocks at
the FFI seam (``tree_verify._ffi_verify_tree`` for the mapping layer,
``tree_verify._load_verify_ffi_lib`` / a fake CDLL for the ctypes layer) to
keep the suite hermetic and fast.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from ciris_engine.logic.services.infrastructure.authentication.attestation import tree_verify


# ---------------------------------------------------------------------------
# get_default_agent_version


def test_get_default_agent_version_strips_channel_suffix():
    with patch.object(tree_verify, "__name__", tree_verify.__name__):
        # Use a real import path patch so the function-local import resolves.
        with patch.dict(sys.modules, {"ciris_engine.constants": SimpleNamespace(CIRIS_VERSION="2.8.6-stable")}):
            assert tree_verify.get_default_agent_version() == "2.8.6"


def test_get_default_agent_version_no_suffix():
    with patch.dict(sys.modules, {"ciris_engine.constants": SimpleNamespace(CIRIS_VERSION="2.8.6")}):
        assert tree_verify.get_default_agent_version() == "2.8.6"


def test_get_default_agent_version_handles_import_failure():
    fake_module = SimpleNamespace()
    # Without CIRIS_VERSION attribute, the function raises AttributeError → returns None.
    with patch.dict(sys.modules, {"ciris_engine.constants": fake_module}):
        assert tree_verify.get_default_agent_version() is None


# ---------------------------------------------------------------------------
# resolve_install_root


def test_resolve_install_root_explicit_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CIRIS_AGENT_ROOT", str(tmp_path))
    monkeypatch.delenv("CIRIS_HOME", raising=False)
    assert tree_verify.resolve_install_root() == str(tmp_path)


def test_resolve_install_root_ciris_home(tmp_path, monkeypatch):
    # Stage a fake install layout under tmp_path so the is_dir() check passes.
    (tmp_path / "ciris_engine").mkdir()
    monkeypatch.delenv("CIRIS_AGENT_ROOT", raising=False)
    monkeypatch.setenv("CIRIS_HOME", str(tmp_path))
    assert tree_verify.resolve_install_root() == str(tmp_path)


def test_resolve_install_root_ciris_home_skipped_when_no_engine(tmp_path, monkeypatch):
    # CIRIS_HOME without a ciris_engine subdir should fall through to package-relative.
    monkeypatch.delenv("CIRIS_AGENT_ROOT", raising=False)
    monkeypatch.setenv("CIRIS_HOME", str(tmp_path))
    root = tree_verify.resolve_install_root()
    # Package-relative resolution must succeed (we're running inside the repo).
    assert root is not None
    assert "ciris_engine" not in root.split("/")[-1]  # the parent dir, not the package itself


def test_resolve_install_root_package_relative_fallback(monkeypatch):
    monkeypatch.delenv("CIRIS_AGENT_ROOT", raising=False)
    monkeypatch.delenv("CIRIS_HOME", raising=False)
    root = tree_verify.resolve_install_root()
    assert root is not None
    # Should point at the parent of ciris_engine (i.e., the install root).
    import ciris_engine

    expected_root = os.path.dirname(os.path.dirname(os.path.abspath(ciris_engine.__file__)))
    assert root == expected_root


def test_resolve_install_root_returns_none_when_package_missing(monkeypatch):
    monkeypatch.delenv("CIRIS_AGENT_ROOT", raising=False)
    monkeypatch.delenv("CIRIS_HOME", raising=False)
    # Patch the import inside resolve_install_root to raise.
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ciris_engine":
            raise ImportError("simulated")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert tree_verify.resolve_install_root() is None


# ---------------------------------------------------------------------------
# _canonical_tree_walk_rules


def test_canonical_tree_walk_rules_shape():
    inc, exd, exe = tree_verify._canonical_tree_walk_rules()
    assert "ciris_engine" in inc
    assert "ciris_adapters" in inc
    assert "ciris_sdk" in inc
    assert "__pycache__" in exd
    assert "tests" in exd
    assert "pyc" in exe
    assert "md" in exe


# ---------------------------------------------------------------------------
# _load_verify_ffi_lib / _ffi_verify_tree (the ctypes layer)


class _FakeVerifyLib:
    """Stand-in for the wheel's CDLL: scripted rc + result JSON."""

    def __init__(self, rc: int = 0, result_json: Optional[str] = None):
        self._rc = rc
        self._result_json = result_json
        self.freed: List[Any] = []
        self.calls: List[Dict[str, Any]] = []
        # MagicMock wrappers so the loader's argtypes/restype assignments
        # (plain attribute writes on a real CDLL function) don't raise.
        self.ciris_verify_tree = MagicMock(side_effect=self._tree)
        self.ciris_verify_free_string = MagicMock(side_effect=self._free)

    def _tree(self, request_json: bytes, registry_url: bytes, result_out: Any) -> int:
        self.calls.append(
            {
                "request": json.loads(request_json.decode("utf-8")),
                "registry_url": registry_url.decode("utf-8"),
            }
        )
        if self._result_json is not None:
            # ctypes.byref(c_char_p) → _obj is the c_char_p to populate.
            result_out._obj.value = self._result_json.encode("utf-8")
        return self._rc

    def _free(self, ptr: Any) -> None:
        self.freed.append(ptr)


def _patch_lib(lib: Optional[_FakeVerifyLib]):
    return patch.object(tree_verify, "_load_verify_ffi_lib", return_value=lib)


def test_ffi_verify_tree_returns_none_when_lib_unavailable():
    with _patch_lib(None):
        assert tree_verify._ffi_verify_tree({"root": "/tmp"}) is None


def test_ffi_verify_tree_returns_none_on_nonzero_rc():
    lib = _FakeVerifyLib(rc=3)
    with _patch_lib(lib):
        assert tree_verify._ffi_verify_tree({"root": "/tmp"}) is None


def test_ffi_verify_tree_returns_none_on_empty_result():
    lib = _FakeVerifyLib(rc=0, result_json=None)
    with _patch_lib(lib):
        assert tree_verify._ffi_verify_tree({"root": "/tmp"}) is None
    assert lib.freed == []  # nothing to free on an empty result


def test_ffi_verify_tree_returns_none_on_unparseable_result():
    lib = _FakeVerifyLib(rc=0, result_json="not-json{")
    with _patch_lib(lib):
        assert tree_verify._ffi_verify_tree({"root": "/tmp"}) is None
    assert len(lib.freed) == 1  # the C string still gets freed


def test_ffi_verify_tree_returns_none_on_non_object_result():
    lib = _FakeVerifyLib(rc=0, result_json="[1, 2]")
    with _patch_lib(lib):
        assert tree_verify._ffi_verify_tree({"root": "/tmp"}) is None


def test_ffi_verify_tree_round_trips_request_and_result():
    payload = {"valid": True, "files_checked": 3}
    lib = _FakeVerifyLib(rc=0, result_json=json.dumps(payload))
    with _patch_lib(lib):
        result = tree_verify._ffi_verify_tree({"root": "/tmp", "project": "ciris-agent"})
    assert result == payload
    assert lib.calls[0]["request"] == {"root": "/tmp", "project": "ciris-agent"}
    assert lib.calls[0]["registry_url"] == tree_verify.DEFAULT_REGISTRY_URL
    assert len(lib.freed) == 1


def test_load_verify_ffi_lib_returns_none_when_ciris_server_missing(monkeypatch):
    monkeypatch.setattr(tree_verify, "_VERIFY_FFI_LIB", None)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ciris_server":
            raise ImportError("simulated: wheel missing")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert tree_verify._load_verify_ffi_lib() is None


def test_load_verify_ffi_lib_returns_none_when_symbol_missing(monkeypatch):
    monkeypatch.setattr(tree_verify, "_VERIFY_FFI_LIB", None)
    bare_lib = SimpleNamespace()  # no ciris_verify_tree attribute
    fake_server = SimpleNamespace(verify_ffi_path=lambda: "/fake/path.so")
    with patch.dict(sys.modules, {"ciris_server": fake_server}):
        with patch.object(ctypes, "CDLL", return_value=bare_lib):
            assert tree_verify._load_verify_ffi_lib() is None


def test_load_verify_ffi_lib_binds_and_caches(monkeypatch):
    monkeypatch.setattr(tree_verify, "_VERIFY_FFI_LIB", None)
    lib = _FakeVerifyLib()
    fake_server = SimpleNamespace(verify_ffi_path=lambda: "/fake/path.so")
    with patch.dict(sys.modules, {"ciris_server": fake_server}):
        with patch.object(ctypes, "CDLL", return_value=lib) as mock_cdll:
            assert tree_verify._load_verify_ffi_lib() is lib
            # Second call served from the cache — no second CDLL load.
            assert tree_verify._load_verify_ffi_lib() is lib
            assert mock_cdll.call_count == 1


# ---------------------------------------------------------------------------
# run_tree_verify


def test_run_tree_verify_returns_none_when_ffi_unavailable():
    # The wheel/symbol being absent surfaces as _ffi_verify_tree → None.
    with patch.object(tree_verify, "_ffi_verify_tree", return_value=None):
        assert tree_verify.run_tree_verify(agent_version="2.8.6", agent_root="/tmp") is None


def test_run_tree_verify_returns_none_when_inputs_missing(monkeypatch):
    monkeypatch.delenv("CIRIS_AGENT_ROOT", raising=False)
    monkeypatch.delenv("CIRIS_HOME", raising=False)
    # Make resolve_install_root return None and version unavailable.
    with patch.object(tree_verify, "resolve_install_root", return_value=None):
        with patch.object(tree_verify, "get_default_agent_version", return_value=None):
            assert tree_verify.run_tree_verify() is None


def _stub_verify_tree_result(**overrides) -> Dict[str, Any]:
    """Build a dict mimicking the JSON-decoded TreeVerifyResult.

    ``missing_files`` carries files in the manifest but not on disk.
    Defaults empty; tests that exercise the platform-asymmetric case
    override.
    """
    defaults: Dict[str, Any] = dict(
        valid=True,
        files_checked=120,
        files_passed=120,
        failed_files=[],
        missing_files=[],
        total_hash="sha256:abc",
        expected_total_hash="sha256:abc",
        registry_match=True,
        registry_error=None,
        binary_version="2.8.7",
        project="ciris-agent",
    )
    defaults.update(overrides)
    return defaults


def test_run_tree_verify_happy_path(tmp_path):
    fake_ffi = MagicMock(return_value=_stub_verify_tree_result())

    with patch.object(tree_verify, "_ffi_verify_tree", fake_ffi):
        result = tree_verify.run_tree_verify(agent_version="2.8.7", agent_root=str(tmp_path))

    assert result is not None
    assert result["valid"] is True
    assert result["modules_checked"] == 120
    assert result["modules_passed"] == 120
    assert result["modules_failed"] == 0
    assert result["modules_missing"] == 0
    assert result["registry_match"] is True
    assert result["algorithm"] == "A"
    assert result["binary_version"] == "2.8.7"
    assert result["failed_modules"] == {}
    assert result["missing_modules"] == {}
    # Field names mirror what result_builder._build_python_integrity_fields()
    # reads (Algorithm B-era keys). Wrong names → result_builder writes None
    # to AttestationResult.python_total_hash / .python_hash_valid.
    assert result["actual_total_hash"] == "sha256:abc"
    assert result["expected_total_hash"] == "sha256:abc"
    assert result["total_hash_valid"] is True

    # The FFI request got the canonical rules.
    request = fake_ffi.call_args.args[0]
    assert request["project"] == "ciris-agent"
    assert request["binary_version"] == "2.8.7"
    assert request["root"] == str(tmp_path)
    assert "ciris_engine" in request["include_roots"]
    assert "__pycache__" in request["exempt_dirs"]
    assert "pyc" in request["exempt_extensions"]


def test_run_tree_verify_project_is_parameterizable(tmp_path):
    """#754: a sibling substrate can verify its own registered manifest by
    passing project=... — the tree verifier is project-agnostic."""
    fake_ffi = MagicMock(return_value=_stub_verify_tree_result(project="ciris-lens-core"))

    with patch.object(tree_verify, "_ffi_verify_tree", fake_ffi):
        result = tree_verify.run_tree_verify(
            agent_version="0.4.1", agent_root=str(tmp_path), project="ciris-lens-core"
        )

    assert result is not None
    # The override flows straight into the FFI request...
    assert fake_ffi.call_args.args[0]["project"] == "ciris-lens-core"
    # ...and the result echoes the verified project.
    assert result["project"] == "ciris-lens-core"


def test_run_tree_verify_failed_files_captured(tmp_path):
    fake_result = _stub_verify_tree_result(
        valid=False,
        files_passed=118,
        failed_files=[
            {"path": "ciris_engine/foo.py", "kind": "hash_mismatch"},
            {"path": "ciris_adapters/bar.py", "kind": "missing"},
        ],
        registry_match=False,
        registry_error="hash_mismatch",
    )

    with patch.object(tree_verify, "_ffi_verify_tree", MagicMock(return_value=fake_result)):
        result = tree_verify.run_tree_verify(agent_version="2.8.6", agent_root=str(tmp_path))

    assert result is not None
    assert result["valid"] is False
    assert result["registry_match"] is False
    assert result["registry_error"] == "hash_mismatch"
    assert result["failed_modules"] == {
        "ciris_engine/foo.py": "hash_mismatch",
        "ciris_adapters/bar.py": "missing",
    }
    assert result["modules_failed"] == 2  # only failed_files entries
    # total_hash_valid is independent of registry_match — pure hash-equality
    # against expected_total_hash. The stub keeps expected==total here, so
    # this stays True even though registry_match=False.
    assert result["total_hash_valid"] is True


def test_run_tree_verify_missing_files_separate_from_failed(tmp_path):
    """TreeVerifyResult.missing_files lands in `missing_modules`, not
    `failed_modules`. The platform-asymmetric build artifact case
    (e.g., `_build_secrets.py` shipped only by mobile bundles) reports here
    as soft / informational rather than as a hard L4-gating failure.
    CIRISVerify#15 → CIRISAgent#742.
    """
    fake_result = _stub_verify_tree_result(
        valid=True,
        files_passed=119,
        failed_files=[],
        missing_files=[{"path": "ciris_adapters/wallet/providers/_build_secrets.py", "kind": "missing"}],
    )
    with patch.object(tree_verify, "_ffi_verify_tree", MagicMock(return_value=fake_result)):
        result = tree_verify.run_tree_verify(agent_version="2.8.7", agent_root=str(tmp_path))

    assert result is not None
    # No hard failures.
    assert result["modules_failed"] == 0
    assert result["failed_modules"] == {}
    # Missing landed in the soft bucket.
    assert result["modules_missing"] == 1
    assert result["missing_modules"] == {"ciris_adapters/wallet/providers/_build_secrets.py": "missing"}


def test_run_tree_verify_tolerates_absent_file_buckets(tmp_path):
    """A result JSON without failed_files/missing_files keys (defensive
    against older verify builds serializing defaults away) must not raise —
    both buckets stay empty.
    """
    legacy_result = _stub_verify_tree_result()
    del legacy_result["failed_files"]
    del legacy_result["missing_files"]
    with patch.object(tree_verify, "_ffi_verify_tree", MagicMock(return_value=legacy_result)):
        result = tree_verify.run_tree_verify(agent_version="2.8.7", agent_root=str(tmp_path))

    assert result is not None
    assert result["modules_failed"] == 0
    assert result["modules_missing"] == 0
    assert result["failed_modules"] == {}
    assert result["missing_modules"] == {}


def test_run_tree_verify_handles_ffi_exception(tmp_path):
    with patch.object(tree_verify, "_ffi_verify_tree", MagicMock(side_effect=RuntimeError("registry 5xx"))):
        result = tree_verify.run_tree_verify(agent_version="2.8.6", agent_root=str(tmp_path))
    assert result is None
