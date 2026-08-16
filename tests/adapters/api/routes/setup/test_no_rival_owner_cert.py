"""Setup must not mint a second ROOT cert with the node owner's name.

THE BUG, found by driving the real Android UI (local login, first boot).

Setup does the node self-claim FIRST — the saga logs it as

    E5 claim_accepted role=SYSTEM_ADMIN waId=wa-root-qa-node-…  (session=setup)

so by the time `completeSetup` runs, the owner the user asked for exists. But
`_create_new_wa`'s duplicate check goes through `list_was()`, which ends in
`if _is_brain_wa_row(row)` (#922) and therefore cannot see `wa-root-*`. The
brain concludes nobody exists and mints a SECOND ROOT certificate under the
same name.

Nothing raises. Setup reports `success=true`. The agent comes up
`status=healthy state=work init=True`. And every login returns 409:

    2 active certificates answer to the name "qaadmin"
    (wa-2026-08-16-143618, wa-root-qa-node-1786857172-as6ffyvux6)
    — refusing to choose between them.

The node is right to refuse: only one of the two carries the password, so
picking either would authenticate as whichever row sorted first. The ambiguity
has to not be created.

This is the FOURTH site blinded by that one correct filter — after the
setup-wizard lockout and the missing founding partnership, both fixed in 2.9.16
by consulting `_list_active_by_role` alongside `list_was()`. It is the worst of
the four: the others degraded a feature, this one locks the user out of a
healthy agent on first boot, with no way back short of wiping app data.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from ciris_engine.logic.adapters.api.routes.setup import complete as C

#: The exact shape the node self-claim leaves behind, from the live device.
NODE_OWNER: Dict[str, Any] = {
    "wa_id": "wa-root-qa-node-1786857172-as6ffyvux6",
    "name": "qaadmin",
    "role": "root",
    "active": 1,
}
#: A classic brain cert — visible to list_was(), NOT our concern here.
BRAIN_CERT: Dict[str, Any] = {
    "wa_id": "wa-2026-08-16-143618",
    "name": "qaadmin",
    "role": "root",
    "active": 1,
}


class _Setup:
    def __init__(self, username: str) -> None:
        self.admin_username = username
        self.oauth_provider = None
        self.oauth_external_id = None
        self.oauth_email = None
        self.admin_password = "irrelevant"


def _patch_rows(monkeypatch: pytest.MonkeyPatch, rows: List[Dict[str, Any]], boom: bool = False) -> None:
    import ciris_engine.logic.persistence.stores.authentication_store as store

    def fake(role: str, limit: int = 1000) -> List[Dict[str, Any]]:
        if boom:
            raise RuntimeError("persist engine not wired")
        return [r for r in rows if str(r.get("role")) == role]

    monkeypatch.setattr(store, "_list_active_by_role", fake, raising=True)


class _Auth:
    """Mirrors the real service: list_was() NEVER returns wa-root-* rows."""

    def __init__(self) -> None:
        self.created: List[str] = []

    async def list_was(self, active_only: bool = True) -> List[Any]:
        return []

    async def create_wa(self, name: str, email: str, scopes: List[str], role: Any) -> Any:
        self.created.append(name)

        class _Cert:
            wa_id = "wa-2026-08-16-999999"

        return _Cert()


@pytest.mark.asyncio
async def test_adopts_the_node_owner_instead_of_minting_a_rival(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE FIX: the owner already exists, so no second cert is created."""
    _patch_rows(monkeypatch, [NODE_OWNER])
    auth = _Auth()

    result = await C._create_new_wa(auth, _Setup("qaadmin"))

    assert auth.created == [], "minting here is what produces the 409 lockout"
    assert result.wa_id == NODE_OWNER["wa_id"]


@pytest.mark.asyncio
async def test_still_mints_when_there_is_no_node_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """The classic path must not regress — a fresh install has no wa-root-*."""
    _patch_rows(monkeypatch, [])
    auth = _Auth()

    result = await C._create_new_wa(auth, _Setup("qaadmin"))

    assert auth.created == ["qaadmin"]
    assert result.wa_id == "wa-2026-08-16-999999"


