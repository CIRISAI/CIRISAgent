"""Setup mints a second ROOT on an identity the fabric already owns.

FIELD FAILURE (2026-09-01, ciris-agent 2.9.44 / ciris-server 0.5.196). A user
completed a clean first-run Google sign-in and was then locked out of BOTH doors:

    ERROR ciris_server::auth::store: AMBIGUOUS provider identity — multiple live
      certs claim this account. Refusing to choose: picking one silently signs
      the human in with whichever rights that cert happens to carry.
      provider=google holders=2
      wa_ids=["wa-2026-09-01-3F4F60", "wa-root-francesco-alvise-zamagni-7pj6t55int"]
    INFO  oauth sign-in refused (browser page) reason_id="auth.oauth.store_unavailable"

Google fails on the ambiguity; local fails because an OAuth user has no password
("Skipping password hash for OAuth user"). The substrate is RIGHT to refuse —
choosing would silently grant whichever rights the winner carries.

THE FOUR SECONDS THAT MATTER:

    15:11:34  substrate: retired a duplicate cert holding the owner's sign-in pair
                         — the provider identity now resolves to the owner alone
    15:11:38  agent:     No existing WA found for OAuth user - will create new
    15:11:38  agent:     Existing WAs before creation: 0
    15:11:38  agent:     Created NEW WA: wa-2026-09-01-3F4F60

The fabric had already bound the identity to `wa-root-<user>`. Setup looked, saw
nothing, and minted a second claim.

WHY EVERY LOOKUP SAID "NOTHING THERE". All three of the agent's paths reduce the
question to "can I build a WACertificate for this?", and `wa-root-<user>` cannot
be one — it fails `_CLASSIC_WA_ID_RE` by construction:

  * `get_wa_by_oauth`      → materializes; non-classic row → None
  * `fabric_oauth_holder_id` → a POINT lookup (`wa_cert_get_by_oauth`) returns one
                             row for an identity that has two
  * `list_was(active_only=False)` → "unsupported under persist; returning
                             active-only set (CIRISAgent#763)" → reported 0

And `_is_brain_wa_row` filters non-classic rows out of the one path that DOES
enumerate (`wa_cert_list_by_role`) — deliberately, so the brain "does not choke
trying to build a WACertificate it cannot represent". That is correct for
building certificates and wrong for answering "who holds this identity", which
needs no certificate at all.

The 2.9.44 fix (`fabric_oauth_holder_id`) addressed the right question with the
wrong instrument: it asks a single-row API in a situation defined by there being
two rows.
"""

from __future__ import annotations

import json

import pytest

PROVIDER = "google"
SUBJECT = "108898137212622955874"

FABRIC_OWNER = "wa-root-francesco-alvise-zamagni-7pj6t55int"
OUR_MINT = "wa-2026-09-01-3F4F60"
PROVISIONAL = f"oauth-{PROVIDER}-{SUBJECT}"


def _row(wa_id: str, role: str = "root", active: bool = True) -> dict:
    return {
        "wa_id": wa_id,
        "name": "oauth_google_user",
        "role": role,
        "active": active,
        "oauth_provider": PROVIDER,
        "oauth_external_id": SUBJECT,
    }


class _FieldEngine:
    """The store as it stood at 15:11:38, from the substrate's own account.

    Two rows carry the identity — the fabric's owner cert and the provisional the
    substrate had just retired. `wa_cert_get_by_oauth` is a POINT lookup: it can
    only answer with one of them.
    """

    def __init__(self, point_lookup_returns: str | None = PROVISIONAL):
        self._rows = {
            FABRIC_OWNER: _row(FABRIC_OWNER),
            PROVISIONAL: _row(PROVISIONAL, role="observer", active=False),
        }
        self._point = point_lookup_returns

    def wa_cert_get_by_oauth(self, provider, external_id):
        if (provider, external_id) != (PROVIDER, SUBJECT) or self._point is None:
            return None
        return json.dumps(self._rows[self._point])

    def wa_cert_list_by_role(self, role, limit=1000):
        return json.dumps([r for r in self._rows.values() if r["role"] == role and r["active"]])


