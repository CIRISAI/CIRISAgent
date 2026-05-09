"""
Setup configuration for CIRIS Agent.

This enables pip-installable distribution with optional GUI bundling.
The CLI command 'ciris-agent' wraps the existing main.py Click interface.

Platform-specific wheels:
  When a CIRIS Desktop JAR is present in ciris_engine/desktop_app/,
  the wheel is tagged with the matching platform (e.g., macosx_11_0_arm64).
  When no JAR is present, a pure-Python py3-none-any wheel is produced
  for headless server deployments.

Localization:
  The authoritative localization files are in /localization/*.json.
  During build, these are copied to ciris_engine/data/localized/ for bundling.
"""

import shutil
from pathlib import Path

from setuptools import find_packages, setup
from setuptools.command.build_py import build_py as _build_py


class _BuildPyWithLocalization(_build_py):
    """Copy localization files to package data before building."""

    def run(self):
        # Copy localization files to package data directory
        src_dir = Path(__file__).parent / "localization"
        dst_dir = Path(__file__).parent / "ciris_engine" / "data" / "localized"
        dst_dir.mkdir(parents=True, exist_ok=True)

        if src_dir.exists():
            for json_file in src_dir.glob("*.json"):
                shutil.copy2(json_file, dst_dir / json_file.name)

        super().run()


try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
except ImportError:
    _bdist_wheel = None

# Map Compose Desktop JAR platform suffixes to PEP 427 wheel platform tags
_JAR_PLATFORM_MAP = {
    "macos-arm64": "macosx_11_0_arm64",
    "macos-x64": "macosx_10_15_x86_64",
    "linux-x64": "manylinux2014_x86_64",
    "windows-x64": "win_amd64",
}


def _detect_host_wheel_tag():
    """Fallback: derive a PEP 427 platform tag from the current interpreter host.

    Used when a bundled JRE is present but no JAR filename is available to
    imply the target platform.
    """
    import platform
    import sys

    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "macosx_11_0_arm64" if machine in {"arm64", "aarch64"} else "macosx_10_15_x86_64"
    if sys.platform.startswith("linux"):
        return "manylinux2014_x86_64" if machine in {"x86_64", "amd64"} else None
    if sys.platform == "win32":
        return "win_amd64" if machine in {"amd64", "x86_64"} else None
    return None


def _detect_jar_platform():
    """Detect platform from the bundled JAR in ciris_engine/desktop_app/.

    NOTE: JRE bundling was removed to keep wheel size under PyPI's 100MB limit.
    Platform detection is now based solely on the JAR filename.
    """
    desktop_dir = Path(__file__).parent / "ciris_engine" / "desktop_app"
    if not desktop_dir.exists():
        return None
    for jar in desktop_dir.glob("CIRIS-*.jar"):
        # JAR names: CIRIS-macos-arm64-2.0.0.jar, CIRIS-linux-x64-2.0.0.jar, etc.
        stem = jar.stem  # e.g. "CIRIS-macos-arm64-2.0.0"
        for jar_suffix, wheel_tag in _JAR_PLATFORM_MAP.items():
            if jar_suffix in stem:
                return wheel_tag
    return None


if _bdist_wheel is not None:

    class _PlatformBdistWheel(_bdist_wheel):
        """Override bdist_wheel to set platform tag based on bundled JAR."""

        def finalize_options(self):
            super().finalize_options()
            self._detected_platform = _detect_jar_platform()
            if self._detected_platform:
                self.root_is_pure = False

        def get_tag(self):
            if self._detected_platform:
                return "py3", "none", self._detected_platform
            return super().get_tag()

    _cmdclass = {"bdist_wheel": _PlatformBdistWheel, "build_py": _BuildPyWithLocalization}
else:
    _cmdclass = {"build_py": _BuildPyWithLocalization}

# Read the README for long description
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

# Read version from constants.py
version = "1.6.2"  # Will be updated by bump_version.py
try:
    with open("ciris_engine/constants.py") as f:
        for line in f:
            if line.startswith("CIRIS_VERSION"):
                version = line.split('"')[1]
                # Strip "-stable" or other suffixes for PEP 440 compliance
                version = version.split("-")[0]
                break
except Exception:
    pass  # Fall back to hardcoded version if constants.py is not readable

# Read requirements. Explicit utf-8 — comments contain non-ASCII (⚠️, →,
# release notes from upstream releases) and the Windows wheel build runs
# under cp1252 by default, which UnicodeDecodeError's on those bytes.
requirements = []
with open("requirements.txt", encoding="utf-8") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Read dev requirements
dev_requirements = []
try:
    with open("requirements-dev.txt", encoding="utf-8") as f:
        dev_requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]
except FileNotFoundError:
    pass

