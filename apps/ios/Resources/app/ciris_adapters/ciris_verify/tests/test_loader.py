"""Tests for the CIRISVerify FFI loader's platform/arch dispatch.

NOTE: These tests are obsolete for CIRISVerify v1.6.3+ which moved the loader
functionality to the ciris-verify package. The internal helper functions
(_binary_is_compatible, _detect_host_libc, _elf_required_libc, etc.) no longer
exist in the codebase - they are now part of the ciris-verify package.

The original tests locked down robustness guarantees for cross-platform
binary loading to prevent attestation timeouts from loading wrong binaries.
These guarantees are now enforced by the ciris-verify package itself.
"""

import pytest

pytest.skip(
    "Loader tests obsolete for CIRISVerify v1.6.3+ - internal helpers moved to ciris-verify package",
    allow_module_level=True,
)
