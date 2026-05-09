"""Coverage tests for ``tree_verify`` (Algorithm A wrapper).

The actual ``verify_tree()`` call goes out to the registry, so each test
mocks at the import boundary or at ``ciris_verify.verify_tree`` to keep
the suite hermetic and fast.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
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
# run_tree_verify


def test_run_tree_verify_returns_none_when_ciris_verify_unavailable(monkeypatch):
    # Force the import inside run_tree_verify to fail.
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ciris_verify":
            raise ImportError("simulated v1.13 missing")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert tree_verify.run_tree_verify(agent_version="2.8.6", agent_root="/tmp") is None


def test_run_tree_verify_returns_none_when_inputs_missing(monkeypatch):
    monkeypatch.delenv("CIRIS_AGENT_ROOT", raising=False)
    monkeypatch.delenv("CIRIS_HOME", raising=False)
    # Make resolve_install_root return None and version unavailable.
    with patch.object(tree_verify, "resolve_install_root", return_value=None):
        with patch.object(tree_verify, "get_default_agent_version", return_value=None):
            assert tree_verify.run_tree_verify() is None


def _stub_verify_tree_result(**overrides):
    """Build a SimpleNamespace mimicking ciris_verify.TreeVerifyResult.

    `missing_files` is the v1.14.0+ field for files in the manifest but not
    on disk. Defaults empty; tests that exercise the platform-asymmetric
    case override.
    """
    defaults = dict(
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
    return SimpleNamespace(**defaults)


def test_run_tree_verify_happy_path(tmp_path):
    fake_verify_tree = MagicMock(return_value=_stub_verify_tree_result())
    fake_request_cls = MagicMock(side_effect=SimpleNamespace)
    fake_module = SimpleNamespace(verify_tree=fake_verify_tree, TreeVerifyRequest=fake_request_cls)

    with patch.dict(sys.modules, {"ciris_verify": fake_module}):
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

    # TreeVerifyRequest got the canonical rules.
    call_kwargs = fake_request_cls.call_args.kwargs
    assert call_kwargs["project"] == "ciris-agent"
    assert call_kwargs["binary_version"] == "2.8.7"
    assert "ciris_engine" in call_kwargs["include_roots"]
    assert "__pycache__" in call_kwargs["exempt_dirs"]
    assert "pyc" in call_kwargs["exempt_extensions"]


def test_run_tree_verify_failed_files_captured(tmp_path):
    # FailedFileKind is an enum at runtime (with .value); accept str too for test stubs.
    failed_one = SimpleNamespace(path="ciris_engine/foo.py", kind="hash_mismatch")
    failed_two = SimpleNamespace(path="ciris_adapters/bar.py", kind="missing")
    # Reusing the str kind values directly — production sees enum members whose
    # .value attribute the wrapper unwraps; either path produces the same dict.
    fake_result = _stub_verify_tree_result(
        valid=False,
        files_passed=118,
        failed_files=[failed_one, failed_two],
        registry_match=False,
        registry_error="hash_mismatch",
    )
    fake_module = SimpleNamespace(
        verify_tree=MagicMock(return_value=fake_result),
        TreeVerifyRequest=MagicMock(side_effect=SimpleNamespace),
    )

    with patch.dict(sys.modules, {"ciris_verify": fake_module}):
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
    """v1.14.0+ TreeVerifyResult.missing_files lands in `missing_modules`,
    not `failed_modules`. The platform-asymmetric build artifact case
    (e.g., `_build_secrets.py` shipped only by mobile bundles) reports here
    as soft / informational rather than as a hard L4-gating failure.
    CIRISVerify#15 → CIRISAgent#742.
    """
    missing_one = SimpleNamespace(
        path="ciris_adapters/wallet/providers/_build_secrets.py", kind="missing"
    )
    fake_result = _stub_verify_tree_result(
        valid=True,
        files_passed=119,
        failed_files=[],
        missing_files=[missing_one],
    )
    fake_module = SimpleNamespace(
        verify_tree=MagicMock(return_value=fake_result),
        TreeVerifyRequest=MagicMock(side_effect=SimpleNamespace),
    )
    with patch.dict(sys.modules, {"ciris_verify": fake_module}):
        result = tree_verify.run_tree_verify(agent_version="2.8.7", agent_root=str(tmp_path))

    assert result is not None
    # No hard failures.
    assert result["modules_failed"] == 0
    assert result["failed_modules"] == {}
    # Missing landed in the soft bucket.
    assert result["modules_missing"] == 1
    assert result["missing_modules"] == {
        "ciris_adapters/wallet/providers/_build_secrets.py": "missing"
    }


def test_run_tree_verify_handles_v1_13_compat(tmp_path):
    """If running against a transitional ciris-verify <1.14.0 (no
    `missing_files` attr), the wrapper must not raise — `missing_modules`
    stays empty. Caught by getattr(result, 'missing_files', None) or [].
    """
    legacy_result = _stub_verify_tree_result(missing_files=None)
    # Simulate older API: drop the attr entirely.
    delattr(legacy_result, "missing_files")
    fake_module = SimpleNamespace(
        verify_tree=MagicMock(return_value=legacy_result),
        TreeVerifyRequest=MagicMock(side_effect=SimpleNamespace),
    )
    with patch.dict(sys.modules, {"ciris_verify": fake_module}):
        result = tree_verify.run_tree_verify(agent_version="2.8.7", agent_root=str(tmp_path))

    assert result is not None
    assert result["modules_missing"] == 0
    assert result["missing_modules"] == {}


def test_run_tree_verify_handles_verify_exception(tmp_path):
    fake_module = SimpleNamespace(
        verify_tree=MagicMock(side_effect=RuntimeError("registry 5xx")),
        TreeVerifyRequest=MagicMock(side_effect=SimpleNamespace),
    )
    with patch.dict(sys.modules, {"ciris_verify": fake_module}):
        result = tree_verify.run_tree_verify(agent_version="2.8.6", agent_root=str(tmp_path))
    assert result is None
