"""The brain verifies session tokens by ASKING THE SUBSTRATE, and never guesses.

`ciris_server.resolve_bearer` (CIRISServer#396) is the same verification the
node's own doors use, so a token minted by ANY node login mechanism — password,
Google or Apple native `id_token`, the OAuth callback, anything added later —
opens brain routes without a second implementation here. Upstream funnels all of
them through one `issue_session_token`, so there is exactly one thing to verify.

Measured on a live fold, with `routes/auth.py` deleted:

    node login -> sess:wa-2026-08-12-8B96B0:…
      :8080 /v1/agent/status       200      (was 401)
      :8080 /v1/telemetry/unified  200
      :8080 /v1/audit/entries      200
      :4243 /v1/auth/me   user_id=wa-2026-08-12-8B96B0 role=SYSTEM_ADMIN perms=22
      :8080 /v1/auth/me   user_id=wa-2026-08-12-8B96B0 role=SYSTEM_ADMIN perms=22
    forged MAC -> 401 on BOTH surfaces

THE CONTRACT THIS FILE EXISTS TO PROTECT:

    None      -> the substrate JUDGED the token and it is invalid  -> 401
    exception -> the substrate COULD NOT judge it                  -> 503

Collapsing those with `except Exception: return None` turns a store outage into a
silent fleet-wide lockout whose logs read exactly like everyone presenting bad
tokens at once. Upstream says so in the exception text itself — "the token was
NOT judged; do not treat this as a rejection" — because that collapse is the
tempting one to write. Verified against the real binding outside a composed node:

    RuntimeError: resolve_bearer: no in-process persist Engine — the node is not
    composed in this process, so this CANNOT be read as 'the token is invalid'
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from ciris_engine.logic.adapters.api.dependencies import auth as auth_mod
from ciris_engine.logic.adapters.api.dependencies.auth import (
    SUBSTRATE_SESSION_PREFIX,
    _describe_token_family,
)


def _strip_docstring(source: str) -> str:
    """Source with the function's docstring removed.

    A source scan that includes the docstring tests the documentation, not the
    behaviour — and these docstrings quote the very anti-patterns being banned.
    """
    tree = ast.parse(textwrap.dedent(source))
    func = tree.body[0]
    assert isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
    body = func.body[1:] if ast.get_docstring(func) is not None else func.body
    return "\n".join(ast.unparse(node) for node in body)


SUBSTRATE_TOKEN = "sess:wa-2026-08-12-8B96B0:EGrH-xxHfLGczX7KJBOCfNRzcEIrq8WH.ybEoQRVUswmcJb"
BRAIN_TOKEN = "ciris_system_admin_29DpbUuyIotDMGeG5vSz"
SERVICE_TOKEN = "service:abc123def456"


def test_token_families_are_told_apart() -> None:
    assert _describe_token_family(SUBSTRATE_TOKEN) == "substrate-session"
    assert _describe_token_family(BRAIN_TOKEN) == "brain-issued"
    assert _describe_token_family(SERVICE_TOKEN) == "service-token"
    assert _describe_token_family("nonsense") == "unrecognized"


def test_the_substrate_token_looks_exactly_like_a_credential_pair() -> None:
    """Why the dispatch order below is load-bearing.

    `sess:<wa_id>:<mac>` contains colons, so before this was handled first the
    bearer dispatch fell through to `username:password` and answered "Invalid
    username or password" — a valid substrate credential reported as a bad
    password. Every instinct that error triggers is wrong.
    """
    assert ":" in SUBSTRATE_TOKEN
    assert SUBSTRATE_TOKEN.startswith(SUBSTRATE_SESSION_PREFIX)


def test_substrate_branch_precedes_the_username_password_branch() -> None:
    """Structural, because a wrong order is not visible in a status code.

    Misparsed → 401. Correctly rejected → 401. A test asserting 401 passes on the
    broken code, so the ordering itself is the thing to assert.
    """
    source = inspect.getsource(auth_mod.get_auth_context)
    substrate_at = source.find("SUBSTRATE_SESSION_PREFIX")
    pair_at = source.find('":" in api_key')
    assert substrate_at != -1, "the substrate-session branch is gone from get_auth_context"
    assert pair_at != -1, "the username:password branch moved — re-check this ordering"
    assert substrate_at < pair_at, (
        "the username:password branch now claims substrate tokens first, so a valid "
        "node credential is reported as 'Invalid username or password' again"
    )


def test_the_brain_does_not_verify_tokens_itself() -> None:
    """The DRY property: one verifier, and it is not us.

    If this handler ever grows its own MAC check, prefix parse, or user lookup,
    the two implementations are back and they will drift — which is the whole
    reason `routes/auth.py` existed and had to go.
    """
    source = inspect.getsource(auth_mod._handle_substrate_session_auth)
    assert "resolve_bearer" in source, "the brain must delegate, not decide"
    for smell in ("hmac", "hashlib", "sha256", "compare_digest", "split(':')", 'split(":")'):
        assert smell not in source, (
            f"{smell!r} in the session handler — the brain is verifying identity itself again"
        )


def test_an_outage_is_never_reported_as_a_rejection() -> None:
    """503 vs 401, asserted on the source, since both need a live node to observe.

    The failure this guards is silent and total: with `except Exception: return
    None`, an identity-store outage logs as every user suddenly presenting bad
    tokens, and the fix looks like a credential problem.
    """
    # The 503 lives in the SHARED resolver, which both authenticators call —
    # `dependencies/auth.py` (AuthContext) and `api/auth.py` (TokenData). When only
    # the first knew about substrate tokens, /v1/partnership, /v1/dsar, /v1/my_data
    # and /v1/connectors 401'd on a credential the rest of the API accepted.
    source = inspect.getsource(auth_mod.resolve_substrate_session)
    # Scan the CODE, not the prose. The docstring deliberately quotes the
    # anti-pattern (`except Exception: return None`) to warn against it, and a
    # scan over the whole source matches its own documentation — the exact
    # self-referential trap this suite exists to avoid.
    code = _strip_docstring(source)
    assert "HTTP_503_SERVICE_UNAVAILABLE" in code, (
        "a substrate that COULD NOT judge the token must answer 503, not 401"
    )
    assert "return None" not in code, (
        "swallowing the substrate's exception into None converts an outage into a "
        "fleet-wide lockout that reads as bad credentials"
    )
    # The 401 must be reachable ONLY from the explicit None verdict.
    none_at = source.find("if resolved is None")
    unauth_at = source.find("HTTP_401_UNAUTHORIZED")
    assert none_at != -1 and unauth_at != -1
    assert none_at < unauth_at, "401 must follow from the substrate's explicit None verdict"


def test_actor_is_read_from_the_resolution() -> None:
    """A delegated grant acts with the owner's authority AS the delegate.

    Logging `wa_id` alone would record the owner as having done what a delegate
    did, which is the wrong name on an audited action.
    """
    source = inspect.getsource(auth_mod._handle_substrate_session_auth)
    assert '"actor"' in source or "'actor'" in source, "the delegate's identity is dropped"


def test_substrate_binding_is_present() -> None:
    """The precondition. Its absence is what kept `routes/auth.py` alive."""
    pytest.importorskip("ciris_server")
    import ciris_server

    assert hasattr(ciris_server, "resolve_bearer"), (
        "ciris_server.resolve_bearer is gone — the brain has no verifier and every "
        "node-issued token will 503. Pin a wheel that carries it (CIRISServer#396)."
    )


def test_binding_raises_rather_than_judging_when_it_cannot_check() -> None:
    """Run against the REAL binding, outside a composed node.

    This is the property the whole contract rests on, so it is checked against
    the artifact rather than assumed from the docs.
    """
    pytest.importorskip("ciris_server")
    import ciris_server

    if not hasattr(ciris_server, "resolve_bearer"):
        pytest.skip("binding not present in this wheel")

    with pytest.raises(Exception) as excinfo:  # noqa: PT011 — the type is upstream's choice
        ciris_server.resolve_bearer("sess:wa-2026-01-01-ABCDEF:FORGED")

    message = str(excinfo.value).lower()
    assert "resolve_bearer" in message
    assert any(
        phrase in message for phrase in ("cannot be read as", "not judged", "cannot verify")
    ), (
        f"the no-engine path must say it did NOT judge the token; got: {excinfo.value!r}. "
        f"A bare error here invites the caller to treat it as a rejection."
    )


def test_python_auth_routes_are_gone() -> None:
    """The deletion this enabled, asserted so it cannot quietly come back."""
    from pathlib import Path

    assert not Path("ciris_engine/logic/adapters/api/routes/auth.py").exists(), (
        "routes/auth.py is back — the brain is minting and verifying its own "
        "identity again alongside the substrate's"
    )


def test_both_authenticators_use_the_same_resolver() -> None:
    """Two adapters onto one resolver is fine; two resolvers is how they drift.

    This adapter has two authenticators, reached by different route families. The
    substrate deletion taught only one of them about `sess:` tokens, and Staged QA
    caught the other 401ing on a valid credential — after the unit shard was green,
    because no unit test has a node behind it.
    """
    from ciris_engine.logic.adapters.api import auth as legacy_mod

    legacy = inspect.getsource(legacy_mod.get_current_user)
    assert "resolve_substrate_session" in legacy, (
        "api/auth.py no longer delegates — node-issued tokens will 401 on "
        "/v1/partnership, /v1/dsar, /v1/my_data and /v1/connectors"
    )
    # Neither caller may re-implement the verification. Docstrings stripped —
    # they NAME `ciris_server.resolve_bearer` while explaining why callers must not
    # call it, and scanning the prose would flag the documentation as the offence.
    for src in (
        _strip_docstring(legacy),
        _strip_docstring(inspect.getsource(auth_mod._handle_substrate_session_auth)),
    ):
        assert "ciris_server.resolve_bearer" not in src, (
            "a caller is calling the substrate directly instead of the shared "
            "resolver — the 503/401 contract will drift between the two surfaces"
        )
