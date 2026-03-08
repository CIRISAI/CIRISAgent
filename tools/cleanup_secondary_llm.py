#!/usr/bin/env python3
"""Maintenance script to clean up stale CIRIS EU secondary LLM configuration.

With multi-endpoint failover support, the primary LLM service now handles
NA/EU failover internally. This means the secondary slot should be used
for a completely different provider (like OpenRouter, Ollama, etc.) instead
of being "wasted" on geographic redundancy.

This script:
1. Checks if CIRIS_OPENAI_API_BASE_2 points to a CIRIS EU endpoint
2. If so, removes the secondary LLM configuration from .env
3. Backs up the original .env before making changes

Usage:
    python -m tools.cleanup_secondary_llm [--dry-run] [--env-file PATH]

Options:
    --dry-run       Show what would be changed without making changes
    --env-file      Path to .env file (default: auto-detect)
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


def get_ciris_home() -> Path:
    """Get CIRIS home directory."""
    # Check environment variable first
    ciris_home = os.environ.get("CIRIS_HOME")
    if ciris_home:
        return Path(ciris_home)

    # Check common locations
    common_paths = [
        Path.home() / ".ciris",
        Path("/data/data/ai.ciris.mobile/files/ciris"),  # Android
        Path("/data/user/0/ai.ciris.mobile/files/ciris"),  # Android alternate
    ]

    for path in common_paths:
        if path.exists():
            return path

    # Default to ~/.ciris
    return Path.home() / ".ciris"


def find_env_file(env_file_path: Optional[str] = None) -> Optional[Path]:
    """Find the .env file to process."""
    if env_file_path:
        path = Path(env_file_path)
        if path.exists():
            return path
        print(f"Error: Specified .env file not found: {env_file_path}")
        return None

    # Auto-detect .env location
    ciris_home = get_ciris_home()
    env_path = ciris_home / ".env"
    if env_path.exists():
        return env_path

    # Check current directory
    local_env = Path(".env")
    if local_env.exists():
        return local_env

    print(f"No .env file found in {ciris_home} or current directory")
    return None


def is_ciris_eu_url(url: str) -> bool:
    """Check if a URL is a CIRIS EU endpoint.

    CIRIS EU endpoints typically contain "eu" in the domain or subdomain.
    """
    if not url:
        return False

    url_lower = url.lower()
    # Check for EU indicators in CIRIS service URLs
    eu_patterns = [
        "ciris-services-eu",
        "ciris-eu",
        "-eu-",
        ".eu.",
        "eu1.ciris",
        "eu2.ciris",
    ]

    return any(pattern in url_lower for pattern in eu_patterns)


def is_ciris_proxy_url(url: str) -> bool:
    """Check if a URL is any CIRIS proxy endpoint."""
    if not url:
        return False

    url_lower = url.lower()
    return "ciris-services" in url_lower or "ciris.ai" in url_lower


def parse_env_file(env_path: Path) -> List[str]:
    """Parse .env file into lines."""
    with open(env_path, "r") as f:
        return f.readlines()


def find_secondary_llm_lines(lines: List[str]) -> Tuple[dict, List[int]]:
    """Find secondary LLM configuration lines and their indices.

    Returns:
        Tuple of (config_dict, line_indices)
        config_dict: {"key": "value"} for secondary LLM vars
        line_indices: List of line indices to remove
    """
    secondary_vars = [
        "CIRIS_OPENAI_API_KEY_2",
        "CIRIS_OPENAI_API_BASE_2",
        "CIRIS_OPENAI_MODEL_NAME_2",
    ]

    config = {}
    indices_to_remove = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        for var in secondary_vars:
            if stripped.startswith(f"{var}="):
                # Extract value (handle quoted values)
                match = re.match(rf'{var}=["\']?([^"\']*)["\']?', stripped)
                if match:
                    config[var] = match.group(1)
                    indices_to_remove.append(i)
                break

    return config, indices_to_remove


def backup_env_file(env_path: Path) -> Path:
    """Create a backup of the .env file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = env_path.parent / f".env.backup_{timestamp}"
    shutil.copy2(env_path, backup_path)
    return backup_path


def remove_lines_from_env(env_path: Path, indices_to_remove: List[int]) -> None:
    """Remove specified lines from the .env file."""
    with open(env_path, "r") as f:
        lines = f.readlines()

    # Remove lines in reverse order to preserve indices
    for i in sorted(indices_to_remove, reverse=True):
        del lines[i]

    # Also remove any blank lines that might result from removal
    # (clean up consecutive blank lines)
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        cleaned_lines.append(line)
        prev_blank = is_blank

    with open(env_path, "w") as f:
        f.writelines(cleaned_lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Clean up stale CIRIS EU secondary LLM configuration")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making changes",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to .env file (default: auto-detect)",
    )
    args = parser.parse_args()

    # Find .env file
    env_path = find_env_file(args.env_file)
    if not env_path:
        return 1

    print(f"Processing: {env_path}")

    # Parse .env file
    lines = parse_env_file(env_path)
    config, indices_to_remove = find_secondary_llm_lines(lines)

    if not config:
        print("No secondary LLM configuration found.")
        return 0

    # Check if secondary is CIRIS EU
    base_url = config.get("CIRIS_OPENAI_API_BASE_2", "")

    print(f"\nSecondary LLM configuration found:")
    for key, value in config.items():
        # Mask sensitive values
        display_value = value
        if "KEY" in key or "TOKEN" in key:
            display_value = value[:20] + "..." if len(value) > 20 else value
        print(f"  {key}={display_value}")

    if not is_ciris_proxy_url(base_url):
        print("\nSecondary LLM is not a CIRIS proxy - no cleanup needed.")
        print("(This slot can be used for a different provider)")
        return 0

    if not is_ciris_eu_url(base_url):
        print("\nSecondary LLM is CIRIS proxy but not EU region.")
        print("Consider whether this configuration is still needed.")
        return 0

    print("\nSecondary LLM is a CIRIS EU endpoint.")
    print("With multi-endpoint failover, EU is now handled by the primary LLM.")
    print("This secondary configuration is redundant and can be removed.")

    if args.dry_run:
        print("\n[DRY RUN] Would remove the following lines:")
        for i in indices_to_remove:
            print(f"  Line {i + 1}: {lines[i].strip()}")
        print("\n[DRY RUN] No changes made.")
        return 0

    # Confirm before making changes
    print("\nWould you like to remove this redundant configuration? [y/N]")
    response = input().strip().lower()
    if response != "y":
        print("Aborted.")
        return 0

    # Backup and remove
    backup_path = backup_env_file(env_path)
    print(f"\nBacked up to: {backup_path}")

    remove_lines_from_env(env_path, indices_to_remove)
    print(f"Removed {len(indices_to_remove)} lines from {env_path}")

    print("\nCleanup complete!")
    print("The secondary LLM slot is now free for a different provider.")
    print("You can configure a backup provider like OpenRouter or Ollama.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
