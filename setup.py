"""
Setup configuration for CIRIS Agent.

This enables pip-installable distribution with optional GUI bundling.
The CLI command 'ciris-agent' wraps the existing main.py Click interface.
"""

from pathlib import Path

from setuptools import find_packages, setup

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

# Read requirements
requirements = []
with open("requirements.txt") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Read dev requirements
dev_requirements = []
try:
    with open("requirements-dev.txt") as f:
        dev_requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]
except FileNotFoundError:
    pass

setup(
    name="ciris-agent",
    version=version,
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
            "covenant_1.0b.txt",  # Covenant text file
        ],
        "ciris_engine": [
            "gui_static/**/*",  # GUI assets (if present, bundled by CI)
        ],
    },
    entry_points={
        "console_scripts": [
            "ciris-agent=ciris_engine.cli:main",  # Thin wrapper around main.py
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
        "License :: OSI Approved :: Apache Software License",
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
