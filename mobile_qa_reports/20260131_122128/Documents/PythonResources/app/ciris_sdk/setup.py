"""Setup configuration for CIRIS SDK."""

from setuptools import find_packages, setup

setup(
    name="ciris-sdk",
    version="0.1.0",
    description="CIRIS SDK for Python",
    author="CIRIS AI",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "aiohttp>=3.8.0",
        "pydantic>=2.0.0",
        "websockets>=11.0",
    ],
)
