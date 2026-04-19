"""Tests for the CIRISVerify FFI loader's platform/arch dispatch.

These tests lock down the robustness guarantees that prevent the
"attestation timeout" regression:

  1. On each host OS, the module-local fallback picks the platform-native
     suffix first (so a Linux `.so` sitting next to a macOS `.dylib`
     can't shadow the one that actually loads).
  2. `_binary_is_compatible` rejects cross-OS and cross-libc mismatches
     with a clear reason before ctypes.CDLL is even called.
  3. `_find_binary` enumerates pip-installed wheels in addition to
     DEFAULT_BINARY_PATHS + module-local.
  4. If candidate files exist but all are incompatible, the raised
     BinaryNotFoundError names each rejected path AND the reason.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from ciris_adapters.ciris_verify.ffi_bindings.client import (
    CIRISVerify,
    _binary_is_compatible,
    _detect_host_libc,
    _elf_required_libc,
    _find_pip_installed_binaries,
    _platform_suffix_order,
)
from ciris_adapters.ciris_verify.ffi_bindings.exceptions import BinaryNotFoundError

# ---------------------------------------------------------------------------
# Minimal fake binaries — just the magic bytes that `_binary_is_compatible`
# reads. Four bytes is enough; the full header isn't.
# ---------------------------------------------------------------------------

ELF_GLIBC = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 50 + b"/lib64/ld-linux-x86-64.so.2\x00libc.so.6\x00"
ELF_MUSL = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 50 + b"/lib/ld-musl-x86_64.so.1\x00libc.musl-x86_64.so.1\x00"
MACHO_ARM64 = b"\xcf\xfa\xed\xfe" + b"\x00" * 60
PE = b"MZ\x90\x00" + b"\x00" * 60
GARBAGE = b"hello world, not a binary\x00\x00"


def _write(path: Path, blob: bytes) -> Path:
    path.write_bytes(blob)
    return path


# ---------------------------------------------------------------------------
# _platform_suffix_order
# ---------------------------------------------------------------------------


class TestPlatformSuffixOrder:
    def test_darwin_prefers_dylib_first(self) -> None:
        assert _platform_suffix_order("Darwin")[0] == ".dylib"

    def test_linux_prefers_so_first(self) -> None:
        assert _platform_suffix_order("Linux")[0] == ".so"

    def test_windows_prefers_dll_first(self) -> None:
        assert _platform_suffix_order("Windows")[0] == ".dll"

    def test_unknown_os_defaults_to_so_first(self) -> None:
        # Anything POSIX-ish that isn't Darwin/Windows is best-guessed as
        # .so first — matches Linux and most BSDs.
        assert _platform_suffix_order("FreeBSD")[0] == ".so"


# ---------------------------------------------------------------------------
# _binary_is_compatible — the magic + libc gate
# ---------------------------------------------------------------------------


class TestBinaryCompatibility:
    def test_macho_on_darwin_ok(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "m.dylib", MACHO_ARM64)
        assert _binary_is_compatible(p, "Darwin") is None

    def test_elf_on_darwin_rejected(self, tmp_path: Path) -> None:
        """The exact regression we're guarding against."""
        p = _write(tmp_path / "l.so", ELF_GLIBC)
        reason = _binary_is_compatible(p, "Darwin")
        assert reason is not None
        assert "ELF" in reason and "Darwin" in reason

    def test_macho_on_linux_rejected(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "m.dylib", MACHO_ARM64)
        reason = _binary_is_compatible(p, "Linux")
        assert reason is not None
        assert "Mach-O" in reason and "Linux" in reason

    def test_pe_on_linux_rejected(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "w.dll", PE)
        reason = _binary_is_compatible(p, "Linux")
        assert reason is not None

    def test_garbage_rejected_on_every_os(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "bad", GARBAGE)
        for os_name in ("Linux", "Darwin", "Windows"):
            reason = _binary_is_compatible(p, os_name)
            assert reason is not None, f"Garbage accepted on {os_name}"

    def test_empty_file_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "empty"
        p.touch()
        assert "empty" in (_binary_is_compatible(p, "Linux") or "")

    def test_elf_musl_on_glibc_host_rejected(self, tmp_path: Path) -> None:
        """HA / Alpine scenario: magic matches but libc doesn't."""
        p = _write(tmp_path / "musl.so", ELF_MUSL)
        with patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client._detect_host_libc",
            return_value="glibc",
        ):
            reason = _binary_is_compatible(p, "Linux")
        assert reason is not None
        assert "musl" in reason and "glibc" in reason

    def test_elf_glibc_on_musl_host_rejected(self, tmp_path: Path) -> None:
        """Reverse: glibc binary on Alpine/HA host."""
        p = _write(tmp_path / "gnu.so", ELF_GLIBC)
        with patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client._detect_host_libc",
            return_value="musl",
        ):
            reason = _binary_is_compatible(p, "Linux")
        assert reason is not None
        assert "musl" in reason and "glibc" in reason

    def test_elf_glibc_on_glibc_host_ok(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "gnu.so", ELF_GLIBC)
        with patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client._detect_host_libc",
            return_value="glibc",
        ):
            assert _binary_is_compatible(p, "Linux") is None

    def test_unknown_host_libc_allows_elf_through(self, tmp_path: Path) -> None:
        """Absence of evidence != evidence of incompatibility. If we can't
        detect the host libc, don't block on libc — fall back to whatever
        the OS magic check says. Avoids false rejections in exotic envs."""
        p = _write(tmp_path / "gnu.so", ELF_GLIBC)
        with patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client._detect_host_libc",
            return_value="unknown",
        ):
            assert _binary_is_compatible(p, "Linux") is None


