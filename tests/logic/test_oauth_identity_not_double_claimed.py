"""Setup must not mint a second ROOT for an identity the fabric already bound.

THE FAILURE THIS PINS, observed on a fresh install (2026-08-31):

    16:02:46  Google sign-in parks provisional cert oauth-google-1153…
    16:02:54  claim-remote (substrate) retires it and binds google:1153… to the
              owner it mints: wa-root-mooreericnyc-7hhypjexoo
    16:02:54  _create_setup_users: "No existing WA found for OAuth user"
              "Existing WAs before creation: 0"   ← the owner cert was right there
              mints wa-2026-08-31-227732 (ROOT) and links google:1153… to it
    16:03:06  every later sign-in:
              AMBIGUOUS provider identity — multiple live certs claim this account
              holders=2 wa_ids=["wa-2026-08-31-227732", "wa-root-mooreericnyc-…"]

Google then failed on the ambiguity, and local failed because an OAuth user has
no password ("Skipping password hash for OAuth user"). A closed door on both
sides of a fresh install.

WHY IT WAS INVISIBLE. `get_wa_by_oauth` returns a `WACertificate`, whose `wa_id`
carries a hard pattern of OUR minting convention. `wa-root-<user>` cannot be
constructed as one at all, so the lookup answered None for an identity that was
very much taken. A shape check standing in for a semantic one: "I cannot
represent this" was read as "this does not exist".

The substrate's refusal is CORRECT and is not the bug — it is fail-closed on an
ambiguity the agent created. Ownership is the fabric's to produce and ours to
surface.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.persistence.stores import authentication_store as store

PROVIDER = "google"
SUBJECT = "115300315355793131383"

# The three id shapes this identity passes through, verbatim from the incident.
PLACEHOLDER = f"oauth-{PROVIDER}-{SUBJECT}"
FABRIC_OWNER = "wa-root-mooreericnyc-7hhypjexoo"
OUR_MINT = "wa-2026-08-31-227732"


@pytest.mark.parametrize(
    ("wa_id", "expected", "why"),
    [
        (FABRIC_OWNER, FABRIC_OWNER, "substrate-minted owner — the identity IS taken"),
        (OUR_MINT, None, "our own mint — the normal path already returns it"),
        (PLACEHOLDER, None, "provisional hand-off — retired after we mint+link"),
    ],
)
def test_fabric_holder_is_recognised(monkeypatch, wa_id, expected, why) -> None:
    """The detector must tell the fabric's cert from ours and from the placeholder."""
    monkeypatch.setattr(store, "_get_engine", lambda: _FakeEngine(wa_id))
    assert store.fabric_oauth_holder_id(PROVIDER, SUBJECT) == expected, why


def test_an_inactive_holder_does_not_count(monkeypatch) -> None:
    """A retired cert is not a claimant.

    The placeholder is retired by claim-remote before setup runs; treating a dead
    row as a live holder would block minting on a genuinely free identity.
    """
    monkeypatch.setattr(store, "_get_engine", lambda: _FakeEngine(FABRIC_OWNER, active=False))
    assert store.fabric_oauth_holder_id(PROVIDER, SUBJECT) is None


def test_no_holder_at_all(monkeypatch) -> None:
    monkeypatch.setattr(store, "_get_engine", lambda: _FakeEngine(None))
    assert store.fabric_oauth_holder_id(PROVIDER, SUBJECT) is None


def test_the_fabric_owner_cannot_be_materialised_which_is_the_whole_point() -> None:
    """Why a shape check could not answer this.

    If `wa-root-…` were constructible as a WACertificate, `get_wa_by_oauth` would
    have returned it and setup would never have minted. It is not — so the
    detector has to answer WITHOUT materializing, which is exactly what it does.
    """
    from pydantic import ValidationError

    from ciris_engine.schemas.services.authority_core import WACertificate

    with pytest.raises(ValidationError):
        WACertificate(
            wa_id=FABRIC_OWNER,
            name="owner",
            role="root",
            pubkey="x",
            jwt_kid="k",
            scopes_json="[]",
            created_at="2026-08-31T00:00:00Z",
        )


class _FakeEngine:
    """Minimal stand-in for the persist engine's OAuth lookup."""

    def __init__(self, wa_id, active: bool = True):
        self._wa_id = wa_id
        self._active = active

    def wa_cert_get_by_oauth(self, provider, external_id):
        if self._wa_id is None:
            return None
        return {"wa_id": self._wa_id, "active": self._active}