setup(
    name="ciris-agent",
    version=version,
    cmdclass=_cmdclass,
    description="CIRIS: Ethical AI Agent with Consensual Evolution Protocol",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Eric Moore",
    author_email="eric@ciris.ai",
    url="https://github.com/CIRISAI/CIRISAgent",
    packages=find_packages(exclude=["tests", "tests.*", "docs", "tools.test_*"]),
    py_modules=["main"],  # Include main.py at root level
    include_package_data=True,  # CRITICAL - includes non-Python files from MANIFEST.in
    package_data={
        "ciris_engine.data": [
            "accord_1.2b.txt",  # Accord text file (v1.2-Beta)
            "accord_1.2b_compressed.txt",  # Compressed accord for testing
            "localized/*.json",  # Backend localization files (copied from /localization/)
            "localized/*.txt",  # Localized ACCORD + comprehensive guide text files (guides
                                # migrated from .md → .txt in 2.8.5 alongside the repo-root
                                # and docs/ consolidation; staging script can now use a
                                # clean .md=devnotes denylist)
            "agent_experience.txt",  # Agent self-help / introspection content (was at
                                     # docs/agent_experience.md pre-2.8.5; CWD-relative
                                     # reader broke on installs)
            "geo/cities.db",  # GeoNames cities database for location typeahead
        ],
        "ciris_engine.config": [
            "*.json",  # Pricing and configuration data
        ],
        "ciris_engine.logic.dma": [
            "prompts/*.yml",  # DMA prompt templates (English)
            "prompts/localized/*/*.yml",  # Localized DMA prompt templates
        ],
        "ciris_engine.logic.conscience": [
            # Same shape as DMA prompts above. The conscience system reads
            # entropy/coherence/optimization_veto/epistemic_humility prompt
            # templates from these YML files at runtime; missing them on a
            # wheel install means the conscience falls back to inline strings
            # (silent degradation). Added in 2.8.5 alongside the canonical
            # staging work — staging includes them, wheel must too, or the
            # runtime walk hash diverges from the signed manifest.
            "prompts/*.yml",
            "prompts/localized/*/*.yml",
        ],
        "ciris_engine.logic.persistence": [
            "migrations/sqlite/*.sql",  # SQLite database migrations
            "migrations/postgres/*.sql",  # PostgreSQL database migrations
        ],
        "ciris_engine.logic.accord": [
            "bip39_english.txt",  # BIP39 wordlist used by accord/extractor.py
                                   # for mnemonic generation. Load-bearing —
                                   # extractor.py:49 reads from package dir
                                   # via Path(__file__).parent. Wasn't shipped
                                   # in 2.8.4 wheels (extractor fell through
                                   # to /app/tools/security/bip39_english.txt
                                   # which only exists in docker, breaks elsewhere).
        ],
        "ciris_engine": [
            "ciris_templates/*.yaml",  # Bundled agent identity templates
            "desktop_app/*.jar",  # CIRIS Desktop app (Kotlin Compose)
            # NOTE: JRE no longer bundled to keep wheel under PyPI's 100MB limit.
            # Users must have Java 17+ installed; CLI provides install instructions.
        ],
    },
    entry_points={
        "console_scripts": [
            "ciris-agent=ciris_engine.cli:main",  # Desktop app (default) or server mode
            "ciris-server=ciris_engine.cli:server",  # Headless API server
            "ciris-desktop=ciris_engine.cli:desktop",  # Desktop app launcher
        ],
        # Adapter discovery entry points - eliminates hardcoded KNOWN_MODULAR_SERVICES list
        # Each entry point maps adapter_name -> module path for manifest loading
        "ciris.adapters": [
            "ciris_hosted_tools=ciris_adapters.ciris_hosted_tools",
            "ciris_verify=ciris_adapters.ciris_verify",
            "external_data_sql=ciris_adapters.external_data_sql",
            "home_assistant=ciris_adapters.home_assistant",
            "mcp_client=ciris_adapters.mcp_client",
            "mcp_common=ciris_adapters.mcp_common",
            "mcp_server=ciris_adapters.mcp_server",
            "mock_llm=ciris_adapters.mock_llm",
            "navigation=ciris_adapters.navigation",
            "reddit=ciris_adapters.reddit",
            "sample_adapter=ciris_adapters.sample_adapter",
            "weather=ciris_adapters.weather",
        ],
    },
    install_requires=requirements,
    extras_require={
        "dev": dev_requirements,
    },
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
    ],
    keywords="ai agent ethical-ai autonomous-agent discord-bot api-server",
    project_urls={
        "Bug Reports": "https://github.com/CIRISAI/CIRISAgent/issues",
        "Source": "https://github.com/CIRISAI/CIRISAgent",
        "Documentation": "https://github.com/CIRISAI/CIRISAgent/tree/main/docs",
    },
)
