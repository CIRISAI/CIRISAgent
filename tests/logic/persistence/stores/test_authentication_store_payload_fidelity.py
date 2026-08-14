"""Storage-fidelity contract for the shared WA-certificate write path.

Two latent bugs lived in `_wa_to_persist_payload` since the 2.9.0 persist
migration (and, for the second, since the raw-SQL era before it). Both were
invisible from the agent's own read path, which is why they survived:

  1. `scopes` was stored DOUBLE-JSON-ENCODED. `WACertificate.scopes_json` is
     already a JSON string; persist types its `scopes` column as a free-form
     JSON value and stores what it is given verbatim, so the column ended up
     holding `"[\\"read:any\\"]"` — a JSON string containing a JSON array. The
     agent round-tripped it fine (string in, string out), but every direct
     consumer of `cirislens_wa_cert` sees a string where the schema promises
     a list. Verified against the live DB: 100% of rows in every
     persist-backed database on the build host carry the string shape.

  2. `token_type` could never be written. The passthrough branch read
     `wa_dict.get("token_type")`, but `WACertificate` has no such field and is
     `extra="forbid"`, so the branch was unreachable and every cert landed on
     persist's `'standard'` default.

The fixes must not break rows written by the OLD code — every existing agent
has them — so the read path deliberately accepts both shapes, permanently.

`FakePersistEngine` below mirrors the real substrate's observed behavior
(ciris-server 0.5.171 / persist wa_cert v1.5.19): `scopes` is stored verbatim
as whatever JSON value it receives, and `token_type` is a closed Rust enum
that raises on an unknown variant. Both behaviors were confirmed against a
real `Engine` before being encoded here.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from ciris_engine.logic.persistence.stores import authentication_store as store
from ciris_engine.schemas.services.authority_core import TokenType, WACertificate

OWNER_ID = "wa-2026-08-14-078CA6"
LEGACY_ID = "wa-2026-08-14-2F77D1"

# A real PBKDF2-shaped hash. If a fix mangles this, the owner cannot log in.
REAL_HASH = "cGFzc3dvcmQtaGFzaC1ieXRlcy1tdXN0LXN1cnZpdmU"

SCOPES_JSON = '["read:any", "write:any"]'
SCOPES_LIST = ["read:any", "write:any"]

# Persist's CHECK constraint / serde variant set for `token_type`. Note it does
# NOT contain the agent's own `TokenType.CHANNEL`.
PERSIST_TOKEN_TYPES = {"standard", "session", "api_key", "oauth", "service"}


class FakePersistEngine:
    """Stand-in for persist's `wa_cert_*` substrate, faithful where it matters."""

    def __init__(self) -> None:
        self.rows: Dict[str, Dict[str, Any]] = {}
        self.upserts: List[Dict[str, Any]] = []

    # -- writes ----------------------------------------------------------- #
    def wa_cert_upsert(self, cert_json: str) -> None:
        payload = json.loads(cert_json)
        # Persist decodes `token_type` into a Rust enum; an unknown variant is
        # a hard decode error BEFORE anything is written.
        token_type = payload.get("token_type", "standard")
        if token_type not in PERSIST_TOKEN_TYPES:
            raise ValueError(
                f"WaCert decode: unknown variant `{token_type}`, expected one of "
                f"`standard`, `session`, `api_key`, `oauth`, `service`"
            )
        if "scopes" not in payload:
            raise ValueError("WaCert decode: missing field `scopes`")
        self.upserts.append(payload)
        existing = self.rows.get(payload["wa_id"], {})
        merged = {**existing, **payload}
        merged.setdefault("token_type", "standard")
        # `created` is preserved by persist's UPSERT.
        if existing.get("created"):
            merged["created"] = existing["created"]
        self.rows[payload["wa_id"]] = merged

    def wa_cert_set_active(self, wa_id: str, active: bool) -> None:
        self.rows[wa_id]["active"] = active

    def wa_cert_update_last_login(self, wa_id: str, iso: str) -> None:
        self.rows[wa_id]["last_login"] = iso

    # -- reads ------------------------------------------------------------ #
    def wa_cert_get(self, wa_id: str) -> Optional[str]:
        row = self.rows.get(wa_id)
        return json.dumps(row) if row else None

    def wa_cert_get_by_kid(self, jwt_kid: str) -> Optional[str]:
        for row in self.rows.values():
            if row.get("jwt_kid") == jwt_kid:
                return json.dumps(row)
        return None

    def wa_cert_get_by_oauth(self, provider: str, external_id: str) -> Optional[str]:
        return None

    def wa_cert_list_by_role(self, role: str, limit: int = 1000) -> str:
        return json.dumps(
            [r for r in self.rows.values() if r.get("role") == role and r.get("active", True)][:limit]
        )

    # -- assertions helper ------------------------------------------------ #
    def stored(self, wa_id: str, field: str = "scopes") -> Any:
        """The value a DIRECT consumer of the column sees."""
        return self.rows[wa_id][field]


