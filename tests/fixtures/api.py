"""API fixtures for tests."""

import socket

import pytest


@pytest.fixture
def random_api_port():
    """Get a random available port for API testing."""
    # Find an available port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Bind to localhost only for tests (not all interfaces)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]

    # Port is now released and should be available
    # There's a small race condition here, but it's acceptable for tests
    return port


@pytest.fixture
def free_api_port():
    """Alternative name for random_api_port."""
    return random_api_port()
