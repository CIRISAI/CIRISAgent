"""Emergency shutdown, signed by the seated Wise Authority (Eric, 2026-11-08).

No session is needed: the signature is the authentication. The command must
carry a valid hybrid signature (Ed25519 + ML-DSA-65, verified strict) from the
node's seated Wise Authority, which today is the node's owner. The signer's key
is resolved from the federation directory, and a record without its ML-DSA-65
half is refused.

Accord holders (A1, B1, C1) are refused here even with a valid signature:
their emergency act is the HUMANITY_ACCORD halt (POST /v1/accord/halt and its
cosign), not this route.
"""

import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request

from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.services.shutdown import EmergencyCommandType, EmergencyShutdownStatus, WASignedCommand

from ..constants import ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE

logger = logging.getLogger(__name__)

router = APIRouter(tags=["emergency"])

#: Accord-holder keys: they act through the accord halt, never this route.
ACCORD_HOLDER_KEY_IDS = frozenset({"A1", "B1", "C1"})
_ACCORD_HOLDER_IDENTITY = "accord_holder"

COMMAND_WINDOW = timedelta(minutes=5)
CLOCK_SKEW = timedelta(minutes=1)


class EmergencyRefused(Exception):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status, self.reason = status, reason


def canonical_command_bytes(command: WASignedCommand) -> bytes:
    """The bytes both halves cover: JCS over every field but the signatures."""
    from ciris_adapters.ciris_verify.ffi_bindings import jcs_canonicalize  # substrate-provided canonicalizer

    body = command.model_dump(mode="json", exclude={"signature", "signature_pqc"})
    canonical: bytes = jcs_canonicalize(body)
    return canonical


def _check_window(command: WASignedCommand, now: datetime) -> None:
    issued = command.issued_at if command.issued_at.tzinfo else command.issued_at.replace(tzinfo=timezone.utc)
    if now - issued > COMMAND_WINDOW:
        raise EmergencyRefused(403, "Command is older than the 5-minute window")
    if issued > now + CLOCK_SKEW:
        raise EmergencyRefused(403, "Command is issued in the future")
    if command.expires_at is not None:
        expires = command.expires_at if command.expires_at.tzinfo else command.expires_at.replace(tzinfo=timezone.utc)
        if now > expires:
            raise EmergencyRefused(403, "Command has expired")


def _signer_record(engine: Any, key_id: str) -> Tuple[str, str, Optional[str]]:
    raw = engine.lookup_public_key(key_id)
    record = json.loads(raw) if raw else None
    if not isinstance(record, dict):
        raise EmergencyRefused(403, "Signer is not in the federation directory")
    ed, pqc = record.get("pubkey_ed25519_base64"), record.get("pubkey_ml_dsa_65_base64")
    if not (isinstance(ed, str) and ed and isinstance(pqc, str) and pqc):
        raise EmergencyRefused(403, "Signer's key record has no ML-DSA-65 half")
    identity_type = record.get("identity_type")
    return ed, pqc, identity_type if isinstance(identity_type, str) else None


def _seated_wa(engine: Any) -> Optional[str]:
    """The node's seated Wise Authority: its owner (Eric, 2026-10-22)."""
    from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService

    return AuthenticationService._owner_key_id(engine, str(engine.local_derived_key_id()))


def verify_command(engine: Any, command: WASignedCommand, now: Optional[datetime] = None) -> None:
    """Raise EmergencyRefused unless the command is in date, from the seated WA, and verifies hybrid."""
    from ciris_engine.logic.utils import substrate_signing

    if command.command_type != EmergencyCommandType.SHUTDOWN_NOW:
        raise EmergencyRefused(400, f"Invalid command type: {command.command_type}")
    _check_window(command, now or datetime.now(timezone.utc))
    if command.signer_key_id in ACCORD_HOLDER_KEY_IDS:
        raise EmergencyRefused(403, "Accord holders act through the accord halt (POST /v1/accord/halt), not this route")
    ed_pub, pqc_pub, identity_type = _signer_record(engine, command.signer_key_id)
    if identity_type == _ACCORD_HOLDER_IDENTITY:
        raise EmergencyRefused(403, "Accord holders act through the accord halt (POST /v1/accord/halt), not this route")
    try:
        substrate_signing.verify_hybrid_required(
            engine, canonical_command_bytes(command), command.signature, command.signature_pqc, ed_pub, pqc_pub
        )
    except Exception as exc:
        logger.warning("[EMERGENCY] signature refused: %s", type(exc).__name__)
        raise EmergencyRefused(403, "Invalid signature") from exc
    seated = _seated_wa(engine)
    if seated is None or command.signer_key_id != seated:
        raise EmergencyRefused(403, "Signer is not this node's seated Wise Authority")


@router.post(
    "/emergency/shutdown",
    responses={
        400: {"description": "Invalid command type"},
        403: {"description": "Window, signature, or seat check failed"},
        500: {"description": "Emergency shutdown execution failed"},
        503: {"description": "Engine, runtime, or shutdown service not available"},
    },
)
async def emergency_shutdown(command: WASignedCommand, request: Request) -> SuccessResponse[EmergencyShutdownStatus]:
    """Shut the agent down now, on a hybrid-signed command from the seated Wise Authority."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    logger.critical("Emergency shutdown requested, signer %s", command.signer_key_id)
    status = EmergencyShutdownStatus(command_received=datetime.now(timezone.utc), command_verified=False)
    engine = get_persist_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Cannot verify: the persist engine is not running")
    try:
        verify_command(engine, command)
    except EmergencyRefused as refused:
        logger.error("[EMERGENCY] refused: %s", refused.reason)
        raise HTTPException(status_code=refused.status, detail=refused.reason)
    status.command_verified = True

    runtime = getattr(request.app.state, "runtime", None)
    shutdown_service = getattr(runtime, "shutdown_service", None) if runtime else None
    if shutdown_service is None:
        raise HTTPException(status_code=503, detail=ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE)
    try:
        status.shutdown_initiated = datetime.now(timezone.utc)
        await shutdown_service.emergency_shutdown(f"EMERGENCY: {command.reason} (WA: {command.signer_key_id})")
        status.services_stopped = ["shutdown_requested"]
        status.data_persisted = True
        status.final_message_sent = True
        status.shutdown_completed = datetime.now(timezone.utc)
        status.exit_code = 0
        logger.critical("Emergency shutdown initiated")
        return SuccessResponse(data=status)
    except Exception as e:
        logger.error("Emergency shutdown failed: %s", e)
        raise HTTPException(status_code=500, detail="Emergency shutdown failed")
