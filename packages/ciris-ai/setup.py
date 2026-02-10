"""
Alias package for ciris-agent.

This package exists to reserve the name and redirect users to ciris-agent.
Install ciris-agent directly for the main package.
"""

from setuptools import setup

# Read version from constants.py
version = "1.9.9"
try:
    with open("../../ciris_engine/constants.py") as f:
        for line in f:
            if line.startswith("CIRIS_VERSION"):
                version = line.split('"')[1]
                version = version.split("-")[0]
                break
except Exception:
    pass

setup(
    name="ciris-ai",
    version=version,
    description="Alias for ciris-agent - CIRIS Ethical AI Agent",
    long_description="This is an alias package. Please install `ciris-agent` directly.",
    long_description_content_type="text/plain",
    author="Eric Moore",
    author_email="eric@ciris.ai",
    url="https://github.com/CIRISAI/CIRISAgent",
    install_requires=["ciris-agent"],
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
    ],
)
