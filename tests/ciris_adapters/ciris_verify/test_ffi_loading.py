"""Test that CIRISVerify FFI binary loading finds the correct platform library."""

import sys
import types
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


def test_find_binary_skips_wrong_platform_in_module_dir_falls_through_to_wheel(
    monkeypatch, tmp_path
):
    """Wrong-platform binary alone in module_dir must NOT shadow the wheel `.so`.

    The exact regression we have hit repeatedly across platforms: a stray
    macOS `.dylib` (e.g., left over from `tools/update_ciris_verify.py`
    or a previous-platform build) sits in
    `ciris_adapters/ciris_verify/ffi_bindings/`. The Linux loader was
    finding it via cross-suffix fallback and trying to dlopen it, which
    surfaces as `OSError: invalid ELF header` and the agent shutting down
    during setup with `UNSUPPORTED_PLATFORM_CIRIS_VERIFY`.

    The contract: module_dir must only consider the platform-preferred
    suffix. If the right-platform binary isn't there, fall through to
    the wheel-resolved `ciris_verify` site-packages path — don't load a
    wrong-platform binary.
    """
    import ciris_adapters.ciris_verify.ffi_bindings.client as client_module
    from ciris_adapters.ciris_verify.ffi_bindings.client import CIRISVerify

    # module_dir: only the WRONG-platform binary is present (the bug shape).
    module_dir = tmp_path / "module"
    module_dir.mkdir()
    module_file = module_dir / "client.py"
    module_file.write_text("# test module marker\n")
    stray_dylib = module_dir / "libciris_verify_ffi.dylib"
    stray_dylib.write_bytes(b"\xcf\xfa\xed\xfe")  # Mach-O 64 LE magic

    # wheel pkg_dir: has the CORRECT-platform binary. We forge a fake
    # `ciris_verify` package whose `__file__` resolves to this dir.
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    wheel_init = wheel_dir / "__init__.py"
    wheel_init.write_text("")
    wheel_so = wheel_dir / "libciris_verify_ffi.so"
    wheel_so.write_bytes(b"\x7fELF")  # ELF magic

    monkeypatch.setattr(client_module, "__file__", str(module_file))
    monkeypatch.setattr(client_module.platform, "system", lambda: "Linux")
    monkeypatch.setitem(client_module.DEFAULT_BINARY_PATHS, "Linux", [])
    monkeypatch.setattr(CIRISVerify, "_is_ios", staticmethod(lambda: False))
    monkeypatch.setattr(CIRISVerify, "_is_android", staticmethod(lambda: False))

    # Inject a fake `ciris_verify` module whose .__file__ points at wheel_init.
    fake_pkg = types.ModuleType("ciris_verify")
    fake_pkg.__file__ = str(wheel_init)
    monkeypatch.setitem(sys.modules, "ciris_verify", fake_pkg)

    verifier = object.__new__(CIRISVerify)
    selected = CIRISVerify._find_binary(verifier, explicit_path=None)

    assert selected == wheel_so, (
        f"Loader picked {selected}, expected the wheel `.so` at {wheel_so}. "
        "Wrong-platform `.dylib` in module_dir must NOT be returned on Linux; "
        "loader must fall through to the wheel branch."
    )


