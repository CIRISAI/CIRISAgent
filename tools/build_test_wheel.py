#!/usr/bin/env python3
"""
Build test wheel with bundled GUI for local testing.

This script mimics the GitHub Actions CI build process:
1. Clones CIRISGUI-Standalone repository
2. Builds GUI static assets with Next.js
3. Copies assets to ciris_engine/gui_static/
4. Builds Python wheel with bundled GUI
5. Verifies wheel contents
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[0;31m"
    NC = "\033[0m"  # No Color


def print_success(msg: str) -> None:
    """Print success message in green."""
    print(f"{Colors.GREEN}✅ {msg}{Colors.NC}")


def print_warning(msg: str) -> None:
    """Print warning message in yellow."""
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.NC}")


def print_error(msg: str) -> None:
    """Print error message in red."""
    print(f"{Colors.RED}❌ {msg}{Colors.NC}")


def print_info(msg: str) -> None:
    """Print info message."""
    print(f"ℹ️  {msg}")


def run_command(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    print_info(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=False, text=True)


def main() -> int:
    """Main build script."""
    print("==================================")
    print("CIRIS Agent Test Wheel Builder")
    print("==================================")
    print()

    # Get project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)

    # Step 1: Clean previous builds
    print("Step 1: Cleaning previous builds...")
    dirs_to_clean = ["dist", "build", "ciris_engine/gui_static", "cirisgui_temp"]
    for d in dirs_to_clean:
        dir_path = project_root / d
        if dir_path.exists():
            shutil.rmtree(dir_path)

    # Also remove egg-info directories
    for egg_info in project_root.glob("*.egg-info"):
        shutil.rmtree(egg_info)

    print_success("Cleaned build directories")
    print()

    # Step 2: Clone and build GUI
    print("Step 2: Building GUI assets...")
    gui_temp_dir = project_root / "cirisgui_temp"

    print_info("Cloning CIRISGUI-Standalone repository...")
    if not gui_temp_dir.exists():
        run_command(["git", "clone", "https://github.com/CIRISAI/CIRISGUI-Standalone.git", str(gui_temp_dir)])
    else:
        print_warning("Using existing cirisgui_temp directory")

    # Find the Next.js app directory (look for next.config.mjs/js)
    print_info("Finding Next.js app directory...")
    gui_dir = None

    # Look for next.config.mjs or next.config.js
    for config_file in list(gui_temp_dir.rglob("next.config.mjs")) + list(gui_temp_dir.rglob("next.config.js")):
        gui_dir = config_file.parent
        print_success(f"Found Next.js app in: {gui_dir}")
        break

    # Fallback to looking for package.json with "next" dependency
    if not gui_dir:
        for package_json in gui_temp_dir.rglob("package.json"):
            try:
                import json

                pkg_data = json.loads(package_json.read_text())
                if "next" in pkg_data.get("dependencies", {}) or "next" in pkg_data.get("devDependencies", {}):
                    gui_dir = package_json.parent
                    print_success(f"Found Next.js app via package.json in: {gui_dir}")
                    break
            except Exception:
                continue

    if not gui_dir:
        print_error("Could not find Next.js app in CIRISGUI-Standalone repo")
        return 1

    # Verify next.config exists
    next_config = gui_dir / "next.config.mjs"
    if not next_config.exists():
        next_config = gui_dir / "next.config.js"

    if not next_config.exists():
        print_warning(f"next.config not found in {gui_dir}")
    else:
        print_success(f"Found {next_config.name}")

    # Configure for static export
    print_info("Configuring for static export...")
    if next_config.exists():
        config_content = next_config.read_text()
        if "output" not in config_content or '"export"' not in config_content:
            print_warning("Adding output: 'export' to next.config.mjs")
            # Backup
            shutil.copy(next_config, next_config.with_suffix(".mjs.bak"))
            # Add output export
            config_content = config_content.replace("const nextConfig = {", "const nextConfig = {\n  output: 'export',")
            next_config.write_text(config_content)
        print_success("Static export configuration verified")

    # Install dependencies
    print_info("Installing Node.js dependencies...")
    run_command(["npm", "ci"], cwd=gui_dir)

    # Build static assets
    print_info("Building static assets (this may take a few minutes)...")
    run_command(["npm", "run", "build"], cwd=gui_dir)

    # Check for static export
    build_output = None
    if (gui_dir / "out").exists():
        print_success("Using static export from out/")
        build_output = gui_dir / "out"
    elif (gui_dir / ".next/standalone").exists():
        print_success("Using standalone build from .next/standalone")
        build_output = gui_dir / ".next/standalone"
    elif (gui_dir / ".next/static").exists():
        print_success("Using static build from .next/static")
        build_output = gui_dir / ".next/static"
    else:
        print_error("No build output found (checked: out/, .next/standalone, .next/static)")
        return 1

    file_count = len(list(build_output.rglob("*")))
    print_success(f"GUI build complete - {file_count} files generated")
    print()

    # Step 3: Copy GUI assets to ciris_engine
    print("Step 3: Copying GUI assets to ciris_engine/gui_static/...")
    gui_static_dir = project_root / "ciris_engine/gui_static"
    gui_static_dir.mkdir(parents=True, exist_ok=True)

    # Copy all files
    shutil.copytree(build_output, gui_static_dir, dirs_exist_ok=True)

    # Verify copy
    copied_files = len(list(gui_static_dir.rglob("*")))
    if copied_files < 5:
        print_warning(f"Very few GUI files found: {copied_files}")
    else:
        print_success(f"Copied {copied_files} GUI files to ciris_engine/gui_static/")
    print()

    # Step 4: Install build tools
    print("Step 4: Installing Python build tools...")
    run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "build", "twine"])
    print_success("Build tools installed")
    print()

    # Step 5: Build wheel
    print("Step 5: Building Python wheel...")
    run_command([sys.executable, "-m", "build", "--wheel"])
    print_success("Wheel built successfully")
    print()

    # Step 6: Verify wheel contents
    print("Step 6: Verifying wheel contents...")
    dist_dir = project_root / "dist"
    wheel_files = list(dist_dir.glob("*.whl"))

    if not wheel_files:
        print_error("No wheel file found in dist/")
        return 1

    wheel_file = wheel_files[0]
    print_info(f"Wheel file: {wheel_file}")

    print()
    print_info("Checking for gui_static assets in wheel...")
    result = subprocess.run(["unzip", "-l", str(wheel_file)], capture_output=True, text=True, check=False)

    gui_static_files = [line for line in result.stdout.split("\n") if "gui_static" in line]
    if gui_static_files:
        print_success(f"Found {len(gui_static_files)} gui_static files in wheel")
        for line in gui_static_files[:10]:
            print(f"  {line.strip()}")
        if len(gui_static_files) > 10:
            print(f"  ... and {len(gui_static_files) - 10} more")
    else:
        print_warning("No gui_static files found in wheel")

    print()
    print_info("Total files in wheel:")
    total_line = result.stdout.split("\n")[-2]
    print(f"  {total_line}")
    print()

    # Step 7: Cleanup
    print("Step 7: Cleaning up temporary files...")
    if gui_temp_dir.exists():
        shutil.rmtree(gui_temp_dir)
    print_success("Cleanup complete")
    print()

    # Final summary
    print("==================================")
    print("Build Complete!")
    print("==================================")
    print()
    print_success(f"Wheel file: {wheel_file}")
    print()
    print_info("To install locally:")
    print(f"  pip install {wheel_file}")
    print()
    print_info("To test the installation:")
    print(f"  pip install {wheel_file}")
    print("  ciris-agent --help")
    print()
    print_info("To upload to PyPI (if you have credentials):")
    print(f"  python -m twine upload {wheel_file}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