@pytest.fixture
def engine() -> FakePersistEngine:
    return FakePersistEngine()


@pytest.fixture
def wired(engine: FakePersistEngine) -> Any:
    with patch.object(store, "_get_engine", return_value=engine):
        yield engine


def _must(wa: Optional[WACertificate]) -> WACertificate:
    """Narrow the store's Optional return — a None here IS the failure."""
    assert wa is not None, "expected the certificate to be present in the store"
    return wa


def _cert(wa_id: str = OWNER_ID, scopes_json: str = SCOPES_JSON, **kw: Any) -> WACertificate:
    fields: Dict[str, Any] = {
        "wa_id": wa_id,
        "name": "jeff",
        "role": "root",
        "pubkey": "cGtfYWJj",
        "jwt_kid": f"wa-jwt-{wa_id[-6:].lower()}",
        "password_hash": REAL_HASH,
        "scopes_json": scopes_json,
        "created_at": datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc),
    }
    fields.update(kw)
    return WACertificate(**fields)


def _seed_legacy_row(engine: FakePersistEngine, wa_id: str = LEGACY_ID, **kw: Any) -> None:
    """Write a row EXACTLY the way the pre-fix code wrote it: scopes as a string.

    This is not a hypothetical. It is the shape of every `cirislens_wa_cert`
    row that exists in the field today.
    """
    row: Dict[str, Any] = {
        "wa_id": wa_id,
        "name": "legacy-owner",
        "role": "root",
        "pubkey": "cGtfYWJj",
        "jwt_kid": f"wa-jwt-{wa_id[-6:].lower()}",
        "password_hash": REAL_HASH,
        "scopes": SCOPES_JSON,  # <-- the bug shape: a JSON STRING, not a list
        "token_type": "standard",
        "active": True,
        "auto_minted": False,
        "created": "2026-08-14T12:00:00+00:00",
    }
    row.update(kw)
    engine.rows[wa_id] = row


# --------------------------------------------------------------------------- #
# 1. New writes store a JSON ARRAY and round-trip byte-for-byte               #
# --------------------------------------------------------------------------- #