def test_find_binary_skips_wrong_platform_in_wheel_dir_raises_not_found(
    monkeypatch, tmp_path
):
    """If only a wrong-platform binary is anywhere reachable, raise — don't load it.

    Symmetric to the module_dir case: if the wheel-distributed `ciris_verify`
    site-packages dir somehow has only a wrong-platform binary (shouldn't
    happen given platform-tagged wheels, but defensive), the loader must
    NOT pick it. Better a clean `BinaryNotFoundError` than an opaque
    `OSError: invalid ELF header` at dlopen.
    """
    import ciris_adapters.ciris_verify.ffi_bindings.client as client_module
    from ciris_adapters.ciris_verify.ffi_bindings.client import (
        BinaryNotFoundError,
        CIRISVerify,
    )

    module_dir = tmp_path / "module"
    module_dir.mkdir()
    module_file = module_dir / "client.py"
    module_file.write_text("# test module marker\n")
    # No binary in module_dir.

    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    wheel_init = wheel_dir / "__init__.py"
    wheel_init.write_text("")
    # Only the WRONG-platform binary in the wheel pkg_dir.
    stray_dylib = wheel_dir / "libciris_verify_ffi.dylib"
    stray_dylib.write_bytes(b"\xcf\xfa\xed\xfe")

    monkeypatch.setattr(client_module, "__file__", str(module_file))
    monkeypatch.setattr(client_module.platform, "system", lambda: "Linux")
    monkeypatch.setitem(client_module.DEFAULT_BINARY_PATHS, "Linux", [])
    monkeypatch.setattr(CIRISVerify, "_is_ios", staticmethod(lambda: False))
    monkeypatch.setattr(CIRISVerify, "_is_android", staticmethod(lambda: False))

    fake_pkg = types.ModuleType("ciris_verify")
    fake_pkg.__file__ = str(wheel_init)
    monkeypatch.setitem(sys.modules, "ciris_verify", fake_pkg)

    verifier = object.__new__(CIRISVerify)
    with pytest.raises(BinaryNotFoundError):
        CIRISVerify._find_binary(verifier, explicit_path=None)


def test_verify_binary_integrity_checks_magic():
    """Binary integrity check should verify valid magic bytes."""
    import inspect

    from ciris_adapters.ciris_verify.ffi_bindings.client import CIRISVerify

    src = inspect.getsource(CIRISVerify._verify_binary_integrity)
    # Should check for ELF, Mach-O, and PE magic bytes
    assert "ELF" in src, "should check ELF magic"
    assert "Mach-O" in src or "xfe\\xed" in src or "xcf\\xfa" in src, "should check Mach-O magic"


def test_find_binary_unknown_platform_iterates_all_suffixes(monkeypatch, tmp_path):
    """Codex P2 regression coverage — on non-canonical platforms (Cygwin
    on Windows reports `platform.system() = 'CYGWIN_NT-...'`, MSYS reports
    `'MSYS_NT-...'`, future runtimes ditto), `_get_platform_binary_suffixes`
    returns the default `['.so', '.dylib', '.dll']` because no preferred
    entry matches. Earlier `_find_binary` restricted to `suffixes[0]` (the
    `.so`) which would NEVER find a `.dll` on a Windows-derivative platform
    — even though one is sitting right next to it on disk.

    The fix: only restrict to the single platform-preferred suffix when
    the platform is recognized (Linux/Darwin/Windows). For unknown
    platforms, iterate the full list and let `ctypes.CDLL` pick the one
    that loads. Preserves the regression protection on known platforms
    AND the pre-fix flexibility on unknown ones.
    """
    import ciris_adapters.ciris_verify.ffi_bindings.client as client_module
    from ciris_adapters.ciris_verify.ffi_bindings.client import CIRISVerify

    module_dir = tmp_path / "module"
    module_dir.mkdir()
    module_file = module_dir / "client.py"
    module_file.write_text("# test module marker\n")
    # Only a .dll is present — what a Cygwin/MSYS host on Windows would
    # actually have. On unknown platforms we want the loader to find it.
    dll_lib = module_dir / "libciris_verify_ffi.dll"
    dll_lib.write_bytes(b"MZ\x90\x00")  # PE/COFF magic

    monkeypatch.setattr(client_module, "__file__", str(module_file))
    # Unknown platform name — what Cygwin/MSYS actually report.
    monkeypatch.setattr(client_module.platform, "system", lambda: "CYGWIN_NT-10.0")
    monkeypatch.setitem(client_module.DEFAULT_BINARY_PATHS, "CYGWIN_NT-10.0", [])
    monkeypatch.setattr(CIRISVerify, "_is_ios", staticmethod(lambda: False))
    monkeypatch.setattr(CIRISVerify, "_is_android", staticmethod(lambda: False))

    verifier = object.__new__(CIRISVerify)
    selected = CIRISVerify._find_binary(verifier, explicit_path=None)
    assert selected == dll_lib, (
        f"Unknown platform must iterate all suffixes and find the .dll — "
        f"got {selected}. The single-suffix restriction was a regression "
        f"on Cygwin/MSYS hosts where `platform.system()` doesn't match "
        f"the {{Linux, Darwin, Windows}} allowlist."
    )
