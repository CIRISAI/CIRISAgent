"""Docker container management for test execution."""

import os
import subprocess
from pathlib import Path
from typing import List, Optional


class DockerManager:
    """Manages Docker containers for test execution."""

    def __init__(self, compose_file: str = "docker/docker-compose-pytest.yml"):
        self.compose_file = compose_file

    def rebuild_container(self, service: str = "pytest") -> tuple[bool, str]:
        """
        Rebuild the test container.

        Returns:
            Tuple of (success, message)
        """
        print("🔨 Rebuilding test container...")
        # Set environment variables for UID/GID
        env = os.environ.copy()
        env["USER_UID"] = str(os.getuid())
        env["USER_GID"] = str(os.getgid())

        cmd = ["docker", "compose", "-f", self.compose_file, "build", service]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if result.returncode != 0:
            return False, f"Failed to rebuild container:\n{result.stderr}"

        return True, "Container rebuilt successfully"

    def run_command(self, command: str, container_name: str, output_file: Path) -> subprocess.Popen:
        """
        Run a command in the Docker container.

        Args:
            command: Command to execute
            container_name: Name for the container
            output_file: File to write output to

        Returns:
            Popen process object
        """
        # Set environment variables for UID/GID
        env = os.environ.copy()
        env["USER_UID"] = str(os.getuid())
        env["USER_GID"] = str(os.getgid())

        cmd = [
            "docker",
            "compose",
            "-f",
            self.compose_file,
            "run",
            "--rm",
            "--name",
            container_name,
            "-T",  # Disable TTY for background execution
            "pytest",
            "/bin/bash",
            "-c",
            command,
        ]

        with open(output_file, "w") as outfile:
            process = subprocess.Popen(cmd, stdout=outfile, stderr=subprocess.STDOUT, cwd=Path.cwd(), env=env)

        return process

    def stop_container(self, container_name: str) -> bool:
        """Stop a running container."""
        try:
            subprocess.run(["docker", "stop", container_name], capture_output=True, timeout=10)
            return True
        except subprocess.TimeoutExpired:
            # Force kill if graceful stop times out
            subprocess.run(["docker", "kill", container_name], capture_output=True)
            return True
        except Exception:
            return False

    def is_container_running(self, container_name: str) -> bool:
        """Check if a container is running."""
        result = subprocess.run(["docker", "ps", "-q", "-f", f"name={container_name}"], capture_output=True, text=True)
        return bool(result.stdout.strip())

    def exec_in_container(self, container_name: str, command: List[str]) -> Optional[str]:
        """
        Execute a command in a running container.

        Returns:
            Command output or None if failed
        """
        if not self.is_container_running(container_name):
            return None

        cmd = ["docker", "exec", container_name] + command
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return None

        return result.stdout
