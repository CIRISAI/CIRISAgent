import hashlib
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional


def _get_code_hash() -> str:
    """Generate a deterministic hash of the Python codebase."""
    repo_root = Path(__file__).resolve().parent
    hasher = hashlib.sha256()

    # Get all Python files in sorted order for deterministic hashing
    py_files = []
    for root, dirs, files in os.walk(repo_root):
        # Skip hidden directories and common non-code directories
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["__pycache__", "venv", "env", ".git"]]

        for file in files:
            if file.endswith(".py"):
                py_files.append(os.path.join(root, file))

    # Sort files for deterministic order
    py_files.sort()

    # Hash the content of each file
    for file_path in py_files:
        try:
            with open(file_path, "rb") as f:
                # Include file path in hash for completeness
                hasher.update(file_path.encode("utf-8"))
                hasher.update(b"\0")  # Separator
                hasher.update(f.read())
        except Exception:
            pass

    # Return first 12 characters of hash for brevity
    return hasher.hexdigest()[:12]


def write_build_version(sign_key: Optional[str] = None) -> str:
    """Write version info to a build file for release tracking.

    Args:
        sign_key: Optional secret key to sign the code hash with HMAC
    """
    code_hash = _get_code_hash()
    build_file = Path(__file__).resolve().parent / "BUILD_INFO.txt"

    # Check if BUILD_INFO.txt exists and has the same hash
    if build_file.exists():
        try:
            existing_content = build_file.read_text()
            # Extract existing hash from the file
            for line in existing_content.splitlines():
                if line.startswith("Code Hash: "):
                    existing_hash = line.split("Code Hash: ")[1].strip()
                    if existing_hash == code_hash:
                        # Hash hasn't changed, no need to update
                        return code_hash
                    break
        except Exception:
            pass  # If we can't read/parse, proceed with update

    # Hash has changed or file doesn't exist, update it
    build_time = datetime.now().isoformat()
    git_commit = _get_git_commit()

    # Optionally sign the code hash
    signature = ""
    if sign_key:
        import hmac

        sig = hmac.new(sign_key.encode("utf-8"), code_hash.encode("utf-8"), hashlib.sha256)
        signature = f"\nSignature: {sig.hexdigest()[:16]}"

    build_info = f"""# Build Information
Code Hash: {code_hash}
Build Time: {build_time}
Git Commit: {git_commit}
Git Branch: {_get_git_branch()}{signature}

This hash is a SHA-256 of all Python source files in the repository.
It provides a deterministic version identifier based on the actual code content.
"""

    build_file.write_text(build_info)
    return code_hash


def _get_git_commit() -> str:
    """Get the current git commit hash."""
    repo_root = Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _get_git_branch() -> str:
    """Get the current git branch name."""
    repo_root = Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


__version__ = _get_code_hash()


if __name__ == "__main__":
    # When run directly, write build info and display version
    # Check for signing key in environment
    sign_key = os.environ.get("CIRIS_BUILD_SIGN_KEY")

    # Check if build info needs updating
    build_file = Path(__file__).resolve().parent / "BUILD_INFO.txt"
    current_hash = _get_code_hash()
    needs_update = True

    if build_file.exists():
        try:
            existing_content = build_file.read_text()
            for line in existing_content.splitlines():
                if line.startswith("Code Hash: "):
                    existing_hash = line.split("Code Hash: ")[1].strip()
                    if existing_hash == current_hash:
                        needs_update = False
                    break
        except Exception:
            pass

    code_hash = write_build_version(sign_key)
    print(f"CIRIS Agent Code Hash: {code_hash}")
    print(f"Git Commit: {_get_git_commit()}")
    print(f"Git Branch: {_get_git_branch()}")
    if sign_key:
        print("Build signed with CIRIS_BUILD_SIGN_KEY")

    if needs_update:
        print("BUILD_INFO.txt has been updated")
    else:
        print("BUILD_INFO.txt is up to date")
