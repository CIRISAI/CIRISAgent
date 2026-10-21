"""Deletion verification API endpoints.

Provides public verification of DSAR deletion proofs.

Proofs are signed by the substrate's local Ed25519 signing identity
(ciris-persist ``Engine.local_sign``) over the RFC 8785 (JCS) canonical
bytes of the deletion data, and verified via ``Engine.verify_hybrid``.
The homegrown RSA-PSS signer was deleted in the 2.9.7 DRY purge.
"""

import base64
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log

from ..models import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verification", tags=["Verification"])


class DeletionProof(BaseModel):
    """Cryptographically signed proof of data deletion (Ed25519)."""

    deletion_id: str = Field(..., description="Unique deletion request ID")
    user_identifier: str = Field(..., description="User identifier for deleted data")
    sources_deleted: Dict[str, Any] = Field(..., description="Sources and records deleted")
    deleted_at: str = Field(..., description="ISO 8601 deletion timestamp")
    signature: str = Field(..., description="Ed25519 signature (base64) over JCS canonical deletion data")
    public_key_id: str = Field(..., description="Derived key ID of the local Ed25519 signing identity")


class SignatureVerificationResult(BaseModel):
    """Result of signature verification."""

    valid: bool = Field(..., description="Whether signature is valid")
    deletion_id: str = Field(..., description="Deletion request ID")
    user_identifier: str = Field(..., description="User identifier")
    deleted_at: str = Field(..., description="Deletion timestamp")
    sources_count: int = Field(..., description="Number of sources deleted")
    total_records: int = Field(..., description="Total records deleted")
    message: str = Field(..., description="Verification result message")
    verified_at: str = Field(..., description="When verification occurred")


class VerifyDeletionRequest(BaseModel):
    """Request to verify a deletion proof."""

    deletion_proof: DeletionProof = Field(..., description="Signed deletion proof to verify")


class ManualSignatureVerificationRequest(BaseModel):
    """Request for manual signature verification."""

    deletion_id: str = Field(..., description="Deletion request ID")
    user_identifier: str = Field(..., description="User identifier")
    sources_deleted: Dict[str, Any] = Field(..., description="Sources and records deleted")
    deleted_at: str = Field(..., description="ISO 8601 deletion timestamp")
    signature: str = Field(..., description="Base64-encoded Ed25519 signature")
    public_key_id: str = Field(..., description="Public key ID used for signing")


def _require_engine() -> Any:
    """Return the wired persist Engine or raise 503.

    The substrate owns the signing identity; without a wired engine the
    verification surface cannot operate.
    """
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signing substrate not available",
        )
    return engine


def _canonical_proof_bytes(
    deletion_id: str, user_identifier: str, sources_deleted: Dict[str, Any], deleted_at: str
) -> bytes:
    """RFC 8785 (JCS) canonical bytes of the deletion data (signed payload)."""
    from ciris_adapters.ciris_verify.ffi_bindings import jcs_canonicalize  # substrate-provided canonicalizer

    # jcs_canonicalize is from the untyped substrate wheel (returns Any); annotate
    # the local as bytes so the declared return type is satisfied without a cast.
    canonical_bytes: bytes = jcs_canonicalize(
        {
            "deletion_id": deletion_id,
            "user_identifier": user_identifier,
            "sources_deleted": sources_deleted,
            "deleted_at": deleted_at,
        }
    )
    return canonical_bytes


def sign_deletion_proof(
    deletion_id: str, user_identifier: str, sources_deleted: Dict[str, Any], deleted_at: datetime
) -> DeletionProof:
    """Create a deletion proof signed by the substrate's local Ed25519 identity."""
    engine = _require_engine()
    deleted_at_iso = deleted_at.isoformat()
    canonical = _canonical_proof_bytes(deletion_id, user_identifier, sources_deleted, deleted_at_iso)
    try:
        # sign_classical, not engine.local_sign: the classical key is sealed on
        # any node with one federation identity, and the sync verb refuses it
        # permanently. Same 64 Ed25519 bytes, so DeletionProof's wire shape is
        # unchanged.
        from ciris_engine.logic.utils import substrate_signing

        signature_bytes = substrate_signing.sign_classical(engine, canonical)
        public_key_id = engine.local_derived_key_id()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Local signing identity not configured: {e}",
        )
    logger.info(f"Deletion proof signed: {deletion_id} using key {public_key_id}")
    return DeletionProof(
        deletion_id=deletion_id,
        user_identifier=user_identifier,
        sources_deleted=sources_deleted,
        deleted_at=deleted_at_iso,
        signature=base64.b64encode(signature_bytes).decode("ascii"),
        public_key_id=public_key_id,
    )


