"""Tests for the ToolInstaller service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.services.tool.installer import InstallResult, ToolInstaller
from ciris_engine.schemas.adapters.tools import InstallStep


class TestInstallResult:
    """Tests for InstallResult dataclass."""

    def test_success_result(self):
        result = InstallResult(
            success=True,
            step_id="brew-ffmpeg",
            message="Successfully installed",
            binaries_installed=["ffmpeg", "ffprobe"],
        )
        assert result.success is True
        assert result.step_id == "brew-ffmpeg"
        assert result.binaries_installed == ["ffmpeg", "ffprobe"]

    def test_failure_result(self):
        result = InstallResult(
            success=False,
            step_id="apt-missing",
            message="Package not found",
            stderr="E: Unable to locate package",
        )
        assert result.success is False
        assert "Package not found" in result.message
        assert result.binaries_installed == []

    def test_default_binaries_list(self):
        result = InstallResult(success=True, step_id="test", message="ok")
        assert result.binaries_installed == []


class TestToolInstaller:
    """Tests for ToolInstaller class."""

    def test_init_defaults(self):
        installer = ToolInstaller()
        assert installer.timeout == 300
        assert installer.dry_run is False

    def test_init_custom_values(self):
        installer = ToolInstaller(timeout=60, dry_run=True)
        assert installer.timeout == 60
        assert installer.dry_run is True

    def test_build_command_brew(self):
        installer = ToolInstaller()
        step = InstallStep(
            id="brew-ffmpeg",
            kind="brew",
            label="Install ffmpeg via Homebrew",
            formula="ffmpeg",
            provides_binaries=["ffmpeg"],
        )
        cmd = installer._build_command(step)
        assert cmd == ["brew", "install", "ffmpeg"]

    def test_build_command_apt(self):
        installer = ToolInstaller()
        step = InstallStep(
            id="apt-git",
            kind="apt",
            label="Install git",
            package="git",
            provides_binaries=["git"],
        )
        cmd = installer._build_command(step)
        assert cmd == ["sudo", "apt-get", "install", "-y", "git"]

    def test_build_command_pip(self):
        installer = ToolInstaller()
        step = InstallStep(
            id="pip-requests",
            kind="pip",
            label="Install requests",
            package="requests",
            provides_binaries=[],
        )
        cmd = installer._build_command(step)
        # Command is: [sys.executable, "-m", "pip", "install", "requests"]
        assert cmd[1] == "-m"
        assert cmd[2] == "pip"
        assert "install" in cmd
        assert "requests" in cmd

    def test_build_command_npm(self):
        installer = ToolInstaller()
        step = InstallStep(
            id="npm-typescript",
            kind="npm",
            label="Install TypeScript",
            package="typescript",
            provides_binaries=["tsc"],
        )
        cmd = installer._build_command(step)
        assert cmd == ["npm", "install", "-g", "typescript"]

    def test_build_command_manual(self):
        installer = ToolInstaller()
        step = InstallStep(
            id="manual-custom",
            kind="manual",
            label="Custom install",
            command="curl -sSL example.com/install.sh | bash",
            provides_binaries=["mytool"],
        )
        cmd = installer._build_command(step)
        assert cmd == ["sh", "-c", "curl -sSL example.com/install.sh | bash"]

    def test_build_command_unknown_kind(self):
        installer = ToolInstaller()
        step = InstallStep(
            id="unknown",
            kind="unknown_manager",
            label="Unknown",
            provides_binaries=[],
        )
        cmd = installer._build_command(step)
        assert cmd is None

    def test_build_command_missing_formula(self):
        installer = ToolInstaller()
        step = InstallStep(
            id="brew-missing",
            kind="brew",
            label="Missing formula",
            provides_binaries=[],
        )
        cmd = installer._build_command(step)
        assert cmd is None

    @pytest.mark.asyncio
    async def test_install_dry_run(self):
        installer = ToolInstaller(dry_run=True)
        step = InstallStep(
            id="brew-test",
            kind="brew",
            label="Test install",
            formula="testtool",
            provides_binaries=["testtool"],
        )
        result = await installer.install(step)
        assert result.success is True
        assert "[dry-run]" in result.message
        assert "brew install testtool" in result.message
        assert result.binaries_installed == ["testtool"]

    @pytest.mark.asyncio
    async def test_install_platform_mismatch(self):
        installer = ToolInstaller()
        step = InstallStep(
            id="winget-tool",
            kind="winget",
            label="Windows only",
            package="SomeTool",
            platforms=["win32"],
            provides_binaries=["sometool"],
        )
        # This will fail on non-Windows
        if installer._platform != "win32":
            result = await installer.install(step)
            assert result.success is False
            assert "not applicable to platform" in result.message

    @pytest.mark.asyncio
    async def test_install_unknown_kind(self):
        installer = ToolInstaller()
        step = InstallStep(
            id="unknown",
            kind="alien_package_manager",
            label="Unknown manager",
            provides_binaries=[],
        )
        result = await installer.install(step)
        assert result.success is False
        assert "Unknown install kind" in result.message

    @pytest.mark.asyncio
    async def test_install_first_applicable_no_applicable(self):
        installer = ToolInstaller()
        steps = [
            InstallStep(
                id="win-only",
                kind="winget",
                label="Windows",
                package="tool",
                platforms=["win32"],
                provides_binaries=["tool"],
            ),
        ]
        # On non-Windows, this should fail
        if installer._platform != "win32":
            result = await installer.install_first_applicable(steps)
            assert result.success is False
            assert "No install steps applicable" in result.message

    @pytest.mark.asyncio
    async def test_install_first_applicable_dry_run(self):
        installer = ToolInstaller(dry_run=True)
        steps = [
            InstallStep(
                id="brew-tool",
                kind="brew",
                label="Install via brew",
                formula="mytool",
                platforms=["darwin", "linux"],
                provides_binaries=["mytool"],
            ),
            InstallStep(
                id="apt-tool",
                kind="apt",
                label="Install via apt",
                package="mytool",
                platforms=["linux"],
                provides_binaries=["mytool"],
            ),
        ]
        with patch.object(installer, "_has_package_manager", return_value=True):
            result = await installer.install_first_applicable(steps)
            assert result.success is True
            assert "[dry-run]" in result.message

    def test_has_package_manager_unknown(self):
        installer = ToolInstaller()
        assert installer._has_package_manager("nonexistent_manager") is False

    @pytest.mark.asyncio
    async def test_run_command_success(self):
        installer = ToolInstaller()
        step = InstallStep(
            id="echo-test",
            kind="manual",
            label="Echo test",
            command="echo hello",
            provides_binaries=[],
        )
        result = await installer._run_command(["echo", "hello"], step)
        assert result.success is True
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_run_command_failure(self):
        installer = ToolInstaller()
        step = InstallStep(
            id="false-test",
            kind="manual",
            label="False test",
            command="false",
            provides_binaries=[],
        )
        result = await installer._run_command(["false"], step)
        assert result.success is False
        assert "exit code" in result.message

    @pytest.mark.asyncio
    async def test_run_command_timeout(self):
        installer = ToolInstaller(timeout=1)
        step = InstallStep(
            id="sleep-test",
            kind="manual",
            label="Sleep test",
            command="sleep 10",
            provides_binaries=[],
        )
        result = await installer._run_command(["sleep", "10"], step)
        assert result.success is False
        assert "timed out" in result.message

    @pytest.mark.asyncio
    async def test_verify_installation_success(self):
        installer = ToolInstaller()
        verified = await installer._verify_installation("echo success")
        assert verified is True

    @pytest.mark.asyncio
    async def test_verify_installation_failure(self):
        installer = ToolInstaller()
        verified = await installer._verify_installation("false")
        assert verified is False

    def test_check_binaries_finds_existing(self):
        installer = ToolInstaller()
        # 'echo' and 'ls' should exist on most systems
        found = installer._check_binaries(["echo", "nonexistent_binary_xyz"])
        assert "echo" in found
        assert "nonexistent_binary_xyz" not in found


class TestEligibilityCheckerInstallIntegration:
    """Tests for install_and_recheck method on EligibilityChecker."""

    @pytest.mark.asyncio
    async def test_install_and_recheck_already_eligible(self):
        from ciris_engine.logic.services.tool.eligibility_checker import ToolEligibilityChecker
        from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema

        checker = ToolEligibilityChecker()
        tool = ToolInfo(
            name="echo_tool",
            description="Uses echo",
            parameters=ToolParameterSchema(type="object", properties={}),
            # No requirements = always eligible
        )
        result, install_result = await checker.install_and_recheck(tool)
        assert result.eligible is True
        assert install_result is None

    @pytest.mark.asyncio
    async def test_install_and_recheck_no_hints(self):
        from ciris_engine.logic.services.tool.eligibility_checker import ToolEligibilityChecker
        from ciris_engine.schemas.adapters.tools import (
            BinaryRequirement,
            ToolInfo,
            ToolParameterSchema,
            ToolRequirements,
        )

        checker = ToolEligibilityChecker()
        tool = ToolInfo(
            name="missing_tool",
            description="Needs a missing binary",
            parameters=ToolParameterSchema(type="object", properties={}),
            requirements=ToolRequirements(binaries=[BinaryRequirement(name="nonexistent_binary_xyz123")]),
            # No install_steps = no hints
        )
        result, install_result = await checker.install_and_recheck(tool)
        assert result.eligible is False
        assert install_result is not None
        assert install_result.success is False
        assert "No install hints" in install_result.message

    @pytest.mark.asyncio
    async def test_install_and_recheck_dry_run(self):
        from ciris_engine.logic.services.tool.eligibility_checker import ToolEligibilityChecker
        from ciris_engine.schemas.adapters.tools import (
            BinaryRequirement,
            InstallStep,
            ToolInfo,
            ToolParameterSchema,
            ToolRequirements,
        )

        checker = ToolEligibilityChecker()
        tool = ToolInfo(
            name="installable_tool",
            description="Can be installed",
            parameters=ToolParameterSchema(type="object", properties={}),
            requirements=ToolRequirements(binaries=[BinaryRequirement(name="nonexistent_binary_xyz123")]),
            install_steps=[
                InstallStep(
                    id="brew-xyz",
                    kind="brew",
                    label="Install xyz",
                    formula="xyz123",
                    provides_binaries=["nonexistent_binary_xyz123"],
                )
            ],
        )
        # Mock _has_package_manager to return True so the install attempt proceeds
        with patch(
            "ciris_engine.logic.services.tool.installer.ToolInstaller._has_package_manager",
            return_value=True,
        ):
            result, install_result = await checker.install_and_recheck(tool, dry_run=True)
        # Still not eligible (dry run doesn't actually install)
        assert result.eligible is False
        # But dry run reports success
        assert install_result is not None
        assert install_result.success is True
        assert "[dry-run]" in install_result.message