@pytest.mark.asyncio
async def test_a_different_username_is_not_adopted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a NAME COLLISION causes the 409, so only a collision may adopt."""
    _patch_rows(monkeypatch, [NODE_OWNER])
    auth = _Auth()

    result = await C._create_new_wa(auth, _Setup("someone-else"))

    assert auth.created == ["someone-else"]
    assert result.wa_id == "wa-2026-08-16-999999"


@pytest.mark.parametrize("typed", ["QAADMIN", "QaAdmin", "  qaadmin  "])
@pytest.mark.asyncio
async def test_name_match_is_case_and_space_insensitive(monkeypatch: pytest.MonkeyPatch, typed: str) -> None:
    """The node's collision check is on the stored name, not on our casing.

    A wizard field that round-trips "QAAdmin" must not sneak a rival past this
    guard and reintroduce the lockout through the back door.
    """
    _patch_rows(monkeypatch, [NODE_OWNER])
    auth = _Auth()

    result = await C._create_new_wa(auth, _Setup(typed))

    assert auth.created == []
    assert result.wa_id == NODE_OWNER["wa_id"]


@pytest.mark.asyncio
async def test_a_brain_cert_of_the_same_name_is_not_adopted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brain certs are visible to list_was(); this guard is only for the invisible ones.

    Adopting one here would silently change which identity the classic path
    returns, which is a different behaviour change than the one being fixed.
    """
    _patch_rows(monkeypatch, [BRAIN_CERT])
    auth = _Auth()

    result = await C._create_new_wa(auth, _Setup("qaadmin"))

    assert auth.created == ["qaadmin"]


@pytest.mark.asyncio
async def test_a_failed_probe_does_not_assert_absence(monkeypatch: pytest.MonkeyPatch) -> None:
    """A read error must not be read as 'no owner exists'.

    Minting on a failed probe is precisely how the lockout gets created, so the
    unreadable case falls through to the normal path rather than claiming the
    owner is missing — the same direction as the 2.9.15 setup fix.
    """
    _patch_rows(monkeypatch, [NODE_OWNER], boom=True)
    auth = _Auth()

    result = await C._create_new_wa(auth, _Setup("qaadmin"))

    assert result is not None
    assert auth.created == ["qaadmin"]


@pytest.mark.asyncio
async def test_no_password_is_written_for_a_node_claimed_owner() -> None:
    """THE ARCHITECTURAL HALF: the server owns auth, so the brain must not set one.

    Removing the duplicate cert alone would fix the 409 while leaving the agent
    an authority on a credential it does not own — and two places to rotate it.
    The setup saga already proves the node did this: `E6 owner_login ok` fires
    BEFORE `/v1/setup/complete` runs at all.
    """
    calls: List[Dict[str, Any]] = []

    class _Auth2:
        def hash_password(self, pw: str) -> str:
            return "hashed"

        async def update_wa(self, **kw: Any) -> None:
            calls.append(kw)

    owner = C._AdoptedNodeOwner(wa_id=NODE_OWNER["wa_id"], name="qaadmin", role="root")
    setup = _Setup("qaadmin")

    await C._set_password_for_wa(_Auth2(), setup, owner)

    assert calls == [], "the brain must not write a credential it does not own"


@pytest.mark.asyncio
async def test_a_brain_owned_cert_still_gets_its_password() -> None:
    """The classic path is unchanged — a brain cert is the brain's to credential."""
    calls: List[Dict[str, Any]] = []

    class _Auth2:
        def hash_password(self, pw: str) -> str:
            return "hashed"

        async def update_wa(self, **kw: Any) -> None:
            calls.append(kw)

    class _Cert:
        wa_id = "wa-2026-08-16-143618"

    await C._set_password_for_wa(_Auth2(), _Setup("qaadmin"), _Cert())

    assert len(calls) == 1
    assert calls[0]["wa_id"] == "wa-2026-08-16-143618"
    assert calls[0]["password_hash"] == "hashed"


def test_the_adopted_owner_carries_no_credential_field() -> None:
    """Structural guard: nothing can hang a secret off this carrier by accident."""
    owner = C._AdoptedNodeOwner(wa_id="wa-root-x", name="n", role="root")
    assert set(C._AdoptedNodeOwner.__slots__) == {"wa_id", "name", "role"}
    for forbidden in ("password_hash", "api_key_hash", "password"):
        assert not hasattr(owner, forbidden)


def test_adopted_owner_carries_what_the_flow_reads() -> None:
    """Downstream reads `.wa_id` for password, partnership, prefs and admin update."""
    owner = C._AdoptedNodeOwner(wa_id="wa-root-x", name="n", role="root")
    assert owner.wa_id == "wa-root-x"
    assert (owner.name, owner.role) == ("n", "root")


def test_adopted_owner_is_deliberately_not_a_wacertificate() -> None:
    """It cannot be one: the schema pins wa_id to the classic pattern.

    Pinning this so nobody 'tidies' the carrier into a WACertificate and gets a
    validation error at the worst possible moment — mid-setup, on first boot.
    """
    from ciris_engine.schemas.services.authority_core import WACertificate

    assert not isinstance(C._AdoptedNodeOwner(wa_id="wa-root-x", name="n", role="root"), WACertificate)
    with pytest.raises(Exception):
        WACertificate(
            wa_id="wa-root-qa-node-1786857172-as6ffyvux6",
            name="qaadmin",
            role="root",
            pubkey="x",
            jwt_kid="x",
            scopes_json="[]",
            created_at="2026-08-16T00:00:00Z",
        )
