"""Tool eligibility checking based on runtime requirements.

Checks if tools are usable in the current environment by verifying:
- Required binaries are in PATH
- Required environment variables are set
- Platform is supported
- Config keys are available
"""

import logging
import os
import shutil
import sys
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.adapters.tools import InstallStep, ToolInfo, ToolRequirements

if TYPE_CHECKING:
    from ciris_engine.logic.services.tool.installer import InstallResult

logger = logging.getLogger(__name__)


class EligibilityResult(BaseModel):
    """Result of checking tool eligibility."""

    eligible: bool = Field(..., description="Whether the tool is eligible for use")
    missing_binaries: List[str] = Field(default_factory=list, description="Binaries that are not available")
    missing_env_vars: List[str] = Field(default_factory=list, description="Environment variables that are not set")
    missing_config: List[str] = Field(default_factory=list, description="Config keys that are not available")
    platform_mismatch: bool = Field(False, description="True if current platform is not supported")
    install_hints: List[InstallStep] = Field(
        default_factory=list, description="Installation steps for missing dependencies"
    )
    reason: Optional[str] = Field(None, description="Summary of why tool is not eligible")

    model_config = ConfigDict(extra="forbid")


class ToolEligibilityChecker:
    """Checks if tool requirements are satisfied in the current environment.

    Validates:
    - binaries: All must be present in PATH
    - any_binaries: At least one must be present (OR condition)
    - env_vars: All must be set (optionally non-empty)
    - platforms: Current platform must be in list (empty = all supported)
    - config_keys: All must be available in CIRIS config (TODO: integrate with config service)
    """

    def __init__(self, config_service: Optional[object] = None):
        """Initialize the checker.

        Args:
            config_service: Optional config service for checking config keys.
                           If not provided, config key checks are skipped.
        """
        self.config_service = config_service
        self._platform = sys.platform  # darwin, linux, win32

    def _check_required_binaries(self, req: ToolRequirements, result: EligibilityResult) -> None:
        """Check required binaries and update result."""
        for bin_req in req.binaries:
            if not self._check_binary(bin_req.name, bin_req.verify_command):
                result.eligible = False
                result.missing_binaries.append(bin_req.name)

    def _check_any_binaries(self, req: ToolRequirements, result: EligibilityResult) -> None:
        """Check alternative binaries (at least one must be present)."""
        if not req.any_binaries:
            return
        has_any = any(self._check_binary(b.name, b.verify_command) for b in req.any_binaries)
        if not has_any:
            result.eligible = False
            result.missing_binaries.extend([b.name for b in req.any_binaries])

    def _check_env_vars(self, req: ToolRequirements, result: EligibilityResult) -> None:
        """Check environment variables."""
        for env_req in req.env_vars:
            if os.environ.get(env_req.name) is None:
                result.eligible = False
                result.missing_env_vars.append(env_req.name)

    def _check_platform(self, req: ToolRequirements, result: EligibilityResult) -> None:
        """Check platform compatibility."""
        if req.platforms and self._platform not in req.platforms:
            result.eligible = False
            result.platform_mismatch = True

    def _check_config_keys(self, req: ToolRequirements, result: EligibilityResult) -> None:
        """Check config keys if config service available."""
        if not req.config_keys or not self.config_service:
            return
        for config_req in req.config_keys:
            if not self._check_config_key(config_req.key):
                result.eligible = False
                result.missing_config.append(config_req.key)

    def _add_install_hints(self, tool_info: ToolInfo, result: EligibilityResult) -> None:
        """Add install hints for missing dependencies."""
        if result.eligible or not tool_info.install_steps:
            return
        for step in tool_info.install_steps:
            if not step.platforms or self._platform in step.platforms:
                if any(b in result.missing_binaries for b in step.provides_binaries):
                    result.install_hints.append(step)

    def _build_reason(self, result: EligibilityResult) -> None:
        """Build summary reason for ineligibility."""
        if result.eligible:
            return
        reasons = []
        if result.missing_binaries:
            reasons.append(f"missing binaries: {', '.join(result.missing_binaries)}")
        if result.missing_env_vars:
            reasons.append(f"missing env vars: {', '.join(result.missing_env_vars)}")
        if result.missing_config:
            reasons.append(f"missing config: {', '.join(result.missing_config)}")
        if result.platform_mismatch:
            reasons.append(f"platform {self._platform} not supported")
        result.reason = "; ".join(reasons)

    def check_eligibility(self, tool_info: ToolInfo) -> EligibilityResult:
        """Check if a tool's requirements are satisfied.

        Args:
            tool_info: Full tool information including requirements

        Returns:
            EligibilityResult with eligibility status and details
        """
        if not tool_info.requirements:
            return EligibilityResult(eligible=True)

        result = EligibilityResult(eligible=True)
        req = tool_info.requirements

        self._check_required_binaries(req, result)
        self._check_any_binaries(req, result)
        self._check_env_vars(req, result)
        self._check_platform(req, result)
        self._check_config_keys(req, result)
        self._add_install_hints(tool_info, result)
        self._build_reason(result)

        return result

    def _check_binary(self, name: str, _verify_command: Optional[str] = None) -> bool:
        """Check if a binary is available in PATH.

        Args:
            name: Binary name (e.g., 'git', 'ffmpeg')
            _verify_command: Reserved for future verification (not yet implemented)

        Returns:
            True if binary is available
        """
        return shutil.which(name) is not None

    def _check_config_key(self, key: str) -> bool:
        """Check if a config key is available.

        Uses environment variable fallback when config service doesn't provide
        a direct lookup method. Converts dot-notation keys to ENV_VAR format.

        Args:
            key: Config key path (e.g., 'adapters.home_assistant.token')

        Returns:
            True if config key exists and has a value
        """
        if not self.config_service:
            return True  # Skip check if no config service

        # Check environment variable as fallback (config.key.path -> CONFIG_KEY_PATH)
        env_key = key.upper().replace(".", "_")
        return os.environ.get(env_key) is not None

    def filter_eligible_tools(self, tools: List[ToolInfo]) -> List[ToolInfo]:
        """Filter a list of tools to only those that are eligible.

        Args:
            tools: List of tool infos to check

        Returns:
            List of tools that pass eligibility checks
        """
        eligible = []
        for tool in tools:
            result = self.check_eligibility(tool)
            if result.eligible:
                eligible.append(tool)
            else:
                logger.info(f"Tool '{tool.name}' not eligible: {result.reason}")
        return eligible

    async def install_and_recheck(
        self, tool_info: ToolInfo, dry_run: bool = False
    ) -> tuple["EligibilityResult", Optional["InstallResult"]]:
        """Attempt to install missing dependencies and re-check eligibility.

        Args:
            tool_info: Tool to install dependencies for
            dry_run: If True, don't actually install, just report what would happen

        Returns:
            Tuple of (new_eligibility_result, install_result or None)
        """
        from ciris_engine.logic.services.tool.installer import InstallResult, ToolInstaller

        initial = self.check_eligibility(tool_info)
        if initial.eligible:
            return initial, None

        if not initial.install_hints:
            return initial, InstallResult(
                success=False,
                step_id="none",
                message="No install hints available for missing dependencies",
            )

        installer = ToolInstaller(dry_run=dry_run)
        install_result = await installer.install_first_applicable(initial.install_hints)

        if install_result.success:
            new_result = self.check_eligibility(tool_info)
            return new_result, install_result

        return initial, install_result