class TestNewWriteRoundTrip:
    def test_scopes_column_is_a_json_array_not_a_string(self, wired: FakePersistEngine) -> None:
        store.store_wa_certificate(_cert())

        stored = wired.stored(OWNER_ID)
        assert isinstance(stored, list), f"scopes must be stored as an array, got {type(stored).__name__}"
        assert stored == SCOPES_LIST

    def test_scopes_json_round_trips_byte_for_byte(self, wired: FakePersistEngine) -> None:
        cert = _cert()
        store.store_wa_certificate(cert)

        back = store.get_wa_by_id(OWNER_ID)
        assert back is not None
        assert back.scopes_json == cert.scopes_json
        assert back.scopes == SCOPES_LIST

    def test_password_hash_survives_the_round_trip(self, wired: FakePersistEngine) -> None:
        """The whole point of the store: an altered hash locks the owner out."""
        store.store_wa_certificate(_cert())

        back = store.get_wa_by_id(OWNER_ID)
        assert back is not None and back.password_hash == REAL_HASH

    def test_round_trip_through_kid_and_list(self, wired: FakePersistEngine) -> None:
        store.store_wa_certificate(_cert())

        assert _must(store.get_wa_by_kid("wa-jwt-078ca6")).scopes == SCOPES_LIST
        assert [wa.scopes for wa in store.list_wa_certificates(active_only=True)] == [SCOPES_LIST]

    def test_empty_scopes_stay_empty(self, wired: FakePersistEngine) -> None:
        store.store_wa_certificate(_cert(scopes_json="[]"))

        assert wired.stored(OWNER_ID) == []
        assert _must(store.get_wa_by_id(OWNER_ID)).scopes == []

    def test_a_write_never_emits_the_old_double_encoded_shape(self, wired: FakePersistEngine) -> None:
        store.store_wa_certificate(_cert())

        payload = wired.upserts[-1]
        assert not isinstance(payload["scopes"], str), (
            "regression: the payload handed to persist is a JSON string again, "
            "which persist re-encodes into a string-containing-an-array column"
        )


# --------------------------------------------------------------------------- #
# 2. Old double-encoded rows keep working — backwards compatibility           #
# --------------------------------------------------------------------------- #


class TestOldDoubleEncodedRowsStillRead:
    def test_legacy_row_reads_correctly_by_id(self, wired: FakePersistEngine) -> None:
        _seed_legacy_row(wired)

        wa = store.get_wa_by_id(LEGACY_ID)
        assert wa is not None
        assert wa.scopes_json == SCOPES_JSON
        assert wa.scopes == SCOPES_LIST
        assert wa.password_hash == REAL_HASH

    def test_legacy_row_reads_correctly_by_kid(self, wired: FakePersistEngine) -> None:
        _seed_legacy_row(wired)

        wa = store.get_wa_by_kid("wa-jwt-2f77d1")
        assert wa is not None and wa.scopes == SCOPES_LIST

    def test_legacy_row_enumerates(self, wired: FakePersistEngine) -> None:
        _seed_legacy_row(wired)

        was = store.list_wa_certificates(active_only=True)
        assert [wa.wa_id for wa in was] == [LEGACY_ID]
        assert was[0].scopes == SCOPES_LIST

    def test_mixed_old_and_new_rows_read_identically(self, wired: FakePersistEngine) -> None:
        """The migration's real state: some rows fixed, some not."""
        _seed_legacy_row(wired)
        store.store_wa_certificate(_cert())

        assert _must(store.get_wa_by_id(LEGACY_ID)).scopes == SCOPES_LIST
        assert _must(store.get_wa_by_id(OWNER_ID)).scopes == SCOPES_LIST
        # ...and they are genuinely stored differently.
        assert isinstance(wired.stored(LEGACY_ID), str)
        assert isinstance(wired.stored(OWNER_ID), list)

    def test_writing_a_legacy_row_heals_its_scopes_column(self, wired: FakePersistEngine) -> None:
        """Read-modify-upsert must not carry the double-encoding forward."""
        _seed_legacy_row(wired)

        store.update_wa_certificate(LEGACY_ID, {"name": "renamed"})

        assert wired.stored(LEGACY_ID) == SCOPES_LIST
        healed = _must(store.get_wa_by_id(LEGACY_ID))
        assert healed.name == "renamed"
        assert healed.scopes == SCOPES_LIST
        assert healed.password_hash == REAL_HASH


# --------------------------------------------------------------------------- #
# 3. The update path must not re-introduce double-encoding                    #
# --------------------------------------------------------------------------- #


