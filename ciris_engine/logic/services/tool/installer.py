"""Tool installation service for executing InstallStep specifications.

Supports multiple package managers:
- brew (macOS/Linux Homebrew)
- apt (Debian/Ubuntu)
- pip/uv (Python packages)
- npm (Node.js packages)
- winget (Windows)
- choco (Windows Chocolatey)
- download (in-process HTTPS fetch + safe archive extraction; no shell)
"""

import asyncio
import logging
import os
import shlex
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

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

        # #851: the 'download' kind is handled in-process (HTTPS fetch + safe
        # archive extraction), NOT via a shell — this replaces the old `sh -c`
        # `curl | tar` escape hatch that let a skill manifest run arbitrary code.
        if step.kind.lower() == "download":
            return await self._install_download(step)

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
    def _command_builders(self) -> Dict[str, Callable[[InstallStep], Optional[List[str]]]]:
        """Command builder dispatch table for each package manager."""
        return {
            "brew": self._build_brew_cmd,
            "apt": self._build_apt_cmd,
            "pip": self._build_pip_cmd,
            "uv": self._build_uv_cmd,
            "npm": self._build_npm_cmd,
            "winget": self._build_winget_cmd,
            "choco": self._build_choco_cmd,
            # #851: 'manual' (arbitrary `sh -c` from a skill manifest) is removed.
            # Archive installs use the structured 'download' kind handled in
            # install() with no shell.
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

    def _has_package_manager(self, kind: str) -> bool:
        """Check if a package manager is available."""
        kind_lower = kind.lower()

        # #851: 'download' is handled in-process (HTTPS + extraction), always
        # available; 'manual' shell installs are no longer supported.
        if kind_lower == "download":
            return True
        if kind_lower == "manual":
            return False

        # Special handling for pip - check module availability via sys.executable
        if kind_lower == "pip":
            import subprocess

            try:
                # Check if python -m pip works
                subprocess.run(
                    [sys.executable, "-m", "pip", "--version"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Fallback to binary check if module check fails
                pass

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
        binary = manager_binaries.get(kind_lower)
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
            # Kill the orphaned subprocess to prevent resource leaks
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass  # Best effort cleanup
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
        """Run verification command and check success.

        #851: parse the verify command into an argument vector and exec it
        directly — no shell. A manifest-supplied verify string with `;`/`|`/`$()`
        can no longer inject commands; shell metacharacters simply make shlex
        produce literal args that won't match a real binary (verification fails
        safely).
        """
        proc = None
        try:
            argv = shlex.split(verify_command)
            if not argv:
                return False
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
            return proc.returncode == 0
        except Exception:
            # Kill orphaned subprocess on timeout or error
            if proc is not None:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass  # Best effort cleanup
            return False

    async def _install_download(self, step: InstallStep) -> InstallResult:
        """Install a 'download' step: HTTPS fetch + safe archive extraction.

        #851: replaces the old `sh -c "curl | tar"` path. No shell is involved;
        the URL must be HTTPS and archive members are validated against path
        traversal (Zip/Tar Slip) before extraction.
        """
        if not step.url or not step.target_dir:
            return InstallResult(
                success=False, step_id=step.id, message="download step missing url or target_dir"
            )

        if self.dry_run:
            return InstallResult(
                success=True,
                step_id=step.id,
                message=f"[dry-run] Would download {step.url} -> {step.target_dir}",
                binaries_installed=step.provides_binaries,
            )

        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    self._download_and_extract, step.url, step.target_dir, step.strip_components
                ),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            return InstallResult(
                success=False, step_id=step.id, message=f"Download timed out after {self.timeout}s"
            )
        except Exception as e:
            return InstallResult(success=False, step_id=step.id, message=f"Download/extract failed: {e}")

        result = InstallResult(
            success=True, step_id=step.id, message=f"Downloaded and extracted to {step.target_dir}"
        )
        if step.verify_command:
            if not await self._verify_installation(step.verify_command):
                result.success = False
                result.message = f"Installation ran but verification failed: {step.verify_command}"
        if result.success:
            result.binaries_installed = self._check_binaries(step.provides_binaries)
        return result

    @staticmethod
    def _download_and_extract(url: str, target_dir: str, strip_components: Optional[int]) -> None:
        """Fetch an HTTPS archive and extract it safely into target_dir."""
        if not url.lower().startswith("https://"):
            raise ValueError(f"Refusing non-HTTPS download URL: {url}")

        target = os.path.realpath(target_dir)
        os.makedirs(target, exist_ok=True)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            with urllib.request.urlopen(url, timeout=60) as resp:  # nosec B310 - scheme validated https above
                shutil.copyfileobj(resp, tmp)
        try:
            if tarfile.is_tarfile(tmp_path):
                with tarfile.open(tmp_path) as tf:
                    ToolInstaller._safe_extract_tar(tf, target, strip_components or 0)
            elif zipfile.is_zipfile(tmp_path):
                with zipfile.ZipFile(tmp_path) as zf:
                    ToolInstaller._safe_extract_zip(zf, target, strip_components or 0)
            else:
                raise ValueError("Downloaded file is neither a tar nor a zip archive")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    def _stripped_dest(name: str, target: str, strip_components: int) -> Optional[str]:
        """Apply strip_components and validate the member stays inside target.

        Returns the absolute destination path, or None if the member should be
        skipped (e.g. fully stripped away). Raises ValueError on traversal.
        """
        parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
        if strip_components:
            parts = parts[strip_components:]
        if not parts:
            return None
        dest = os.path.realpath(os.path.join(target, *parts))
        if dest != target and not dest.startswith(target + os.sep):
            raise ValueError(f"Refusing archive member escaping target dir: {name}")
        return dest

    @staticmethod
    def _safe_extract_tar(tf: tarfile.TarFile, target: str, strip_components: int) -> None:
        for member in tf.getmembers():
            # Only regular files and directories — never symlinks/hardlinks/devices
            # (a symlink could redirect a later write outside target).
            if not (member.isreg() or member.isdir()):
                continue
            dest = ToolInstaller._stripped_dest(member.name, target, strip_components)
            if dest is None:
                continue
            if member.isdir():
                os.makedirs(dest, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            with extracted, open(dest, "wb") as out:
                shutil.copyfileobj(extracted, out)

    @staticmethod
    def _safe_extract_zip(zf: zipfile.ZipFile, target: str, strip_components: int) -> None:
        for info in zf.infolist():
            name = info.filename
            is_dir = name.endswith("/")
            dest = ToolInstaller._stripped_dest(name, target, strip_components)
            if dest is None:
                continue
            if is_dir:
                os.makedirs(dest, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)

    def _check_binaries(self, binaries: List[str]) -> List[str]:
        """Check which binaries are now available."""
        return [b for b in binaries if shutil.which(b) is not None]
