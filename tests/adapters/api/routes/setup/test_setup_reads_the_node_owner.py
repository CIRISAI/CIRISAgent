"""Setup reads the node-claimed owner; it never mints a user.

The node creates the user when it is claimed (CIRISServer#9 auth, #19 ROOT
bootstrap, #37 upgrade-owner). The wizard claims first, then posts
/v1/setup/complete. The agent used to mint its own ROOT cert there, then link
OAuth to it, set a password on it, retire the substrate's provisional cert and
repair the duplicate holders its own mint produced. Each step answered a bug
the previous one caused (the "2 active certificates answer to the name"
409 lockout, the "AMBIGUOUS provider identity / holders=2" OAuth lockout). All
of it is deleted; `_resolve_node_owner` is the one user source.

`list_was()` cannot see a node-claimed owner (`_is_brain_wa_row`, #922), so the
resolver reads owner rows by role from the store, as the wizard gate does.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from ciris_engine.logic.adapters.api.routes.setup import complete as C

#: The exact shape the node self-claim leaves behind, from the live device.
NODE_OWNER: Dict[str, Any] = {
    "wa_id": "wa-root-qa-node-1786857172-as6ffyvux6",
    "name": "qaadmin",
    "role": "root",
    "active": 1,
}
#: A classic brain cert: not the node-claimed owner.
BRAIN_CERT: Dict[str, Any] = {
    "wa_id": "wa-2026-08-16-143618",
    "name": "qaadmin",
    "role": "root",
    "active": 1,
}


class _Setup:
    def __init__(self, username: str, oauth: bool = False) -> None:
        self.admin_username = username
        self.oauth_provider: Optional[str] = "google" if oauth else None
        self.oauth_external_id: Optional[str] = "12345" if oauth else None


def _patch_store(
    monkeypatch: pytest.MonkeyPatch,
    rows: List[Dict[str, Any]],
    oauth_holders: Optional[List[str]] = None,
    boom: bool = False,
) -> None:
    import ciris_engine.logic.persistence.stores.authentication_store as store

    def fake(role: str, limit: int = 1000) -> List[Dict[str, Any]]:
        if boom:
            raise RuntimeError("persist engine not wired")
        return [r for r in rows if str(r.get("role")) == role]

    monkeypatch.setattr(store, "_list_active_by_role", fake, raising=True)
    monkeypatch.setattr(store, "live_oauth_holders", lambda p, s: list(oauth_holders or []), raising=True)


def test_the_owner_row_answering_to_the_username(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_store(monkeypatch, [NODE_OWNER, {**NODE_OWNER, "wa_id": "wa-root-other", "name": "other"}])
    owner = C._resolve_node_owner(_Setup("qaadmin"))
    assert owner is not None and owner.wa_id == NODE_OWNER["wa_id"]


@pytest.mark.parametrize("typed", ["QAADMIN", "QaAdmin", "  qaadmin  "])
def test_name_match_is_case_and_space_insensitive(monkeypatch: pytest.MonkeyPatch, typed: str) -> None:
    _patch_store(monkeypatch, [NODE_OWNER, {**NODE_OWNER, "wa_id": "wa-root-other", "name": "other"}])
    owner = C._resolve_node_owner(_Setup(typed))
    assert owner is not None and owner.wa_id == NODE_OWNER["wa_id"]


def test_the_oauth_binding_wins_over_the_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """The substrate bound this provider identity at claim; that is the most precise answer."""
    bound = {**NODE_OWNER, "wa_id": "wa-root-bound", "name": "someone"}
    _patch_store(monkeypatch, [NODE_OWNER, bound], oauth_holders=["wa-root-bound"])
    owner = C._resolve_node_owner(_Setup("qaadmin", oauth=True))
    assert owner is not None and owner.wa_id == "wa-root-bound"


def test_a_brain_or_placeholder_oauth_holder_is_not_the_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_store(
        monkeypatch,
        [NODE_OWNER],
        oauth_holders=["wa-2026-08-16-143618", "oauth-google-12345"],
    )
    owner = C._resolve_node_owner(_Setup("qaadmin", oauth=True))
    assert owner is not None and owner.wa_id == NODE_OWNER["wa_id"]


def test_the_single_owner_when_the_name_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    """A node has one owner; the wizard's username field does not change who it is."""
    _patch_store(monkeypatch, [NODE_OWNER])
    owner = C._resolve_node_owner(_Setup("typed-something-else"))
    assert owner is not None and owner.wa_id == NODE_OWNER["wa_id"]


def test_two_owners_and_no_match_is_no_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guessing between two owners would key the user's consent to the wrong human."""
    _patch_store(monkeypatch, [NODE_OWNER, {**NODE_OWNER, "wa_id": "wa-root-other", "name": "other"}])
    assert C._resolve_node_owner(_Setup("nobody")) is None


def test_a_brain_cert_is_never_the_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_store(monkeypatch, [BRAIN_CERT])
    assert C._resolve_node_owner(_Setup("qaadmin")) is None


def test_no_owner_rows_is_no_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_store(monkeypatch, [])
    assert C._resolve_node_owner(_Setup("qaadmin")) is None


def test_a_failed_read_names_no_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail closed: an unreadable store is refused (409), never minted around."""
    _patch_store(monkeypatch, [NODE_OWNER], boom=True)
    assert C._resolve_node_owner(_Setup("qaadmin")) is None


def test_the_mint_paths_are_gone() -> None:
    """The agent mints no user at setup: these helpers must not come back."""
    for gone in (
        "_create_new_wa",
        "_check_existing_oauth_wa",
        "_link_oauth_identity_to_wa",
        "_set_password_for_wa",
        "_enforce_single_holder",
    ):
        assert not hasattr(C, gone), gone


def test_the_owner_carries_no_credential_field() -> None:
    owner = C._NodeOwner(wa_id="wa-root-x", name="n", role="root")
    assert set(C._NodeOwner.__slots__) == {"wa_id", "name", "role"}
    for forbidden in ("password_hash", "api_key_hash", "password"):
        assert not hasattr(owner, forbidden)


def test_the_owner_is_deliberately_not_a_wacertificate() -> None:
    """It cannot be one: the schema pins wa_id to the classic pattern."""
    from ciris_engine.schemas.services.authority_core import WACertificate

    assert not isinstance(C._NodeOwner(wa_id="wa-root-x", name="n", role="root"), WACertificate)
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