def test_the_store_can_name_every_live_holder_of_an_identity(monkeypatch) -> None:
    """THE MISSING QUESTION.

    The substrate answers exactly this in its own refusal (`holders=2 wa_ids=[…]`).
    The agent has no way to ask it, so it cannot know it is about to create the
    second holder. Everything else here follows from that.
    """
    from ciris_engine.logic.persistence.stores import authentication_store as store

    monkeypatch.setattr(store, "_get_engine", lambda: _FieldEngine())
    holders = store.live_oauth_holders(PROVIDER, SUBJECT)  # type: ignore[attr-defined]

    assert set(holders) == {FABRIC_OWNER}, (
        "the live holder set must include substrate-owned rows; they are the ones "
        "that caused the lockout"
    )


def test_the_fabric_holder_is_found_even_when_a_retired_provisional_shadows_it(monkeypatch) -> None:
    """The exact field condition: provisional retired, owner live, point lookup ambiguous.

    Whichever row `wa_cert_get_by_oauth` happens to return, the answer to "is this
    identity already spoken for?" must be YES.
    """
    from ciris_engine.logic.persistence.stores import authentication_store as store

    monkeypatch.setattr(store, "_get_engine", lambda: _FieldEngine(point_lookup_returns=PROVISIONAL))
    assert store.fabric_oauth_holder_id(PROVIDER, SUBJECT) == FABRIC_OWNER


def test_the_fabric_holder_is_found_when_the_point_lookup_is_empty(monkeypatch) -> None:
    from ciris_engine.logic.persistence.stores import authentication_store as store

    monkeypatch.setattr(store, "_get_engine", lambda: _FieldEngine(point_lookup_returns=None))
    assert store.fabric_oauth_holder_id(PROVIDER, SUBJECT) == FABRIC_OWNER


def test_the_answer_no_longer_depends_on_which_row_the_point_lookup_returns(monkeypatch) -> None:
    """THE INVARIANT THAT WAS MISSING.

    Before the fix this same two-holder store gave three different answers
    depending on which row `wa_cert_get_by_oauth` happened to hand back — and one
    of them was None, which is what let setup mint the second claim. Ownership is
    a property of the store, not of which row an accessor picks, so the answer
    must be identical however the point lookup behaves.
    """
    from ciris_engine.logic.persistence.stores import authentication_store as store

    answers = set()
    for returns in (FABRIC_OWNER, PROVISIONAL, None):
        monkeypatch.setattr(store, "_get_engine", lambda r=returns: _FieldEngine(point_lookup_returns=r))
        answers.add(store.fabric_oauth_holder_id(PROVIDER, SUBJECT))

    assert answers == {FABRIC_OWNER}, f"still point-lookup dependent: {answers}"


def test_a_retired_row_is_not_a_holder(monkeypatch) -> None:
    """The provisional is retired on purpose; counting it would fail healthy installs.

    The substrate retires it at claim-remote ("the provider identity now resolves
    to the owner alone"), so a holder set that included dead rows would report
    ambiguity on every correct first run.
    """
    from ciris_engine.logic.persistence.stores import authentication_store as store

    monkeypatch.setattr(store, "_get_engine", lambda: _FieldEngine())
    assert PROVISIONAL not in store.live_oauth_holders(PROVIDER, SUBJECT)


def test_our_own_mint_is_a_holder_too(monkeypatch) -> None:
    """The set is for counting, not for judging whose cert it is.

    `fabric_oauth_holder_id` filters to the FABRIC's holder, but the underlying
    enumeration must report every live claim — that is what makes it usable as
    the one-holder invariant check.
    """
    import json

    from ciris_engine.logic.persistence.stores import authentication_store as store

    class _Both(_FieldEngine):
        def wa_cert_list_by_role(self, role, limit=1000):
            rows = [_row(FABRIC_OWNER), _row(OUR_MINT)]
            return json.dumps([r for r in rows if r["role"] == role])

    monkeypatch.setattr(store, "_get_engine", lambda: _Both())
    assert store.live_oauth_holders(PROVIDER, SUBJECT) == sorted([FABRIC_OWNER, OUR_MINT])