class TestUpdatePathScopes:
    def test_scopes_json_update_stores_an_array(self, wired: FakePersistEngine) -> None:
        """Reachable in production: update_wa(updates=WAUpdate(permissions=[...]))."""
        _seed_legacy_row(wired)

        store.update_wa_certificate(LEGACY_ID, {"scopes_json": json.dumps(["read:any", "manage:all"])})

        assert wired.stored(LEGACY_ID) == ["read:any", "manage:all"]
        assert _must(store.get_wa_by_id(LEGACY_ID)).scopes == ["read:any", "manage:all"]

    def test_scopes_update_accepts_a_list(self, wired: FakePersistEngine) -> None:
        _seed_legacy_row(wired)

        store.update_wa_certificate(LEGACY_ID, {"scopes": ["read:any"]})

        assert wired.stored(LEGACY_ID) == ["read:any"]

    def test_scopes_update_to_none_clears_to_empty(self, wired: FakePersistEngine) -> None:
        _seed_legacy_row(wired)

        store.update_wa_certificate(LEGACY_ID, {"scopes_json": None})

        assert wired.stored(LEGACY_ID) == []


# --------------------------------------------------------------------------- #
# 4. token_type — persisted deliberately, never silently                      #
# --------------------------------------------------------------------------- #


class TestTokenType:
    def test_store_pins_the_standard_variant(self, wired: FakePersistEngine) -> None:
        """WACertificate cannot carry token_type, so the write pins it explicitly."""
        store.store_wa_certificate(_cert())

        assert wired.upserts[-1]["token_type"] == "standard"
        assert wired.stored(OWNER_ID, "token_type") == "standard"

    def test_certificate_still_cannot_smuggle_a_token_type(self) -> None:
        """The dead branch is gone; this documents WHY it was dead."""
        assert "token_type" not in WACertificate.model_fields
        with pytest.raises(Exception):
            _cert(token_type="channel")

    def test_allowed_variant_is_preserved_on_update(self, wired: FakePersistEngine) -> None:
        _seed_legacy_row(wired)

        store.update_wa_certificate(LEGACY_ID, {"token_type": "oauth"})

        assert wired.stored(LEGACY_ID, "token_type") == "oauth"

    def test_allowed_variant_survives_an_unrelated_update(self, wired: FakePersistEngine) -> None:
        _seed_legacy_row(wired, token_type="api_key")

        store.update_wa_certificate(LEGACY_ID, {"name": "renamed"})

        assert wired.stored(LEGACY_ID, "token_type") == "api_key"

    def test_channel_is_refused_loudly_not_silently_defaulted(self, wired: FakePersistEngine, caplog: pytest.LogCaptureFixture) -> None:
        """The agent's own TokenType.CHANNEL is outside persist's variant set.

        Passing it straight through would raise `WaCert decode: unknown
        variant` out of the auth store. Map it deliberately AND say so.
        """
        _seed_legacy_row(wired)

        with caplog.at_level("WARNING"):
            store.update_wa_certificate(LEGACY_ID, {"token_type": TokenType.CHANNEL})

        assert wired.stored(LEGACY_ID, "token_type") == "standard"
        # Reported by CLASSIFICATION, not by echoing the value — and that loses
        # nothing here: of the agent's three TokenType members (standard, channel,
        # oauth) only `channel` is absent from persist's set, so it is the ONLY
        # agent variant that can reach this branch. `known agent variant: True`
        # therefore names it as precisely as the literal did, while a
        # caller-supplied value can no longer reach the log at all.
        assert "known agent variant: True" in caplog.text
        assert "not one of" in caplog.text

    def test_unknown_variant_never_reaches_persist(self, wired: FakePersistEngine) -> None:
        """FakePersistEngine raises on an unknown variant, exactly as persist does."""
        _seed_legacy_row(wired)

        store.update_wa_certificate(LEGACY_ID, {"token_type": "nonsense"})  # must not raise

        assert wired.stored(LEGACY_ID, "token_type") == "standard"

    def test_fake_engine_is_a_faithful_oracle(self, engine: FakePersistEngine) -> None:
        """Guard the guard: the fake must reject what persist rejects."""
        with pytest.raises(ValueError, match="unknown variant"):
            engine.wa_cert_upsert(json.dumps({"wa_id": "x", "scopes": [], "token_type": "channel"}))


# --------------------------------------------------------------------------- #
# 5. Coercion helpers — the unit-level contract                               #
# --------------------------------------------------------------------------- #


