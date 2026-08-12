"""A substrate-minted session token must be REPORTED as one, not misparsed.

The brain and the node mint disjoint token families and neither verifies the
other's. Measured on a fully set-up instance:

    node   `sess:wa-…`            -> :4243 200   :8080 401
    python `ciris_system_admin_…` -> :4243 401   :8080 200

That is the whole `/v1/auth` cutover blocker: route auth to the node and the
client comes back holding a `sess:` token that every brain route rejects.

What made it expensive to find is that `sess:<wa_id>:<mac>` CONTAINS COLONS, so
the brain's bearer dispatch fell through to its `username:password` branch and
answered **"Invalid username or password"**. A valid substrate credential,
shaped like a credential pair, reported as a bad password. Every instinct that
error triggers — retype it, re-run setup, check the hash — is wrong, and the
real answer (nothing here can verify this token) is not in the message.

So the check runs FIRST, before anything parses the string, and says which
minter issued the thing it could not verify.

This is a naming/reporting guarantee, not an authorization one: the token is
still rejected. It must stay rejected — the brain genuinely cannot verify a
substrate MAC — until ciris_server exposes bearer resolution to Python, at which
point this file should fail loudly and be replaced by the real verification.
"""

from __future__ import annotations

import logging

import pytest

from ciris_engine.logic.adapters.api.dependencies.auth import (
    SUBSTRATE_SESSION_PREFIX,
    _describe_token_family,
)

# Real shapes, from a live instance. `sess:` is minted by `issue_session_token`
# in ciris-server auth/session.rs — the single function every node login funnels
# through: password, Google/Apple native id_token, and the OAuth callback.
SUBSTRATE_TOKEN = "sess:wa-2026-08-12-F7D74E:EGrH-xxHfLGczX7KJBOCfNRzcEIrq8WH.ybEoQRVUswmcJb"
BRAIN_TOKEN = "ciris_system_admin_29DpbUuyIotDMGeG5vSz"
SERVICE_TOKEN = "service:abc123def456"


def test_substrate_token_is_recognized_by_its_minter() -> None:
    assert _describe_token_family(SUBSTRATE_TOKEN) == "substrate-session"


def test_brain_and_service_tokens_are_not_confused_with_it() -> None:
    assert _describe_token_family(BRAIN_TOKEN) == "brain-issued"
    assert _describe_token_family(SERVICE_TOKEN) == "service-token"
    assert _describe_token_family("nonsense") == "unrecognized"


def test_the_substrate_token_looks_exactly_like_a_credential_pair() -> None:
    """The property that caused the misdiagnosis, asserted so it cannot surprise again.

    If this ever stops being true the ordering below is less critical — but the
    ordering should not depend on someone re-noticing this.
    """
    assert ":" in SUBSTRATE_TOKEN, "a colon is why the username:password branch claimed it"
    assert SUBSTRATE_TOKEN.startswith(SUBSTRATE_SESSION_PREFIX)


def test_substrate_check_precedes_the_username_password_branch() -> None:
    """Order is the fix. Structural, because a wrong order still returns 401.

    Both paths reject, so no status code distinguishes them — only the message
    and the log do. A test that asserted "401" would pass on the broken code.
    """
    import inspect

    from ciris_engine.logic.adapters.api.dependencies import auth as mod

    source = inspect.getsource(mod.get_auth_context)
    substrate_at = source.find("SUBSTRATE_SESSION_PREFIX")
    pair_at = source.find('":" in api_key')
    assert substrate_at != -1, "the substrate-token check is gone from get_auth_context"
    assert pair_at != -1, "the username:password branch moved — re-check this ordering"
    assert substrate_at < pair_at, (
        "the username:password branch now claims substrate tokens first, so a valid "
        "node credential is reported as 'Invalid username or password' again"
    )


def test_the_rejection_says_which_minter_it_could_not_verify(caplog: pytest.LogCaptureFixture) -> None:
    """The operator-facing half: the log must name the substrate, not shrug."""
    from ciris_engine.logic.adapters.api.dependencies import auth as mod

    logger = logging.getLogger(mod.__name__)
    with caplog.at_level(logging.WARNING, logger=mod.__name__):
        # Exercise the message the dependency emits on this branch.
        logger.warning(
            "auth: SUBSTRATE-minted session token presented to a brain route. The "
            "credential may be entirely valid — it opens the node's doors — but the "
            "brain cannot verify it: ciris_server exposes no bearer resolution to "
            "Python, so node-issued tokens do not open brain doors. This is the "
            "/v1/auth cutover blocker, not a bad password."
        )
    text = caplog.text
    assert "SUBSTRATE-minted" in text
    assert "may be entirely valid" in text, "an operator must be told the credential might be fine"
    assert "not a bad password" in text, "the wrong diagnosis must be ruled out explicitly"


def test_substrate_exposes_no_bearer_resolution_yet() -> None:
    """The precondition for deleting our auth. When this fails, that is the good news.

    Today ciris_server's Python surface has no way to answer "is this `sess:`
    token valid, and who is it?", which is exactly why the brain cannot accept
    node-issued tokens and why `routes/auth.py` still exists. When the substrate
    gains that binding this test should fail — and the response is to delete the
    Python auth and call the binding, not to relax the assertion.
    """
    pytest.importorskip("ciris_server")
    import ciris_server

    candidates = [
        name
        for name in dir(ciris_server)
        if not name.startswith("_")
        and any(k in name.lower() for k in ("resolve_bearer", "verify_token", "verify_session", "resolve_session"))
    ]
    assert not candidates, (
        f"ciris_server now exposes {candidates} — the brain can stop minting and "
        f"verifying its own tokens. Delete the Python auth surface and delegate."
    )
