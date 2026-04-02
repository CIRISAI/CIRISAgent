"""Test that CIRISVerify FFI binary loading finds the correct platform library."""
import platform
from pathlib import Path

import pytest


def test_find_binary_prefers_pip_package():
    """The FFI client should check the pip-installed ciris_verify package first."""
    from ciris_adapters.ciris_verify.ffi_bindings.client import CIRISVerify

    import inspect
    src = inspect.getsource(CIRISVerify._find_binary)
    assert "pip-installed" in src, "pip package check should be first in search order"
    assert src.index("pip-installed") < src.index("system paths"), \
        "pip check should come before system path check"


def test_is_valid_binary_for_platform(tmp_path: Path):
    """Platform validation should reject wrong-platform binaries."""
    from ciris_adapters.ciris_verify.ffi_bindings.client import CIRISVerify

    client = CIRISVerify.__new__(CIRISVerify)

    # ELF header (Linux)
    elf_path = tmp_path / "test_elf.bin"
    elf_path.write_bytes(b"\x7fELF" + b"\x00" * 100)

    # Mach-O header (macOS arm64)
    macho_path = tmp_path / "test_macho.bin"
    macho_path.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 100)

    if platform.system() == "Darwin":
        assert client._is_valid_binary_for_platform(macho_path, "Darwin") is True
        assert client._is_valid_binary_for_platform(elf_path, "Darwin") is False
    elif platform.system() == "Linux":
        assert client._is_valid_binary_for_platform(elf_path, "Linux") is True
        assert client._is_valid_binary_for_platform(macho_path, "Linux") is False
    # tmp_path fixture automatically cleans up after test
