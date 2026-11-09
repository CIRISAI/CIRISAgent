"""The SQL adapter's GDPR deletion proof carries both signature halves (100% PQC)."""

import base64

import pytest
from sqlalchemy import create_engine, text

from ciris_adapters.external_data_sql.dialects import get_dialect
from ciris_adapters.external_data_sql.schemas import (
    PrivacyColumnMapping,
    PrivacySchemaConfig,
    PrivacyTableMapping,
    SQLConnectorConfig,
    SQLDialect,
)
from ciris_adapters.external_data_sql.service import SQLToolService


class _Signer:
    def __init__(self, pqc: bool = True) -> None:
        self.pqc = pqc

    def local_derived_key_id(self) -> str:
        return "node-key-1"

    def local_sign_hybrid(self, data: bytes) -> dict:
        return {"classical_sig": b"C" * 64, "pqc_sig": (b"P" * 32) if self.pqc else None}


def _service(tmp_path, signer: _Signer) -> SQLToolService:
    config = SQLConnectorConfig(
        connector_id="t",
        connection_string=f"sqlite:///{tmp_path / 'db.sqlite'}",
        dialect=SQLDialect.SQLITE,
        privacy_schema=PrivacySchemaConfig(
            tables=[
                PrivacyTableMapping(
                    table_name="users",
                    identifier_column="user_id",
                    columns=[PrivacyColumnMapping(column_name="email", data_type="email", is_identifier=True)],
                )
            ],
            global_identifier_column="user_id",
        ),
    )
    svc = SQLToolService(config=config)
    svc._engine = create_engine(config.connection_string)
    with svc._engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (user_id TEXT, email TEXT)"))
    svc._dialect = get_dialect("sqlite")
    svc._signer = signer
    return svc


@pytest.mark.asyncio
async def test_the_deletion_proof_is_hybrid(tmp_path) -> None:
    result = await _service(tmp_path, _Signer())._verify_deletion({"user_identifier": "gone"}, "c1")
    proof = result.data["cryptographic_proof"]
    algo, key_id, classical, pqc = proof.split(":")
    assert (algo, key_id) == ("ed25519+ml-dsa-65", "node-key-1")
    assert base64.b64decode(classical) == b"C" * 64 and base64.b64decode(pqc) == b"P" * 32


@pytest.mark.asyncio
async def test_no_proof_without_the_pqc_half(tmp_path) -> None:
    result = await _service(tmp_path, _Signer(pqc=False))._verify_deletion({"user_identifier": "gone"}, "c1")
    assert result.data["cryptographic_proof"] is None
