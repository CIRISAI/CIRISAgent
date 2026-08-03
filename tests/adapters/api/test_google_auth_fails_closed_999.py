"""#999 — Google ID-token verification fails closed. No unverified path exists.

`_verify_google_id_token` caught `asyncio.TimeoutError` and fell back to
`_decode_google_jwt_locally`, whose own docstring read:

    WARNING: This does NOT verify the token signature.

The justification was *"the token came from the Google Sign-In SDK on the
device, which already verified it cryptographically."* That is **transport
provenance**, and HTTP cannot establish it — `/v1/auth/oauth/native` is a public
endpoint and anyone can POST a JWT. The fallback read `exp` and `iss` out of the
**unverified payload** and trusted them.

So an attacker who could make the outbound call to `oauth2.googleapis.com` time
out — a hostile network, a DNS hold, a slow enough link — converted a forged
`id_token` into a real CIRIS session.

The general rule this violated, and the reason it is worth a gate rather than
just a fix: **a timeout is an availability failure, and an authentication
control may never become more permissive when a dependency is unreachable.**
Every degraded path must be at least as strict as the healthy one.

Offline sign-in is a genuine capability and removing the fallback removes it.
Restoring it correctly means verifying the signature against **cached Google
JWKS** — offline, still verified — not trusting the token. Tracked as the
follow-up on #999.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

AUTH = pathlib.Path("ciris_engine/logic/adapters/api/routes/auth.py")

#: Helpers that decode a credential without verifying it. None may exist in the
#: auth route module: an unverified decoder sitting next to a verifier is a
#: loaded gun — the next `except` that reaches for it silently re-opens the
#: bypass, exactly as this one did.
FORBIDDEN_HELPERS = ("_decode_google_jwt_locally",)


def test_no_unverified_token_decoder_exists() -> None:
    tree = ast.parse(AUTH.read_text(encoding="utf-8"), filename=str(AUTH))
    defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    present = sorted(set(FORBIDDEN_HELPERS) & defined)
    assert not present, (
        f"unverified credential decoder(s) back in auth.py: {present}. "
        f"Verify against cached JWKS instead — offline is fine, unverified is not."
    )


def test_timeout_does_not_become_an_authentication_decision() -> None:
    """The specific regression: the TimeoutError handler must refuse, not fall back.

    Asserted on the AST of the handler rather than by string search, so a
    comment explaining the history (which necessarily names the old helper)
    cannot satisfy or break the check.
    """
    from ciris_engine.logic.adapters.api.routes import auth

    tree = ast.parse(inspect.getsource(auth._verify_google_id_token))
    timeout_handlers = [
        h
        for h in ast.walk(tree)
        if isinstance(h, ast.ExceptHandler)
        and h.type is not None
        and "TimeoutError" in ast.dump(h.type)
    ]
    assert timeout_handlers, "the timeout handler vanished — check this test still tracks the code"

    for handler in timeout_handlers:
        returns = [n for n in ast.walk(handler) if isinstance(n, ast.Return) and n.value is not None]
        assert not returns, (
            "the Google-timeout handler RETURNS a user identity. A timeout is an availability "
            "failure; turning it into an authentication decision is the #999 bypass. Raise."
        )
        raises = [n for n in ast.walk(handler) if isinstance(n, ast.Raise)]
        assert raises, "the Google-timeout handler must raise — fail closed"


def test_every_verification_failure_path_raises() -> None:
    """No handler in the verifier may produce an identity. Generalised from the
    one that did, because the next one will be written by someone who has not
    read this file."""
    from ciris_engine.logic.adapters.api.routes import auth

    tree = ast.parse(inspect.getsource(auth._verify_google_id_token))
    offenders = []
    for handler in [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]:
        if any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(handler)):
            offenders.append(ast.dump(handler.type) if handler.type else "bare except")
    assert not offenders, (
        f"exception handlers in _verify_google_id_token that return an identity: {offenders}. "
        f"A degraded path must be at least as strict as the healthy one."
    )
