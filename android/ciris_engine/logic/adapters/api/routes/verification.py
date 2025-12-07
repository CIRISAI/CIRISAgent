"""Deletion verification API endpoints.

Provides public verification of DSAR deletion proofs using RSA signatures.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ciris_engine.logic.services.governance.dsar.signature_service import (
    DeletionProof,
    RSASignatureService,
    SignatureVerificationResult,
)

from ..models import StandardResponse

router = APIRouter(prefix="/verification", tags=["Verification"])

# Global signature service instance
_signature_service: Optional[RSASignatureService] = None


def _get_signature_service(req: Request) -> RSASignatureService:
    """Get or create signature service.

    Args:
        req: FastAPI request

    Returns:
        RSASignatureService instance
    """
    global _signature_service

    if _signature_service is None:
        _signature_service = RSASignatureService(key_size=2048)

    return _signature_service


class VerifyDeletionRequest(BaseModel):
    """Request to verify a deletion proof."""

    deletion_proof: DeletionProof = Field(..., description="Signed deletion proof to verify")


class ManualSignatureVerificationRequest(BaseModel):
    """Request for manual signature verification."""

    deletion_id: str = Field(..., description="Deletion request ID")
    user_identifier: str = Field(..., description="User identifier")
    sources_deleted: Dict[str, Any] = Field(..., description="Sources and records deleted (for hash computation)")
    deleted_at: str = Field(..., description="ISO 8601 deletion timestamp")
    verification_hash: str = Field(..., description="SHA-256 hash to verify")
    signature: str = Field(..., description="Base64-encoded RSA signature")
    public_key_id: str = Field(..., description="Public key ID used for signing")


@router.post("/deletion", response_model=StandardResponse)
async def verify_deletion_proof(
    request: VerifyDeletionRequest,
    req: Request,
) -> StandardResponse:
    """
    Verify cryptographic deletion proof.

    NO AUTHENTICATION REQUIRED - Public verification endpoint.

    Users can verify that their data was actually deleted by checking
    the RSA-PSS signature on the deletion proof.

    Returns verification result with signature validity.
    """
    import logging

    logger = logging.getLogger(__name__)

    signature_service = _get_signature_service(req)

    try:
        verification_result = signature_service.verify_deletion(request.deletion_proof)

        logger.info(
            f"Deletion verification request: {request.deletion_proof.deletion_id} - Valid: {verification_result.valid}"
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

    except Exception as e:
        logger.error(f"Deletion verification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}",
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
                <li>The API will verify the RSA-PSS signature</li>
                <li>A valid signature proves the deletion was performed by CIRIS</li>
            </ol>

            <div class="warning">
                <p><strong>⚠️ Manual Verification</strong></p>
                <p>For maximum transparency, you can also verify the signature manually using the public key available at:</p>
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
    Download RSA public key.

    NO AUTHENTICATION REQUIRED - Public keys are public by design.

    Users can download the public key to manually verify deletion signatures.
    """
    import logging

    logger = logging.getLogger(__name__)

    signature_service = _get_signature_service(req)

    # Check if requested key ID matches current key
    current_key_id = signature_service.get_public_key_id()

    if key_id != current_key_id:
        logger.warning(f"Public key request for unknown key ID: {key_id} (current: {current_key_id})")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Public key {key_id} not found. Current key: {current_key_id}",
        )

    try:
        public_key_pem = signature_service.get_public_key_pem()

        logger.info(f"Public key {key_id} downloaded")

        return PlainTextResponse(
            content=public_key_pem,
            media_type="application/x-pem-file",
            headers={
                "Content-Disposition": f'attachment; filename="{key_id}.pub"',
            },
        )

    except Exception as e:
        logger.error(f"Failed to retrieve public key {key_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve public key",
        )


@router.post("/verify-signature", response_model=StandardResponse)
async def manual_signature_verification(
    request: ManualSignatureVerificationRequest,
    req: Request,
) -> StandardResponse:
    """
    Manual signature verification endpoint.

    NO AUTHENTICATION REQUIRED - For manual verification using external tools.

    Users can verify signatures manually by:
    1. Computing hash of deletion data
    2. Verifying RSA-PSS signature using public key
    3. Comparing with this endpoint's result

    This endpoint helps users who want to verify independently.
    """
    import logging

    logger = logging.getLogger(__name__)

    signature_service = _get_signature_service(req)

    # Build deletion proof for verification with provided data
    deletion_proof = DeletionProof(
        deletion_id=request.deletion_id,
        user_identifier=request.user_identifier,
        sources_deleted=request.sources_deleted,
        deleted_at=request.deleted_at,
        verification_hash=request.verification_hash,
        signature=request.signature,
        public_key_id=request.public_key_id,
    )

    try:
        verification_result = signature_service.verify_deletion(deletion_proof)

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

    except Exception as e:
        logger.error(f"Manual verification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Manual verification failed: {str(e)}",
        )


@router.get("/keys/current", response_model=StandardResponse)
async def get_current_public_key_info(
    req: Request,
) -> StandardResponse:
    """
    Get current public key information.

    NO AUTHENTICATION REQUIRED - Public key metadata is public.

    Returns the current public key ID and download URL.
    """
    signature_service = _get_signature_service(req)

    key_id = signature_service.get_public_key_id()

    return StandardResponse(
        success=True,
        data={
            "public_key_id": key_id,
            "download_url": f"/v1/verification/keys/{key_id}.pub",
            "algorithm": "RSA-PSS with SHA-256",
            "key_size": 2048,
        },
        message="Current public key information",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
