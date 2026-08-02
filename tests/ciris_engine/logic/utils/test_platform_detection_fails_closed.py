"""An unidentified platform gets NO capabilities (CIRISAgent#948).

``detect_platform_capabilities`` used to route anything that was not android or
ios into ``_detect_desktop_capabilities()`` via a bare ``else``, so a host the
runtime could not classify received the desktop set — including
``DESKTOP_CLI``, the requirement that gates shell execution and file writes.
Unknown read as permitted.

The correct pattern was already in the same module: ``is_desktop()`` tests
membership in ``DESKTOP_PLATFORM_NAMES``, so ``"unknown"`` is denied by
construction rather than by a branch someone has to remember to write. These
tests pin the two onto the same footing.

Per the issue, the platform is simulated through the real environment signals
rather than by patching the predicate, so the predicate itself is exercised.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

from ciris_engine.logic.utils.platform_detection import (
    DESKTOP_PLATFORM_NAMES,
    PlatformRequirement,
    detect_platform_capabilities,
    get_platform_name,
    is_desktop,
)

# Signals get_platform_name() consults; all must be absent to reach "unknown".
_PLATFORM_ENV = ("ANDROID_ROOT", "ANDROID_DATA", "IOS_SIMULATOR_HOME")


def _unknown_platform():  # type: ignore[no-untyped-def]
    """Force get_platform_name() down its "unknown" path via real signals."""
    env = {k: v for k, v in os.environ.items() if k not in _PLATFORM_ENV}
    return patch.dict(os.environ, env, clear=True), patch.object(sys, "platform", "vms")


class TestUnknownPlatformFailsClosed:
    def test_unknown_platform_gets_no_capabilities(self) -> None:
        env_patch, plat_patch = _unknown_platform()
        with env_patch, plat_patch:
            detect_platform_capabilities.cache_clear()
            caps = detect_platform_capabilities()
            assert caps.platform == "unknown"
            assert caps.capabilities == set()
        detect_platform_capabilities.cache_clear()

    def test_unknown_platform_is_not_granted_desktop_cli(self) -> None:
        """The specific grant that made this a security defect and not a nit.

        DESKTOP_CLI gates the CLI adapter's shell_command / write_file tools.
        """
        env_patch, plat_patch = _unknown_platform()
        with env_patch, plat_patch:
            detect_platform_capabilities.cache_clear()
            caps = detect_platform_capabilities()
            assert PlatformRequirement.DESKTOP_CLI not in caps.capabilities
        detect_platform_capabilities.cache_clear()

    def test_capability_detection_agrees_with_is_desktop(self) -> None:
        """The two predicates must not disagree about the same host.

        is_desktop() has always failed closed. Before #948 capability detection
        did not, so on an unrecognized host is_desktop() said False while the
        capability set said DESKTOP_CLI. Whichever one a caller reached for
        decided whether shell access was allowed.
        """
        env_patch, plat_patch = _unknown_platform()
        with env_patch, plat_patch:
            detect_platform_capabilities.cache_clear()
            caps = detect_platform_capabilities()
            assert is_desktop() is False
            assert (PlatformRequirement.DESKTOP_CLI in caps.capabilities) is is_desktop()
        detect_platform_capabilities.cache_clear()

    def test_a_real_desktop_still_gets_desktop_cli(self) -> None:
        """Failing closed must not cost the recognized case its capabilities."""
        env = {k: v for k, v in os.environ.items() if k not in _PLATFORM_ENV}
        with patch.dict(os.environ, env, clear=True), patch.object(sys, "platform", "linux"):
            detect_platform_capabilities.cache_clear()
            caps = detect_platform_capabilities()
            assert caps.platform in DESKTOP_PLATFORM_NAMES
            assert PlatformRequirement.DESKTOP_CLI in caps.capabilities
        detect_platform_capabilities.cache_clear()

    def test_get_platform_name_reports_unknown(self) -> None:
        """Guards the premise: if this ever stopped returning "unknown", the
        branch added for #948 would be unreachable and the tests above would
        pass while proving nothing."""
        env_patch, plat_patch = _unknown_platform()
        with env_patch, plat_patch:
            assert get_platform_name() == "unknown"