def _verify_proof(proof: DeletionProof) -> SignatureVerificationResult:
    """Verify a deletion proof against the substrate's local Ed25519 identity."""
    engine = _require_engine()
    verified_at = datetime.now(timezone.utc).isoformat()

    try:
        public_key_b64 = engine.local_public_key_b64()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Local signing identity not configured: {e}",
        )

    canonical = _canonical_proof_bytes(
        proof.deletion_id, proof.user_identifier, proof.sources_deleted, proof.deleted_at
    )

    try:
        engine.verify_hybrid(canonical, proof.signature, None, public_key_b64, None, "ed25519_fallback")
        valid = True
        message = "Deletion proof verified - signature valid"
    except ValueError as e:
        logger.warning("Signature verification failed for %s: %s", sanitize_for_log(proof.deletion_id), e)
        valid = False
        message = "Invalid signature - deletion proof cannot be verified"

    total_records = 0
    if valid:
        total_records = sum(
            int(source.get("total_records_deleted", 0))
            for source in proof.sources_deleted.values()
            if isinstance(source, dict)
        )

    return SignatureVerificationResult(
        valid=valid,
        deletion_id=proof.deletion_id,
        user_identifier=proof.user_identifier,
        deleted_at=proof.deleted_at,
        sources_count=len(proof.sources_deleted),
        total_records=total_records,
        message=message,
        verified_at=verified_at,
    )


@router.post("/deletion")
async def verify_deletion_proof(
    request: VerifyDeletionRequest,
    req: Request,
) -> StandardResponse:
    """
    Verify cryptographic deletion proof.

    NO AUTHENTICATION REQUIRED - Public verification endpoint.

    Users can verify that their data was actually deleted by checking
    the Ed25519 signature on the deletion proof.

    Returns verification result with signature validity.
    """
    verification_result = _verify_proof(request.deletion_proof)

    logger.info(
        "Deletion verification request: %s - Valid: %s",
        sanitize_for_log(request.deletion_proof.deletion_id),
        verification_result.valid,
    )

    return StandardResponse(
        success=verification_result.valid,
        data=verification_result.model_dump(),
        message=verification_result.message,
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "public_endpoint": True,
        },
    )


