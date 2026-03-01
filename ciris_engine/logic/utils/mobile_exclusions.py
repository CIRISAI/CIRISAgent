"""Mobile exclusion utilities for file integrity checking.

On mobile (Android/iOS), certain files are expected to be missing from the
device filesystem because they are:
1. Platform-specific adapters (discord, reddit, cli, slack)
2. Web UI assets (gui_static)
3. Non-Python content files (.md, .html, .svg, .png, etc.)

These utilities help identify and filter mobile-excluded files from
the file integrity results.
"""

from typing import Dict, List, Optional, Tuple

# Prefixes for directories that are excluded on mobile
MOBILE_EXCLUDED_PREFIXES = (
    "ciris_engine/gui_static/",
    "ciris_engine/logic/adapters/discord/",
    "ciris_engine/logic/adapters/reddit/",
    "ciris_engine/logic/adapters/cli/",
    "ciris_engine/logic/adapters/slack/",
)

# Extensions that Chaquopy doesn't bundle (non-Python content files)
MOBILE_EXCLUDED_EXTENSIONS = (
    ".md",  # Markdown docs
    ".rst",  # ReStructuredText docs
    ".html",  # HTML files
    ".svg",  # SVG images
    ".png",  # PNG images
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".webm",
    ".css",
    ".map",  # Source maps
)


def is_mobile_excluded(filepath: str) -> bool:
    """Check if a file path is expected to be excluded on mobile.

    Args:
        filepath: Relative file path from agent root

    Returns:
        True if file is expected to be missing on mobile
    """
    # Check prefix exclusions
    if any(filepath.startswith(prefix) for prefix in MOBILE_EXCLUDED_PREFIXES):
        return True

    # Check extension exclusions
    if any(filepath.endswith(ext) for ext in MOBILE_EXCLUDED_EXTENSIONS):
        return True

    return False


def compute_mobile_excluded_from_results(per_file_results: Optional[Dict[str, str]]) -> Tuple[int, List[str]]:
    """Compute mobile exclusion count and list from per-file results.

    Includes ALL files expected to be missing on mobile:
    - Files in excluded directories (discord, reddit, cli, slack, gui_static)
    - Files with excluded extensions (images, fonts, etc.)

    Note: Previously excluded .py files, but discord/*.py etc. ARE expected
    to be missing on mobile since those adapters aren't bundled.

    Args:
        per_file_results: Dict mapping file paths to status (passed/failed/missing)

    Returns:
        Tuple of (count, list) where list is capped at 50 items
    """
    if not per_file_results:
        return 0, []

    excluded_files: List[str] = []

    for filepath, status in per_file_results.items():
        # Only consider missing files for exclusion
        if status != "missing":
            continue

        if is_mobile_excluded(filepath):
            excluded_files.append(filepath)

    return len(excluded_files), excluded_files[:50]


def compute_mobile_excluded_count(per_file_results: Optional[Dict[str, str]]) -> Optional[int]:
    """Compute count of mobile-excluded files from per-file results.

    Args:
        per_file_results: Dict mapping file paths to status

    Returns:
        Count of mobile-excluded files, or None if no results
    """
    if not per_file_results:
        return None

    count, _ = compute_mobile_excluded_from_results(per_file_results)
    return count


def compute_mobile_excluded_list(
    per_file_results: Optional[Dict[str, str]], max_items: int = 50
) -> Optional[List[str]]:
    """Compute list of mobile-excluded files from per-file results.

    Args:
        per_file_results: Dict mapping file paths to status
        max_items: Maximum number of items to return

    Returns:
        List of mobile-excluded file paths, or None if no results
    """
    if not per_file_results:
        return None

    _, excluded_list = compute_mobile_excluded_from_results(per_file_results)
    return excluded_list[:max_items]


def compute_files_missing_list(per_file_results: Optional[Dict[str, str]], max_items: int = 50) -> Optional[List[str]]:
    """Compute list of files missing from device (excluding mobile-excluded).

    These are files in the manifest that are NOT on the device AND are
    NOT expected to be excluded on mobile (i.e., they SHOULD be there).

    Args:
        per_file_results: Dict mapping file paths to status
        max_items: Maximum number of items to return

    Returns:
        List of missing file paths, or None if no results
    """
    if not per_file_results:
        return None

    missing_files: List[str] = []

    for filepath, status in per_file_results.items():
        if status != "missing":
            continue

        # Skip mobile-excluded files (those are expected to be missing)
        if is_mobile_excluded(filepath):
            continue

        missing_files.append(filepath)

    return missing_files[:max_items]


def compute_files_unexpected_list(
    per_file_results: Optional[Dict[str, str]], max_items: int = 50
) -> Optional[List[str]]:
    """Compute list of files on device but not in manifest (unexpected).

    These are files that exist on the device but are NOT in the registry
    manifest - potential unauthorized additions.

    Args:
        per_file_results: Dict mapping file paths to status
        max_items: Maximum number of items to return

    Returns:
        List of unexpected file paths, or None if no results
    """
    if not per_file_results:
        return None

    unexpected_files: List[str] = []

    for filepath, status in per_file_results.items():
        if status == "unexpected":
            unexpected_files.append(filepath)

    return unexpected_files[:max_items]
