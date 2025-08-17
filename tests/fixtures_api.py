"""Fixtures for API-related tests to ensure proper isolation."""

import os
import socket
from typing import Generator

import pytest


def get_free_port() -> int:
    """Get a free port by binding to port 0 and getting the assigned port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))  # noqa: S104 - Test fixture: binding to get free port
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture(autouse=True)
def randomize_api_port(monkeypatch) -> Generator[int, None, None]:
    """
    Automatically randomize API port for all tests to prevent conflicts.
    This fixture is autouse=True, so it applies to all tests automatically.
    """
    # Always randomize port for test isolation
    port = get_free_port()
    monkeypatch.setenv("CIRIS_API_PORT", str(port))
    yield port


@pytest.fixture
def api_port() -> int:
    """Get the current API port being used."""
    return int(os.getenv("CIRIS_API_PORT", "8080"))
