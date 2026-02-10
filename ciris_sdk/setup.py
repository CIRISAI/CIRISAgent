"""
Setup configuration for CIRIS SDK.

Async client library for interacting with a running CIRIS Agent instance.
"""

from pathlib import Path

from setuptools import find_packages, setup

# Read the README for long description
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

# Read version from constants.py (sync with main package)
version = "1.9.9"
try:
    with open("../ciris_engine/constants.py") as f:
        for line in f:
            if line.startswith("CIRIS_VERSION"):
                version = line.split('"')[1]
                version = version.split("-")[0]
                break
except Exception:
    pass

setup(
    name="ciris-sdk",
    version=version,
    description="CIRIS SDK - Async Python client for CIRIS Agent API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Eric Moore",
    author_email="eric@ciris.ai",
    url="https://github.com/CIRISAI/CIRISAgent",
    packages=find_packages(exclude=["tests", "tests.*", "examples"]),
    python_requires=">=3.10",
    install_requires=[
        "aiohttp>=3.8.0",
        "pydantic>=2.0.0",
        "websockets>=11.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Framework :: AsyncIO",
    ],
    keywords="ciris ai agent sdk async client api",
    project_urls={
        "Bug Reports": "https://github.com/CIRISAI/CIRISAgent/issues",
        "Source": "https://github.com/CIRISAI/CIRISAgent/tree/main/ciris_sdk",
        "Documentation": "https://github.com/CIRISAI/CIRISAgent/tree/main/ciris_sdk",
    },
)
