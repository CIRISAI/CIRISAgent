"""Tests for attestation platform detection module."""

import os
from unittest.mock import patch

import pytest

from ciris_engine.logic.services.infrastructure.authentication.attestation.platform import is_android, is_ios, is_mobile


class TestIsAndroid:
    """Tests for is_android function."""

    def test_android_when_env_set(self):
        """Test detection when ANDROID_ROOT is set."""
        with patch.dict(os.environ, {"ANDROID_ROOT": "/system"}):
            assert is_android() is True

    def test_not_android_when_env_unset(self):
        """Test detection when ANDROID_ROOT is not set."""
        env = os.environ.copy()
        env.pop("ANDROID_ROOT", None)
        with patch.dict(os.environ, env, clear=True):
            assert is_android() is False


class TestIsIOS:
    """Tests for is_ios function."""

    def test_ios_with_framework_path(self):
        """Test detection when CIRIS_IOS_FRAMEWORK_PATH is set."""
        with patch.dict(os.environ, {"CIRIS_IOS_FRAMEWORK_PATH": "/path/to/framework"}):
            assert is_ios() is True

    def test_ios_with_static_link(self):
        """Test detection when CIRIS_IOS_STATIC_LINK is set."""
        with patch.dict(os.environ, {"CIRIS_IOS_STATIC_LINK": "1"}):
            assert is_ios() is True

    def test_not_ios_when_env_unset(self):
        """Test detection when iOS env vars are not set."""
        env = os.environ.copy()
        env.pop("CIRIS_IOS_FRAMEWORK_PATH", None)
        env.pop("CIRIS_IOS_STATIC_LINK", None)
        with patch.dict(os.environ, env, clear=True):
            assert is_ios() is False


class TestIsMobile:
    """Tests for is_mobile function."""

    def test_mobile_on_android(self):
        """Test is_mobile returns True on Android."""
        with patch.dict(os.environ, {"ANDROID_ROOT": "/system"}):
            assert is_mobile() is True

    def test_mobile_on_ios(self):
        """Test is_mobile returns True on iOS."""
        with patch.dict(os.environ, {"CIRIS_IOS_FRAMEWORK_PATH": "/path"}):
            assert is_mobile() is True

    def test_not_mobile_on_desktop(self):
        """Test is_mobile returns False on desktop."""
        env = os.environ.copy()
        env.pop("ANDROID_ROOT", None)
        env.pop("CIRIS_IOS_FRAMEWORK_PATH", None)
        env.pop("CIRIS_IOS_STATIC_LINK", None)
        with patch.dict(os.environ, env, clear=True):
            assert is_mobile() is False
