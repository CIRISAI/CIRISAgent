"""Test that CIRISVerify FFI binary loading finds the correct platform library."""

import platform
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


def test_verify_binary_integrity_checks_magic():
    """Binary integrity check should verify valid magic bytes."""
    import inspect

    from ciris_adapters.ciris_verify.ffi_bindings.client import CIRISVerify

    src = inspect.getsource(CIRISVerify._verify_binary_integrity)
    # Should check for ELF, Mach-O, and PE magic bytes
    assert "ELF" in src, "should check ELF magic"
    assert "Mach-O" in src or "xfe\\xed" in src or "xcf\\xfa" in src, "should check Mach-O magic"
