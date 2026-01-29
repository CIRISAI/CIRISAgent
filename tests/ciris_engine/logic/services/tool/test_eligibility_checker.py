"""Tests for the ToolEligibilityChecker service."""

import os
import sys
from unittest.mock import patch

import pytest

from ciris_engine.logic.services.tool.eligibility_checker import EligibilityResult, ToolEligibilityChecker
from ciris_engine.schemas.adapters.tools import (
    BinaryRequirement,
    ConfigRequirement,
    EnvVarRequirement,
    InstallStep,
    ToolInfo,
    ToolParameterSchema,
    ToolRequirements,
)


def make_tool_info(name: str, description: str, **kwargs) -> ToolInfo:
    """Helper to create ToolInfo with default parameters."""
    return ToolInfo(
        name=name,
        description=description,
        parameters=ToolParameterSchema(type="object", properties={}),
        **kwargs,
    )


class TestEligibilityResult:
    """Tests for EligibilityResult model."""

    def test_eligible_result(self) -> None:
        """Test creating an eligible result."""
        result = EligibilityResult(eligible=True)
        assert result.eligible is True
        assert result.missing_binaries == []
        assert result.missing_env_vars == []
        assert result.missing_config == []
        assert result.platform_mismatch is False
        assert result.install_hints == []
        assert result.reason is None

    def test_ineligible_result_with_details(self) -> None:
        """Test creating an ineligible result with details."""
        result = EligibilityResult(
            eligible=False,
            missing_binaries=["git", "ffmpeg"],
            missing_env_vars=["API_KEY"],
            platform_mismatch=True,
            reason="missing binaries: git, ffmpeg; missing env vars: API_KEY",
        )
        assert result.eligible is False
        assert "git" in result.missing_binaries
        assert "ffmpeg" in result.missing_binaries
        assert "API_KEY" in result.missing_env_vars
        assert result.platform_mismatch is True