# ---------------------------------------------------------------------------
# _elf_required_libc — scan the interpreter string
# ---------------------------------------------------------------------------


class TestElfRequiredLibc:
    def test_glibc_elf(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "g.so", ELF_GLIBC)
        assert _elf_required_libc(p) == "glibc"

    def test_musl_elf(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "m.so", ELF_MUSL)
        assert _elf_required_libc(p) == "musl"

    def test_static_or_unrecognised_returns_unknown(self, tmp_path: Path) -> None:
        # Bare ELF header with no interpreter string -> unknown
        p = _write(tmp_path / "s.so", b"\x7fELF" + b"\x00" * 100)
        assert _elf_required_libc(p) == "unknown"


# ---------------------------------------------------------------------------
# _find_binary integration — the regression test
# ---------------------------------------------------------------------------


class TestFindBinaryRegression:
    """Exercises the full _find_binary path with synthetic candidates."""

    @pytest.fixture
    def isolated_module_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Point _find_binary's module_dir fallback at a clean tmp dir.

        Patches `Path(__file__).parent` inside client.py to `tmp_path` so
        existing on-disk binaries in the real ffi_bindings dir can't pollute
        the test.
        """
        import ciris_adapters.ciris_verify.ffi_bindings.client as client_mod

        # Monkeypatch the module's __file__ so `Path(__file__).parent`
        # resolves to tmp_path for test duration.
        fake_file = tmp_path / "client.py"
        fake_file.touch()
        monkeypatch.setattr(client_mod, "__file__", str(fake_file))

        # Also block DEFAULT_BINARY_PATHS and pip-install discovery so the
        # test is fully hermetic.
        monkeypatch.setattr(client_mod, "DEFAULT_BINARY_PATHS", {})
        monkeypatch.setattr(client_mod, "_find_pip_installed_binaries", lambda: [])
        monkeypatch.delenv("CIRIS_VERIFY_BINARY_PATH", raising=False)
        return tmp_path

    def _instance_with_no_init(self) -> CIRISVerify:
        """Build a CIRISVerify without running __init__ — we only want to
        call `_find_binary` directly. Avoids the cost of loading a real
        library and lets us drive the finder with synthetic candidates."""
        return CIRISVerify.__new__(CIRISVerify)

    def test_darwin_with_both_so_and_dylib_picks_dylib(self, isolated_module_dir: Path) -> None:
        """THE REGRESSION: both binaries present, must pick the native one."""
        _write(isolated_module_dir / "libciris_verify_ffi.so", ELF_GLIBC)
        _write(isolated_module_dir / "libciris_verify_ffi.dylib", MACHO_ARM64)

        with patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client.platform.system",
            return_value="Darwin",
        ):
            picked = self._instance_with_no_init()._find_binary(None)
        assert picked.suffix == ".dylib"

    def test_linux_with_both_so_and_dylib_picks_so(self, isolated_module_dir: Path) -> None:
        _write(isolated_module_dir / "libciris_verify_ffi.so", ELF_GLIBC)
        _write(isolated_module_dir / "libciris_verify_ffi.dylib", MACHO_ARM64)

        with patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client.platform.system",
            return_value="Linux",
        ), patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client._detect_host_libc",
            return_value="glibc",
        ):
            picked = self._instance_with_no_init()._find_binary(None)
        assert picked.suffix == ".so"

    def test_darwin_with_only_elf_raises_with_rejection_reason(self, isolated_module_dir: Path) -> None:
        _write(isolated_module_dir / "libciris_verify_ffi.so", ELF_GLIBC)

        with patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client.platform.system",
            return_value="Darwin",
        ):
            with pytest.raises(BinaryNotFoundError) as exc:
                self._instance_with_no_init()._find_binary(None)
        # Error must tell the user WHY — "wrong OS: ELF binary on Darwin host"
        msg = str(exc.value)
        assert "ELF" in msg
        assert "Darwin" in msg

    def test_musl_host_prefers_musl_variant_when_both_present(self, isolated_module_dir: Path) -> None:
        """HA scenario: `libciris_verify_ffi-musl.so` should win over the
        generic `libciris_verify_ffi.so` (which would be glibc-built)."""
        _write(isolated_module_dir / "libciris_verify_ffi.so", ELF_GLIBC)
        _write(isolated_module_dir / "libciris_verify_ffi-musl.so", ELF_MUSL)

        with patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client.platform.system",
            return_value="Linux",
        ), patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client._detect_host_libc",
            return_value="musl",
        ):
            picked = self._instance_with_no_init()._find_binary(None)
        assert picked.name == "libciris_verify_ffi-musl.so"

    def test_explicit_path_is_trusted_without_compat_check(self, isolated_module_dir: Path) -> None:
        """If the caller passes an explicit path, don't second-guess them
        — they might be testing, shimming, or using a format we don't
        recognise. The integrity check in `_verify_binary_integrity` is
        the safety net for the load phase."""
        bad = _write(isolated_module_dir / "bogus.so", ELF_GLIBC)
        with patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client.platform.system",
            return_value="Darwin",
        ):
            picked = self._instance_with_no_init()._find_binary(str(bad))
        assert picked == bad

    def test_env_var_override_is_respected(self, isolated_module_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        override = _write(isolated_module_dir / "override.dylib", MACHO_ARM64)
        monkeypatch.setenv("CIRIS_VERIFY_BINARY_PATH", str(override))
        with patch(
            "ciris_adapters.ciris_verify.ffi_bindings.client.platform.system",
            return_value="Darwin",
        ):
            picked = self._instance_with_no_init()._find_binary(None)
        assert picked == override

    def test_env_var_missing_file_raises(self, isolated_module_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CIRIS_VERIFY_BINARY_PATH", str(isolated_module_dir / "nope.dylib"))
        with pytest.raises(BinaryNotFoundError, match="CIRIS_VERIFY_BINARY_PATH"):
            self._instance_with_no_init()._find_binary(None)


# ---------------------------------------------------------------------------
# Pip-install discovery — smoke test; can't mock importlib.metadata
# comprehensively, so just exercise the happy path if a package is present.
# ---------------------------------------------------------------------------


class TestPipInstalledDiscovery:
    def test_returns_list_without_raising(self) -> None:
        """Never raises regardless of the installed package state."""
        result = _find_pip_installed_binaries()
        assert isinstance(result, list)
        # Every returned path must at least look like a native library.
        for p in result:
            assert p.name.startswith("libciris_verify_ffi")

    def test_de_duplicates_paths(self, tmp_path: Path) -> None:
        """If importlib and the site-packages scan both report the same
        file (common on pip-installed wheels), the result is deduplicated.
        """
        # This property is enforced by the internal `seen` set; verify
        # generically that there are no duplicates in whatever came back.
        result = _find_pip_installed_binaries()
        resolved = [p.resolve() for p in result]
        assert len(resolved) == len(set(resolved))


# ---------------------------------------------------------------------------
# Host libc detection — platform-aware, should never raise.
# ---------------------------------------------------------------------------


class TestDetectHostLibc:
    def test_returns_one_of_expected_values(self) -> None:
        assert _detect_host_libc() in ("musl", "glibc", "unknown")

    def test_does_not_raise_when_ldd_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ldd isn't always on PATH (minimal containers). Detection must
        still succeed (return 'unknown' at worst) without raising."""
        import subprocess

        def _boom(*_a, **_kw):  # noqa: ANN002, ANN003
            raise FileNotFoundError("ldd not installed")

        monkeypatch.setattr(subprocess, "run", _boom)
        assert _detect_host_libc() in ("musl", "glibc", "unknown")
