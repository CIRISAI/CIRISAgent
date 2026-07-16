"""Regression tests: the brain's WA enumeration must survive substrate/node-owner rows.

Context (CIRISAgent#922): the local node's self-claim (ciris-server
/v1/setup/claim-remote) mints the node *owner* WA in a fed-ID-rooted shape
(e.g. "wa-root-qa-node-1784174637-kz4dnlfxzi") and writes it to the SHARED
persist wa_cert store — the same table the brain's auth service reads. That
id does not match WACertificate.wa_id's classic pattern
(^wa-\\d{4}-\\d{2}-\\d{2}-[A-Z0-9]{6}$), so materializing it as a WACertificate
raises a pydantic validation error. Before the "claim THEN complete" reorder
the owner row didn't exist yet when the brain read the store; the reorder
exposed the latent incompatibility as an HTTP 500 during /v1/setup/complete.

The store must recognize node-owner rows as a different identity kind and skip
them, so brain WA enumeration (list_was, OAuth fallback, counts) does not choke.
The classic path (no node-owner rows) must be byte-for-byte unchanged.
"""

from unittest.mock import MagicMock, patch

from ciris_engine.logic.persistence.stores import authentication_store as store
from ciris_engine.schemas.services.authority_core import WACertificate

CLASSIC_WA_ID = "wa-2026-07-15-ABC123"
NODE_OWNER_WA_ID = "wa-root-qa-node-1784174637-kz4dnlfxzi"


def _classic_row(wa_id: str = CLASSIC_WA_ID, role: str = "root", name: str = "admin") -> dict:
    """A well-formed classic brain WA row as persist would return it."""
    return {
        "wa_id": wa_id,
        "name": name,
        "role": role,
        "pubkey": "cGtfYWJj",  # base64url-ish placeholder
        "jwt_kid": f"wa-jwt-{wa_id[-6:].lower()}",
        "scopes": '["read:any", "write:any"]',
        "created": "2026-07-15T12:00:00+00:00",
        "active": True,
    }


def _node_owner_row() -> dict:
    """The substrate-minted node-owner row — fed-ID-rooted wa_id, role root."""
    return {
        "wa_id": NODE_OWNER_WA_ID,
        "name": "qa-node",
        "role": "root",
        # A node-owner row need not even carry every field a brain WA requires;
        # it is a federation ownership identity, not a WACertificate. The point
        # is the brain must never try to build a WACertificate from it.
        "created": "2026-07-14T00:00:00+00:00",
        "active": True,
    }


def _engine_returning(rows_by_role: dict) -> MagicMock:
    """Build a mock persist engine whose wa_cert_list_by_role returns per-role rows."""
    engine = MagicMock()

    def _list_by_role(role: str, limit: int = 1000):
        return list(rows_by_role.get(role, []))

    engine.wa_cert_list_by_role.side_effect = _list_by_role
    return engine


class TestListWaCertificatesSkipsNodeOwner:
    def test_node_owner_row_does_not_crash_list(self):
        """list_wa_certificates must return the classic WA and skip the node-owner row."""
        engine = _engine_returning({"root": [_node_owner_row(), _classic_row()]})
        with patch.object(store, "_get_engine", return_value=engine):
            was = store.list_wa_certificates(active_only=False)

        assert [wa.wa_id for wa in was] == [CLASSIC_WA_ID]
        assert all(isinstance(wa, WACertificate) for wa in was)

    def test_classic_only_is_unchanged(self):
        """With no node-owner rows the classic path yields exactly the classic WA(s)."""
        engine = _engine_returning({"root": [_classic_row()]})
        with patch.object(store, "_get_engine", return_value=engine):
            was = store.list_wa_certificates(active_only=True)

        assert len(was) == 1
        assert was[0].wa_id == CLASSIC_WA_ID
        assert was[0].role.value == "root"

    def test_empty_store_returns_empty(self):
        engine = _engine_returning({})
        with patch.object(store, "_get_engine", return_value=engine):
            assert store.list_wa_certificates(active_only=False) == []


class TestGetWaByOauthFallbackSkipsNodeOwner:
    def test_oauth_fallback_scan_survives_node_owner(self):
        """The linked-identity fallback scan must not choke on a node-owner row."""
        engine = _engine_returning({"root": [_node_owner_row(), _classic_row()]})
        # Primary OAuth lookup misses -> fallback scans all active rows.
        engine.wa_cert_get_by_oauth.return_value = None
        with patch.object(store, "_get_engine", return_value=engine):
            result = store.get_wa_by_oauth("google", "does-not-exist")

        # No match, but crucially: no exception raised on the node-owner row.
        assert result is None


class TestGetCertificateCountsExcludesNodeOwner:
    def test_counts_reflect_brain_was_only(self):
        engine = _engine_returning({"root": [_node_owner_row(), _classic_row()]})
        with patch.object(store, "_get_engine", return_value=engine):
            counts = store.get_certificate_counts()

        assert counts["total"] == 1
        assert counts["active"] == 1
        assert counts["by_role"]["root"] == 1


class TestIsBrainWaRow:
    def test_classic_id_is_brain_wa(self):
        assert store._is_brain_wa_row({"wa_id": CLASSIC_WA_ID}) is True

    def test_node_owner_id_is_not_brain_wa(self):
        assert store._is_brain_wa_row({"wa_id": NODE_OWNER_WA_ID}) is False

    def test_missing_or_non_string_id_is_not_brain_wa(self):
        assert store._is_brain_wa_row({}) is False
        assert store._is_brain_wa_row({"wa_id": None}) is False
        assert store._is_brain_wa_row({"wa_id": 12345}) is False

    def test_lowercase_suffix_is_not_classic(self):
        # Pattern requires uppercase/digits in the suffix.
        assert store._is_brain_wa_row({"wa_id": "wa-2026-07-15-abc123"}) is False
