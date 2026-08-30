"""The node proxy builds an outbound URL from an inbound one. Guard the path.

Sonar flagged this as MAJOR — "do not construct the URL's path from
user-controlled data" — and it was right. The prefix allow-list alone is not
enough: `/v1/setup/../../admin` starts with `/v1/setup/` and so passes it, and
the traversal then resolves on the way out, reaching a node route the prefix was
supposed to fence off.

The host is a hardcoded loopback literal and is never derived from input. This
file is about the PATH, which is the half that is.

There is a second reason to keep these cases: the proxy's whole purpose is to
make the agent one address, so anything that gets through here reaches the
substrate's own surface — federation, self, accord, and the ownership claim.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.adapters.api.routes.node_proxy import _is_node_owned, _safe_forward_path


@pytest.mark.parametrize(
    "path",
    [
        "setup/owned-nodes",
        "setup/claim-remote",
        "federation/consent",
        "self/identity",
        "accord/canonical/servers",
        "federation/keys/abc-123_x.y~z",
    ],
)
def test_ordinary_routes_forward_unchanged(path: str) -> None:
    """A real REST path must survive exactly, or the proxy breaks the product."""
    assert _safe_forward_path(path) == path


@pytest.mark.parametrize(
    ("path", "why"),
    [
        ("setup/../../admin", "traversal that still satisfies the prefix check"),
        ("../secrets", "traversal from the root"),
        ("setup/..", "bare parent segment"),
        ("/etc/passwd", "absolute path"),
        ("setup/x?a=b", "query injection into the outbound URL"),
        ("setup/x#frag", "fragment injection"),
        ("setup/x\r\nHost: evil", "CRLF request splitting"),
        ("setup/x\nY: z", "bare LF"),
        ("setup/x%2F..%2Fy", "percent-encoded separator, decoded downstream"),
        ("setup/a b", "space"),
        ("setup/<script>", "angle brackets"),
        ("setup/x@evil.com", "authority-shaped content"),
        ("setup/x\x00y", "NUL"),
    ],
)
def test_dangerous_paths_are_refused(path: str, why: str) -> None:
    """None means the request is rejected outright, never forwarded."""
    assert _safe_forward_path(path) is None, why


def test_the_prefix_check_alone_would_have_allowed_the_traversal() -> None:
    """Why both checks exist.

    This is the case that makes the point: the allow-list says yes, and only the
    path validator says no. Remove either and the other does not cover it.
    """
    traversal = "setup/../../admin"
    assert _is_node_owned(traversal) is True, "the prefix check passes it"
    assert _safe_forward_path(traversal) is None, "the path check must catch it"


@pytest.mark.parametrize(
    ("path", "owned"),
    [
        ("setup/owned-nodes", True),
        ("federation/consent", True),
        ("self/identity", True),
        ("system/health", False),
        ("wa/manual-defer", False),
        ("definitely-not-a-route", False),
    ],
)
def test_only_the_substrate_surface_is_forwarded(path: str, owned: bool) -> None:
    """Everything else must keep 404ing.

    `wa/manual-defer` is not arbitrary: TestNoBypassEndpoints asserts that route
    does NOT exist. When this proxy was a catch-all it answered 502 for it, and
    a check whose purpose is proving a bypass route is absent could no longer
    tell absent from unreachable.
    """
    assert _is_node_owned(path) is owned