@router.get("/public/{deletion_id}", response_class=HTMLResponse)
async def public_verification_page(
    deletion_id: str,
    req: Request,
) -> HTMLResponse:
    """
    Public verification page (HTML).

    NO AUTHENTICATION REQUIRED - Anyone can view.

    Provides a human-readable page showing deletion proof verification.
    """
    import html

    # Sanitize user input to prevent XSS
    safe_deletion_id = html.escape(deletion_id)

    # Build HTML page
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>DSAR Deletion Verification - {safe_deletion_id}</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                max-width: 800px;
                margin: 40px auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            .container {{
                background: white;
                border-radius: 8px;
                padding: 30px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                margin-top: 0;
            }}
            .info {{
                background: #e3f2fd;
                border-left: 4px solid #2196F3;
                padding: 15px;
                margin: 20px 0;
            }}
            .success {{
                background: #e8f5e9;
                border-left: 4px solid #4CAF50;
                padding: 15px;
                margin: 20px 0;
            }}
            .warning {{
                background: #fff3e0;
                border-left: 4px solid #FF9800;
                padding: 15px;
                margin: 20px 0;
            }}
            .label {{
                font-weight: bold;
                color: #666;
            }}
            .value {{
                color: #333;
                margin-left: 10px;
            }}
            .footer {{
                margin-top: 40px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                color: #666;
                font-size: 14px;
            }}
            code {{
                background: #f5f5f5;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 GDPR Deletion Verification</h1>

            <div class="info">
                <p><strong>Deletion Request ID:</strong> <code>{safe_deletion_id}</code></p>
                <p>This page provides cryptographic verification that your data deletion request was processed.</p>
            </div>

            <h2>How to Verify</h2>
            <p>To verify your deletion proof:</p>
            <ol>
                <li>You should have received a signed deletion proof JSON file</li>
                <li>POST the deletion proof to <code>/v1/verification/deletion</code></li>
                <li>The API will verify the Ed25519 signature</li>
                <li>A valid signature proves the deletion was performed by CIRIS</li>
            </ol>

            <div class="warning">
                <p><strong>⚠️ Manual Verification</strong></p>
                <p>For maximum transparency, you can also verify the signature manually: canonicalize the
                deletion data per RFC 8785 (JCS) and verify the Ed25519 signature using the public key
                available at:</p>
                <p><code>GET /v1/verification/keys/{{key_id}}.pub</code></p>
            </div>

            <h2>What Gets Deleted?</h2>
            <p>Multi-source deletion includes:</p>
            <ul>
                <li><strong>CIRIS Internal:</strong> 90-day decay protocol (identity severed immediately)</li>
                <li><strong>SQL Databases:</strong> User records deleted and verified</li>
                <li><strong>External APIs:</strong> Deletion requests forwarded</li>
            </ul>

            <div class="footer">
                <p><strong>GDPR Compliance</strong></p>
                <p>This verification system implements Article 17 (Right to Erasure) with cryptographic proof.</p>
                <p>For questions, contact: privacy@ciris.ai</p>
            </div>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


@router.get("/keys/{key_id}.pub", response_class=PlainTextResponse)
async def download_public_key(
    key_id: str,
    req: Request,
) -> PlainTextResponse:
    """
    Download the local Ed25519 public key (base64, raw 32 bytes).

    NO AUTHENTICATION REQUIRED - Public keys are public by design.

    Users can download the public key to manually verify deletion signatures.
    """
    engine = _require_engine()

    try:
        current_key_id = engine.local_derived_key_id()
        public_key_b64 = engine.local_public_key_b64()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Local signing identity not configured: {e}",
        )

    if key_id != current_key_id:
        logger.warning(f"Public key request for unknown key ID: {key_id} (current: {current_key_id})")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Public key {key_id} not found. Current key: {current_key_id}",
        )

    logger.info(f"Public key {key_id} downloaded")

    return PlainTextResponse(
        content=public_key_b64,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{key_id}.pub"',
        },
    )


@router.post("/verify-signature")
async def manual_signature_verification(
    request: ManualSignatureVerificationRequest,
    req: Request,
) -> StandardResponse:
    """
    Manual signature verification endpoint.

    NO AUTHENTICATION REQUIRED - For manual verification using external tools.

    Users can verify signatures manually by:
    1. Canonicalizing deletion data per RFC 8785 (JCS)
    2. Verifying the Ed25519 signature using the public key
    3. Comparing with this endpoint's result
    """
    deletion_proof = DeletionProof(
        deletion_id=request.deletion_id,
        user_identifier=request.user_identifier,
        sources_deleted=request.sources_deleted,
        deleted_at=request.deleted_at,
        signature=request.signature,
        public_key_id=request.public_key_id,
    )

    verification_result = _verify_proof(deletion_proof)

    from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log

    safe_deletion_id = sanitize_for_log(request.deletion_id, max_length=100)
    logger.info(f"Manual signature verification: {safe_deletion_id} - Valid: {verification_result.valid}")

    return StandardResponse(
        success=verification_result.valid,
        data=verification_result.model_dump(),
        message=verification_result.message,
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "manual_verification": True,
        },
    )


@router.get("/keys/current")
async def get_current_public_key_info(
    req: Request,
) -> StandardResponse:
    """
    Get current public key information.

    NO AUTHENTICATION REQUIRED - Public key metadata is public.

    Returns the current public key ID and download URL.
    """
    engine = _require_engine()

    try:
        key_id = engine.local_derived_key_id()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Local signing identity not configured: {e}",
        )

    return StandardResponse(
        success=True,
        data={
            "public_key_id": key_id,
            "download_url": f"/v1/verification/keys/{key_id}.pub",
            "algorithm": "Ed25519 over RFC 8785 (JCS) canonical bytes",
        },
        message="Current public key information",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
