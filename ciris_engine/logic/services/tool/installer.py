"""Tool installation service for executing InstallStep specifications.

Supports multiple package managers:
- brew (macOS/Linux Homebrew)
- apt (Debian/Ubuntu)
- pip/uv (Python packages)
- npm (Node.js packages)
- winget (Windows)
- choco (Windows Chocolatey)
- manual (custom command)
"""

import asyncio
import logging
import shutil
import sys
from dataclasses import dataclass
from typing import List, Optional

from ciris_engine.schemas.adapters.tools import InstallStep

logger = logging.getLogger(__name__)


@dataclass
class InstallResult:
    """Result of an installation attempt."""

    success: bool
    step_id: str
    message: str
    stdout: str = ""
    stderr: str = ""
    binaries_installed: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.binaries_installed is None:
            self.binaries_installed = []


class ToolInstaller:
    """Executes InstallStep specifications to install tool dependencies.

    Usage:
        installer = ToolInstaller()
        result = await installer.install(step)
        if result.success:
            print(f"Installed: {result.binaries_installed}")
    """

    def __init__(self, timeout: int = 300, dry_run: bool = False):
        """Initialize installer.

        Args:
            timeout: Max seconds for install commands (default 5 min)
            dry_run: If True, don't execute commands, just return what would run
        """
        self.timeout = timeout
        self.dry_run = dry_run
        self._platform = sys.platform

    async def install(self, step: InstallStep) -> InstallResult:
        """Execute an installation step.

        Args:
            step: The InstallStep to execute

        Returns:
            InstallResult with success status and details
        """
        if step.platforms and self._platform not in step.platforms:
            return InstallResult(
                success=False,
                step_id=step.id,
                message=f"Step {step.id} not applicable to platform {self._platform}",
            )

        cmd = self._build_command(step)
        if not cmd:
            return InstallResult(
                success=False,
                step_id=step.id,
                message=f"Unknown install kind: {step.kind}",
            )

        if self.dry_run:
            return InstallResult(
                success=True,
                step_id=step.id,
                message=f"[dry-run] Would execute: {' '.join(cmd)}",
                binaries_installed=step.provides_binaries,
            )

        result = await self._run_command(cmd, step)

        if result.success and step.verify_command:
            verified = await self._verify_installation(step.verify_command)
            if not verified:
                result.success = False
                result.message = f"Installation ran but verification failed: {step.verify_command}"

        if result.success:
            result.binaries_installed = self._check_binaries(step.provides_binaries)

        return result

    async def install_first_applicable(self, steps: List[InstallStep]) -> InstallResult:
        """Try install steps in order, return first success.

        Args:
            steps: List of InstallStep options (e.g., brew for mac, apt for linux)

        Returns:
            InstallResult from first successful step, or last failure
        """
        applicable = [s for s in steps if not s.platforms or self._platform in s.platforms]

        if not applicable:
            return InstallResult(
                success=False,
                step_id="none",
                message=f"No install steps applicable to platform {self._platform}",
            )

        last_result = None
        for step in applicable:
            if not self._has_package_manager(step.kind):
                logger.info(f"Skipping {step.id}: {step.kind} not available")
                continue

            result = await self.install(step)
            if result.success:
                return result
            last_result = result
            logger.warning(f"Install step {step.id} failed: {result.message}")

        return last_result or InstallResult(
            success=False,
            step_id="none",
            message="No package managers available for applicable steps",
        )

    def _build_command(self, step: InstallStep) -> Optional[List[str]]:
        """Build the shell command for an install step."""
        kind = step.kind.lower()
        builder = self._command_builders.get(kind)
        if not builder:
            return None
        return builder(step)

    @property
    def _command_builders(self) -> dict:
        """Command builder dispatch table for each package manager."""
        return {
            "brew": self._build_brew_cmd,
            "apt": self._build_apt_cmd,
            "pip": self._build_pip_cmd,
            "uv": self._build_uv_cmd,
            "npm": self._build_npm_cmd,
            "winget": self._build_winget_cmd,
            "choco": self._build_choco_cmd,
            "manual": self._build_manual_cmd,
        }

    def _build_brew_cmd(self, step: InstallStep) -> Optional[List[str]]:
        """Build brew install command."""
        return ["brew", "install", step.formula] if step.formula else None

    def _build_apt_cmd(self, step: InstallStep) -> Optional[List[str]]:
        """Build apt-get install command."""
        return ["sudo", "apt-get", "install", "-y", step.package] if step.package else None

    def _build_pip_cmd(self, step: InstallStep) -> Optional[List[str]]:
        """Build pip install command."""
        return [sys.executable, "-m", "pip", "install", step.package] if step.package else None

    def _build_uv_cmd(self, step: InstallStep) -> Optional[List[str]]:
        """Build uv tool install command."""
        return ["uv", "tool", "install", step.package] if step.package else None

    def _build_npm_cmd(self, step: InstallStep) -> Optional[List[str]]:
        """Build npm global install command."""
        return ["npm", "install", "-g", step.package] if step.package else None

    def _build_winget_cmd(self, step: InstallStep) -> Optional[List[str]]:
        """Build winget install command."""
        return ["winget", "install", "--accept-package-agreements", step.package] if step.package else None

    def _build_choco_cmd(self, step: InstallStep) -> Optional[List[str]]:
        """Build chocolatey install command."""
        return ["choco", "install", "-y", step.package] if step.package else None

    def _build_manual_cmd(self, step: InstallStep) -> Optional[List[str]]:
        """Build manual shell command."""
        return ["sh", "-c", step.command] if step.command else None

    def _has_package_manager(self, kind: str) -> bool:
        """Check if a package manager is available."""
        manager_binaries = {
            "brew": "brew",
            "apt": "apt-get",
            "pip": "pip",
            "uv": "uv",
            "npm": "npm",
            "winget": "winget",
            "choco": "choco",
            "manual": "sh",
        }
        binary = manager_binaries.get(kind.lower())
        if not binary:
            return False
        return shutil.which(binary) is not None

    async def _run_command(self, cmd: List[str], step: InstallStep) -> InstallResult:
        """Execute a command and return result."""
        try:
            logger.info(f"Installing {step.id}: {' '.join(cmd)}")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                return InstallResult(
                    success=True,
                    step_id=step.id,
                    message=f"Successfully installed via {step.kind}",
                    stdout=stdout_str,
                    stderr=stderr_str,
                )
            else:
                return InstallResult(
                    success=False,
                    step_id=step.id,
                    message=f"Command failed with exit code {proc.returncode}",
                    stdout=stdout_str,
                    stderr=stderr_str,
                )

        except asyncio.TimeoutError:
            return InstallResult(
                success=False,
                step_id=step.id,
                message=f"Installation timed out after {self.timeout}s",
            )
        except Exception as e:
            return InstallResult(
                success=False,
                step_id=step.id,
                message=f"Installation error: {e}",
            )

    async def _verify_installation(self, verify_command: str) -> bool:
        """Run verification command and check success."""
        try:
            proc = await asyncio.create_subprocess_shell(
                verify_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
            return proc.returncode == 0
        except Exception:
            return False

    def _check_binaries(self, binaries: List[str]) -> List[str]:
        """Check which binaries are now available."""
        return [b for b in binaries if shutil.which(b) is not None]
