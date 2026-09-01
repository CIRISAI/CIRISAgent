"""Asked for all certificates, answered with some, said so only in a WARNING.

FIELD FAILURE (2026-09-01). Immediately before minting the duplicate ROOT, setup
counted what was already there:

    WARNING list_wa_certificates(active_only=False) is unsupported under persist;
            returning active-only set (CIRISAgent#763).
    INFO    CIRIS_USER_CREATE: Existing WAs before creation: 0

Two rows held that identity at that moment. The count was 0.

THE CLASS. A caller asked a question the backend cannot answer, and the backend
answered a DIFFERENT question — narrower, plausible, and wrong — reporting the
substitution at WARNING level to a log nobody reads mid-setup. The caller has no
way to distinguish "there are none" from "I did not look at all of them", so it
proceeds as if it knows.

This is the same shape as the two-holder lockout and the actor/node key split:
an interface that answers with less than it was asked for, and a caller that
cannot tell.

`active_only=False` exists precisely to see retired rows — the provisional OAuth
cert is retired, and whether it is still live is exactly what setup needs to
know. Silently dropping the one distinction the parameter requests makes the
parameter a lie.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    strict=True,
    reason="list_wa_certificates(active_only=False) silently returns the active-only set (CIRISAgent#763)",
)
def test_asking_for_inactive_certificates_does_not_silently_drop_them(monkeypatch) -> None:
    """Either answer the question, or refuse it — do not answer a smaller one.

    A caller that must reason about retired rows (setup, deciding whether an
    identity is free) cannot build on a result that quietly omits them.
    """
    import json

    from ciris_engine.logic.persistence.stores import authentication_store as store

    rows = [
        {"wa_id": "wa-2026-09-01-3F4F60", "role": "root", "active": True, "name": "live"},
        {"wa_id": "oauth-google-108898137212622955874", "role": "observer", "active": False, "name": "retired"},
    ]

    class _Engine:
        def wa_cert_list_by_role(self, role, limit=1000):
            return json.dumps([r for r in rows if r["role"] == role and r["active"]])

    monkeypatch.setattr(store, "_get_engine", lambda: _Engine())
    got = store.list_wa_certificates(active_only=False)

    assert len(got) == 2, (
        "the retired row was dropped from a query that explicitly asked for it; "
        "setup used this count (0) to conclude the identity was free"
    )


@pytest.mark.xfail(
    strict=True,
    reason="the narrowing is reported only as a log WARNING; callers get no signal they can branch on",
)
def test_a_caller_can_tell_that_the_answer_was_narrowed() -> None:
    """If the query cannot be honoured, the caller must be able to KNOW.

    A WARNING in a log is not a return value. Setup cannot branch on it, so it
    treated a partial answer as a complete one. Raising, or returning a result
    that carries its own completeness, both work; silence does not.
    """
    import inspect

    from ciris_engine.logic.persistence.stores import authentication_store as store

    src = inspect.getsource(store.list_wa_certificates)
    assert "raise" in src or "complete" in src.lower(), (
        "the unsupported case is neither raised nor represented in the result — "
        "the only trace is a log line the caller cannot see"
    )