class TestToolEligibilityChecker:
    """Tests for ToolEligibilityChecker."""

    def test_no_requirements_is_eligible(self) -> None:
        """Tool with no requirements is always eligible."""
        checker = ToolEligibilityChecker()
        tool = make_tool_info(name="simple_tool", description="A simple tool")

        result = checker.check_eligibility(tool)

        assert result.eligible is True
        assert result.reason is None

    def test_empty_requirements_is_eligible(self) -> None:
        """Tool with empty requirements object is eligible."""
        checker = ToolEligibilityChecker()
        tool = make_tool_info(
            name="simple_tool",
            description="A simple tool",
            requirements=ToolRequirements(),
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is True

    @patch("shutil.which")
    def test_missing_binary_not_eligible(self, mock_which) -> None:
        """Tool with missing binary is not eligible."""
        mock_which.return_value = None  # Binary not found
        checker = ToolEligibilityChecker()
        tool = make_tool_info(
            name="git_tool",
            description="Git operations",
            requirements=ToolRequirements(binaries=[BinaryRequirement(name="git")]),
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is False
        assert "git" in result.missing_binaries
        assert "missing binaries" in (result.reason or "")

    @patch("shutil.which")
    def test_present_binary_is_eligible(self, mock_which) -> None:
        """Tool with present binary is eligible."""
        mock_which.return_value = "/usr/bin/git"  # Binary found
        checker = ToolEligibilityChecker()
        tool = make_tool_info(
            name="git_tool",
            description="Git operations",
            requirements=ToolRequirements(binaries=[BinaryRequirement(name="git")]),
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is True

    @patch("shutil.which")
    def test_any_binaries_one_present(self, mock_which) -> None:
        """Tool is eligible if any of the alternative binaries is present."""

        def which_side_effect(name):
            return "/usr/bin/vim" if name == "vim" else None

        mock_which.side_effect = which_side_effect
        checker = ToolEligibilityChecker()
        tool = make_tool_info(
            name="editor_tool",
            description="Text editing",
            requirements=ToolRequirements(
                any_binaries=[
                    BinaryRequirement(name="vim"),
                    BinaryRequirement(name="nano"),
                    BinaryRequirement(name="emacs"),
                ]
            ),
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is True

    @patch("shutil.which")
    def test_any_binaries_none_present(self, mock_which) -> None:
        """Tool is not eligible if none of the alternative binaries are present."""
        mock_which.return_value = None  # No binaries found
        checker = ToolEligibilityChecker()
        tool = make_tool_info(
            name="editor_tool",
            description="Text editing",
            requirements=ToolRequirements(
                any_binaries=[
                    BinaryRequirement(name="vim"),
                    BinaryRequirement(name="nano"),
                ]
            ),
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is False
        assert "vim" in result.missing_binaries
        assert "nano" in result.missing_binaries

    def test_missing_env_var_not_eligible(self) -> None:
        """Tool with missing env var is not eligible."""
        checker = ToolEligibilityChecker()
        tool = make_tool_info(
            name="api_tool",
            description="API operations",
            requirements=ToolRequirements(env_vars=[EnvVarRequirement(name="NONEXISTENT_API_KEY_12345")]),
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is False
        assert "NONEXISTENT_API_KEY_12345" in result.missing_env_vars
        assert "missing env vars" in (result.reason or "")

    def test_present_env_var_is_eligible(self) -> None:
        """Tool with present env var is eligible."""
        checker = ToolEligibilityChecker()
        tool = make_tool_info(
            name="path_tool",
            description="Path operations",
            requirements=ToolRequirements(env_vars=[EnvVarRequirement(name="PATH")]),  # Always set
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is True

    def test_platform_mismatch_not_eligible(self) -> None:
        """Tool with unsupported platform is not eligible."""
        checker = ToolEligibilityChecker()
        # Use a platform that definitely doesn't match current
        fake_platforms = ["fakeos", "notreal"]
        tool = make_tool_info(
            name="platform_tool",
            description="Platform specific",
            requirements=ToolRequirements(platforms=fake_platforms),
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is False
        assert result.platform_mismatch is True
        assert "not supported" in (result.reason or "")

    def test_matching_platform_is_eligible(self) -> None:
        """Tool with matching platform is eligible."""
        checker = ToolEligibilityChecker()
        current_platform = sys.platform
        tool = make_tool_info(
            name="platform_tool",
            description="Platform specific",
            requirements=ToolRequirements(platforms=[current_platform, "other"]),
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is True

    @patch("shutil.which")
    def test_multiple_requirements_all_met(self, mock_which) -> None:
        """Tool is eligible when all multiple requirements are met."""
        mock_which.return_value = "/usr/bin/git"
        checker = ToolEligibilityChecker()
        tool = make_tool_info(
            name="complex_tool",
            description="Complex operations",
            requirements=ToolRequirements(
                binaries=[BinaryRequirement(name="git")],
                env_vars=[EnvVarRequirement(name="PATH")],
                platforms=[sys.platform],
            ),
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is True

    @patch("shutil.which")
    def test_multiple_requirements_partial_met(self, mock_which) -> None:
        """Tool is not eligible when only some requirements are met."""
        mock_which.return_value = "/usr/bin/git"
        checker = ToolEligibilityChecker()
        tool = make_tool_info(
            name="complex_tool",
            description="Complex operations",
            requirements=ToolRequirements(
                binaries=[BinaryRequirement(name="git")],
                env_vars=[EnvVarRequirement(name="NONEXISTENT_VAR_12345")],
            ),
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is False
        assert "NONEXISTENT_VAR_12345" in result.missing_env_vars

    @patch("shutil.which")
    def test_install_hints_added_for_missing(self, mock_which) -> None:
        """Install hints are provided for missing binaries."""
        mock_which.return_value = None
        checker = ToolEligibilityChecker()
        tool = make_tool_info(
            name="ffmpeg_tool",
            description="Video operations",
            requirements=ToolRequirements(binaries=[BinaryRequirement(name="ffmpeg")]),
            install_steps=[
                InstallStep(
                    id="brew-ffmpeg",
                    kind="brew",
                    label="Install ffmpeg via Homebrew",
                    formula="ffmpeg",
                    provides_binaries=["ffmpeg"],
                    platforms=["darwin"],
                ),
                InstallStep(
                    id="apt-ffmpeg",
                    kind="apt",
                    label="Install ffmpeg via apt",
                    package="ffmpeg",
                    provides_binaries=["ffmpeg"],
                    platforms=["linux"],
                ),
            ],
        )

        result = checker.check_eligibility(tool)

        assert result.eligible is False
        # Should have install hints for current platform
        if sys.platform in ["darwin", "linux"]:
            assert len(result.install_hints) > 0
            assert any("ffmpeg" in h.provides_binaries for h in result.install_hints)

    @patch("shutil.which")
    def test_filter_eligible_tools(self, mock_which) -> None:
        """filter_eligible_tools returns only eligible tools."""

        def which_side_effect(name):
            return "/usr/bin/git" if name == "git" else None

        mock_which.side_effect = which_side_effect
        checker = ToolEligibilityChecker()

        tools = [
            make_tool_info(name="simple", description="No requirements"),
            make_tool_info(
                name="git_tool",
                description="Git",
                requirements=ToolRequirements(binaries=[BinaryRequirement(name="git")]),
            ),
            make_tool_info(
                name="missing_tool",
                description="Missing",
                requirements=ToolRequirements(binaries=[BinaryRequirement(name="nonexistent_binary_xyz")]),
            ),
        ]

        eligible = checker.filter_eligible_tools(tools)

        assert len(eligible) == 2
        names = [t.name for t in eligible]
        assert "simple" in names
        assert "git_tool" in names
        assert "missing_tool" not in names

    def test_config_key_check_without_service(self) -> None:
        """Config key checks are skipped without config service."""
        checker = ToolEligibilityChecker(config_service=None)
        tool = make_tool_info(
            name="config_tool",
            description="Config dependent",
            requirements=ToolRequirements(config_keys=[ConfigRequirement(key="some.config.key")]),
        )

        # Without config service, config checks are skipped
        result = checker.check_eligibility(tool)

        assert result.eligible is True

    def test_config_key_check_with_env_fallback(self) -> None:
        """Config key check falls back to env var."""
        # Create a mock config service
        checker = ToolEligibilityChecker(config_service=object())
        tool = make_tool_info(
            name="config_tool",
            description="Config dependent",
            requirements=ToolRequirements(config_keys=[ConfigRequirement(key="test.config.value")]),
        )

        # Set env var that matches config key pattern
        with patch.dict(os.environ, {"TEST_CONFIG_VALUE": "yes"}):
            result = checker.check_eligibility(tool)
            assert result.eligible is True

    def test_config_key_missing(self) -> None:
        """Config key check fails when env var not set."""
        checker = ToolEligibilityChecker(config_service=object())
        tool = make_tool_info(
            name="config_tool",
            description="Config dependent",
            requirements=ToolRequirements(config_keys=[ConfigRequirement(key="nonexistent.config.key.xyz")]),
        )

        # Ensure env var is not set
        env_key = "NONEXISTENT_CONFIG_KEY_XYZ"
        with patch.dict(os.environ, {}, clear=False):
            if env_key in os.environ:
                del os.environ[env_key]
            result = checker.check_eligibility(tool)
            assert result.eligible is False
            assert "nonexistent.config.key.xyz" in result.missing_config

    def test_reason_combines_multiple_issues(self) -> None:
        """Reason string combines all eligibility issues."""
        checker = ToolEligibilityChecker(config_service=object())
        tool = make_tool_info(
            name="complex_tool",
            description="Many requirements",
            requirements=ToolRequirements(
                binaries=[BinaryRequirement(name="nonexistent_bin_xyz")],
                env_vars=[EnvVarRequirement(name="NONEXISTENT_VAR_ABC")],
                platforms=["fakeos"],
            ),
        )

        with patch("shutil.which", return_value=None):
            result = checker.check_eligibility(tool)

        assert result.eligible is False
        reason = result.reason or ""
        assert "nonexistent_bin_xyz" in reason
        assert "NONEXISTENT_VAR_ABC" in reason
        assert "not supported" in reason