class TestScopesToPersist:
    def test_json_string_decodes_to_a_list(self) -> None:
        assert store._scopes_to_persist(SCOPES_JSON) == SCOPES_LIST

    def test_list_passes_through(self) -> None:
        assert store._scopes_to_persist(SCOPES_LIST) == SCOPES_LIST

    def test_double_wrapped_string_unwraps_fully(self) -> None:
        """A legacy row read back and re-upserted arrives wrapped twice."""
        assert store._scopes_to_persist(json.dumps(SCOPES_JSON)) == SCOPES_LIST

    def test_none_is_empty(self) -> None:
        assert store._scopes_to_persist(None) == []

    def test_empty_string_is_empty_without_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Absent, not garbled — the pre-fix code coerced this to "[]" too."""
        with caplog.at_level("WARNING"):
            assert store._scopes_to_persist("") == []
        assert caplog.text == ""

    def test_empty_json_array_is_empty(self) -> None:
        assert store._scopes_to_persist("[]") == []

    def test_garbage_fails_closed_with_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Scopes drive authorization — a garbled value must not widen access."""
        with caplog.at_level("WARNING"):
            assert store._scopes_to_persist("not json at all") == []
        assert "did not decode to a list" in caplog.text
        # The warning must describe the SHAPE, never echo the bytes. A value that
        # failed to decode came off a credential row and is the least trustworthy
        # input we hold (py/clear-text-logging-sensitive-data).
        assert "not json at all" not in caplog.text
        assert "type=str" in caplog.text

    def test_non_list_json_fails_closed(self) -> None:
        assert store._scopes_to_persist('{"read": true}') == []

    def test_unwrapping_is_bounded(self) -> None:
        """A pathologically nested value terminates instead of spinning."""
        nested = SCOPES_JSON
        for _ in range(10):
            nested = json.dumps(nested)
        assert store._scopes_to_persist(nested) == []


class TestCoerceScopesJson:
    def test_list_from_a_new_row(self) -> None:
        assert store._coerce_scopes_json(SCOPES_LIST) == SCOPES_JSON

    def test_string_from_an_old_row_is_returned_unchanged(self) -> None:
        assert store._coerce_scopes_json(SCOPES_JSON) == SCOPES_JSON

    def test_old_and_new_rows_yield_identical_scopes_json(self) -> None:
        assert store._coerce_scopes_json(SCOPES_LIST) == store._coerce_scopes_json(SCOPES_JSON)

    def test_none_is_empty_array(self) -> None:
        assert store._coerce_scopes_json(None) == "[]"

    def test_invalid_json_string_does_not_poison_wacertificate(self) -> None:
        """WACertificate validates scopes_json; a non-JSON string would raise
        there and take down every enumeration touching the row."""
        result = store._coerce_scopes_json("}{ not json")
        assert result == "[]"
        json.loads(result)  # must be constructible

    def test_deeper_wrapping_is_unwrapped(self) -> None:
        assert store._coerce_scopes_json(json.dumps(SCOPES_JSON)) == SCOPES_JSON


class TestCoerceTokenType:
    @pytest.mark.parametrize("value", sorted(PERSIST_TOKEN_TYPES))
    def test_allowed_variants_pass_through(self, value: str) -> None:
        assert store._coerce_token_type(value) == value

    def test_none_becomes_standard(self) -> None:
        assert store._coerce_token_type(None) == "standard"

    def test_agent_enum_channel_maps_to_standard(self) -> None:
        assert store._coerce_token_type(TokenType.CHANNEL) == "standard"

    def test_agent_enum_oauth_passes_through(self) -> None:
        assert store._coerce_token_type(TokenType.OAUTH) == "oauth"

    def test_unknown_value_maps_to_standard(self) -> None:
        assert store._coerce_token_type("nonsense") == "standard"

    def test_persist_variant_set_matches_the_substrate_check_constraint(self) -> None:
        """If persist widens or narrows its enum, this is the tripwire."""
        assert store._PERSIST_TOKEN_TYPES == PERSIST_TOKEN_TYPES
