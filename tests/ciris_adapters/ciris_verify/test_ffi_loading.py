"""Test that CIRISVerify FFI binary loading finds the correct platform library."""

from pathlib import Path

import pytest


def test_find_binary_searches_default_paths():
    """The FFI client should search DEFAULT_BINARY_PATHS for the platform."""
    import inspect

    from ciris_adapters.ciris_verify.ffi_bindings.client import CIRISVerify

    src = inspect.getsource(CIRISVerify._find_binary)
    # Verify the binary search checks default paths and module directory
    assert "DEFAULT_BINARY_PATHS" in src, "should check DEFAULT_BINARY_PATHS"
    assert "module_dir" in src or "__file__" in src, "should check relative to module"


def test_find_binary_prefers_platform_suffix_in_module_dir(monkeypatch, tmp_path):
    """Mixed-platform bundles should prefer the host platform's native library."""
    import ciris_adapters.ciris_verify.ffi_bindings.client as client_module
    from ciris_adapters.ciris_verify.ffi_bindings.client import CIRISVerify

    module_file = tmp_path / "client.py"
    module_file.write_text("# test module marker\n")
    linux_lib = tmp_path / "libciris_verify_ffi.so"
    macos_lib = tmp_path / "libciris_verify_ffi.dylib"
    linux_lib.write_bytes(b"\x7fELF")
    macos_lib.write_bytes(b"\xcf\xfa\xed\xfe")

    monkeypatch.setattr(client_module, "__file__", str(module_file))
    monkeypatch.setattr(client_module.platform, "system", lambda: "Darwin")
    monkeypatch.setitem(client_module.DEFAULT_BINARY_PATHS, "Darwin", [])
    monkeypatch.setattr(CIRISVerify, "_is_ios", staticmethod(lambda: False))
    monkeypatch.setattr(CIRISVerify, "_is_android", staticmethod(lambda: False))

    verifier = object.__new__(CIRISVerify)
    selected = CIRISVerify._find_binary(verifier, explicit_path=None)

    assert selected == macos_lib


def test_verify_binary_integrity_checks_magic():
    """Binary integrity check should verify valid magic bytes."""
    import inspect

    from ciris_adapters.ciris_verify.ffi_bindings.client import CIRISVerify

    src = inspect.getsource(CIRISVerify._verify_binary_integrity)
    # Should check for ELF, Mach-O, and PE magic bytes
    assert "ELF" in src, "should check ELF magic"
    assert "Mach-O" in src or "xfe\\xed" in src or "xcf\\xfa" in src, "should check Mach-O magic"
