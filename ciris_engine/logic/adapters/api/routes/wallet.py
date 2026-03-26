"""
Wallet API routes for CIRIS.

Provides endpoints for wallet status and transfers:
- GET /v1/wallet/status - Get wallet address, balance, and limits
- POST /v1/wallet/transfer - Send USDC to another Base address

All endpoints require ADMIN authentication.
"""

import logging
from decimal import Decimal
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..dependencies.auth import AuthContext, require_admin

logger = logging.getLogger(__name__)

# Type alias for admin authentication dependency
AuthAdminDep = Annotated[AuthContext, Depends(require_admin)]

router = APIRouter(prefix="/wallet", tags=["wallet"])


# ============================================================================
# Request/Response Models
# ============================================================================


class WalletStatusResponse(BaseModel):
    """Wallet status response."""

    has_wallet: bool = Field(description="Whether wallet is configured")
    provider: str = Field(description="Wallet provider (x402, chapa, etc.)")
    network: str = Field(description="Network (base-mainnet, base-sepolia)")
    currency: str = Field(description="Primary currency (USDC)")
    balance: str = Field(description="Current USDC balance")
    eth_balance: str = Field(default="0.00", description="ETH balance for gas fees")
    needs_gas: bool = Field(default=True, description="True if ETH balance is too low for transfers")
    address: Optional[str] = Field(description="Wallet address (EVM format)")
    is_receive_only: bool = Field(description="True if sending is disabled")
    hardware_trust_degraded: bool = Field(description="True if hardware trust compromised")
    trust_degradation_reason: Optional[str] = Field(description="Reason for trust degradation")
    attestation_level: int = Field(description="Current attestation level (0-5)")
    max_transaction_limit: str = Field(description="Max per-transaction limit")
    daily_limit: str = Field(description="Daily spending limit")


class TransferRequest(BaseModel):
    """Transfer request."""

    recipient: str = Field(description="Recipient EVM address (0x...)")
    amount: str = Field(description="Amount to send (e.g., '10.00')")
    memo: Optional[str] = Field(default=None, description="Optional memo/note")


class TransferResponse(BaseModel):
    """Transfer response."""

    success: bool
    transaction_id: Optional[str] = None
    tx_hash: Optional[str] = None
    amount: str
    currency: str
    recipient: str
    error: Optional[str] = None


class SwapRequest(BaseModel):
    """USDC to ETH swap request for gas fees."""

    usdc_amount: str = Field(description="Amount of USDC to swap (e.g., '2.00')")


class SwapResponse(BaseModel):
    """Swap response."""

    success: bool
    usdc_spent: str = Field(description="USDC amount swapped")
    eth_received: str = Field(description="ETH amount received")
    tx_hash: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================


def _get_wallet_provider_from_app(request: Request) -> Any:
    """Get the x402 wallet provider from the app state."""
    logger.info("[WALLET_PROVIDER] Starting provider lookup...")

    try:
        # Get runtime from app state
        runtime = getattr(request.app.state, 'runtime', None)
        logger.info(f"[WALLET_PROVIDER] runtime: {runtime is not None}")

        if runtime:
            # runtime.adapters is a List, not a Dict
            adapters = getattr(runtime, 'adapters', [])
            logger.info(f"[WALLET_PROVIDER] runtime.adapters count: {len(adapters)}")

            for adapter in adapters:
                adapter_name = type(adapter).__name__
                logger.info(f"[WALLET_PROVIDER] Checking adapter: {adapter_name}")

                # Check if this adapter has a _providers dict with 'x402'
                if hasattr(adapter, '_providers'):
                    providers = getattr(adapter, '_providers', {})
                    logger.info(f"[WALLET_PROVIDER] {adapter_name} has _providers: {list(providers.keys())}")
                    if 'x402' in providers:
                        logger.info(f"[WALLET_PROVIDER] Found x402 in {adapter_name}!")
                        return providers['x402']

        logger.warning("[WALLET_PROVIDER] Could not find x402 provider in runtime.adapters")

    except Exception as e:
        logger.error(f"[WALLET_PROVIDER] Error: {e}", exc_info=True)

    return None


def _validate_recipient(recipient: str) -> Optional[str]:
    """Validate recipient address format. Returns error message or None if valid."""
    if not recipient.startswith("0x") or len(recipient) != 42:
        return "Invalid recipient address format. Must be 0x followed by 40 hex characters."
    return None


def _parse_transfer_amount(amount_str: str) -> tuple[Optional[Decimal], Optional[str]]:
    """Parse and validate transfer amount. Returns (amount, error_message)."""
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            return None, "Amount must be positive"
        return amount, None
    except Exception:
        return None, "Invalid amount format"


def _get_spending_authority(provider: Any) -> Any:
    """Get spending authority from provider, defaulting to level 0 if not available."""
    spending_authority = getattr(provider, '_spending_authority', None)
    if not spending_authority:
        from ciris_adapters.wallet.providers.x402_provider import SpendingAuthority
        spending_authority = SpendingAuthority.from_attestation(0)
        logger.info("[WALLET_TRANSFER] No spending_authority on provider - using receive-only defaults (level 0)")
    return spending_authority


# ============================================================================
# Routes
# ============================================================================


@router.get("/status")
async def get_wallet_status(
    request: Request,
    auth: AuthAdminDep,
) -> WalletStatusResponse:
    """
    Get wallet status including address, balance, and spending limits.

    Returns wallet configuration and current state based on CIRISVerify
    attestation level and hardware trust status.
    """
    logger.info("[WALLET_STATUS] Fetching wallet status")

    try:
        provider = _get_wallet_provider_from_app(request)

        if not provider:
            logger.warning("[WALLET_STATUS] No wallet provider available")
            return WalletStatusResponse(
                has_wallet=False,
                provider="none",
                network="unknown",
                currency="USDC",
                balance="0.00",
                eth_balance="0.00",
                needs_gas=True,
                address=None,
                is_receive_only=True,
                hardware_trust_degraded=False,
                trust_degradation_reason=None,
                attestation_level=0,
                max_transaction_limit="0.00",
                daily_limit="0.00",
            )

        # Get provider details
        address = getattr(provider, '_evm_address', None)
        network = getattr(provider.config, 'network', 'base-mainnet') if hasattr(provider, 'config') else 'base-mainnet'

        # Get attestation level from auth_service's cached attestation (same source as trust badge)
        # This ensures wallet and badge always show the same level and pending state
        attestation_level = 0
        max_tx = "0.00"
        daily = "0.00"
        is_receive_only = True
        hardware_degraded = False
        degradation_reason = None

        auth_service = getattr(request.app.state, "authentication_service", None)
        if auth_service:
            try:
                # Get cached attestation result - same source as /v1/setup/verify-status
                cached_result = auth_service.get_cached_attestation(allow_stale=True)
                if cached_result:
                    attestation_level = cached_result.max_level
                    hardware_degraded = getattr(cached_result, 'hardware_trust_degraded', False)
                    degradation_reason = getattr(cached_result, 'trust_degradation_reason', None)
                    logger.info(f"[WALLET_STATUS] Using cached attestation: level={attestation_level}, pending={cached_result.level_pending}")

                    # Import SpendingAuthority to calculate limits from level
                    from ciris_adapters.wallet.providers.x402_provider import SpendingAuthority
                    spending_authority = SpendingAuthority.from_attestation(
                        attestation_level=attestation_level,
                        hardware_trust_degraded=hardware_degraded,
                        trust_degradation_reason=degradation_reason,
                    )
                    max_tx = str(spending_authority.max_transaction)
                    daily = str(spending_authority.max_daily)
                    is_receive_only = spending_authority.max_transaction == Decimal("0")
                else:
                    logger.info("[WALLET_STATUS] No cached attestation available - using level 0 defaults")
            except Exception as e:
                logger.warning(f"[WALLET_STATUS] Failed to get cached attestation: {e}")
        else:
            logger.warning("[WALLET_STATUS] Authentication service not available - using level 0 defaults")

        # Get balance (cached, don't block on RPC)
        balance = "0.00"
        eth_balance = "0.00"
        if hasattr(provider, '_balance'):
            balance = str(provider._balance.available)
            # ETH balance is stored in metadata by the balance monitor
            if provider._balance.metadata:
                eth_balance = provider._balance.metadata.get("eth_balance", "0.00")

        # Determine if user needs gas (< 0.0001 ETH is too low for a transfer)
        # A typical USDC transfer on Base costs ~0.00002-0.00005 ETH
        try:
            eth_decimal = Decimal(eth_balance)
            needs_gas = eth_decimal < Decimal("0.0001")
        except Exception:
            needs_gas = True

        logger.info(f"[WALLET_STATUS] Returning status: address={address}, balance={balance}, eth={eth_balance}, needs_gas={needs_gas}, level={attestation_level}")

        return WalletStatusResponse(
            has_wallet=True,
            provider="x402",
            network=network,
            currency="USDC",
            balance=balance,
            eth_balance=eth_balance,
            needs_gas=needs_gas,
            address=address,
            is_receive_only=is_receive_only,
            hardware_trust_degraded=hardware_degraded,
            trust_degradation_reason=degradation_reason,
            attestation_level=attestation_level,
            max_transaction_limit=max_tx,
            daily_limit=daily,
        )

    except Exception as e:
        logger.error(f"[WALLET_STATUS] Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get wallet status: {str(e)}",
        )


@router.post("/transfer")
async def transfer_usdc(
    transfer_request: TransferRequest,
    request: Request,
    auth: AuthAdminDep,
) -> TransferResponse:
    """
    Transfer USDC to another Base address.

    This is for manual fiat cashout - send USDC to an exchange or
    other address for conversion to fiat currency.

    Requires appropriate attestation level for the amount.
    """
    # Log transfer request without user-controlled data to prevent log injection
    logger.info("[WALLET_TRANSFER] Transfer request received")

    try:
        provider = _get_wallet_provider_from_app(request)

        if not provider:
            return TransferResponse(
                success=False,
                amount=transfer_request.amount,
                currency="USDC",
                recipient=transfer_request.recipient,
                error="Wallet provider not available",
            )

        # Validate recipient address format
        recipient_error = _validate_recipient(transfer_request.recipient)
        if recipient_error:
            return TransferResponse(
                success=False,
                amount=transfer_request.amount,
                currency="USDC",
                recipient=transfer_request.recipient,
                error=recipient_error,
            )

        # Parse and validate amount
        amount, amount_error = _parse_transfer_amount(transfer_request.amount)
        if amount_error:
            return TransferResponse(
                success=False,
                amount=transfer_request.amount,
                currency="USDC",
                recipient=transfer_request.recipient,
                error=amount_error,
            )

        # Check spending authority
        spending_authority = _get_spending_authority(provider)
        can_spend, spend_error = spending_authority.can_spend(amount)
        if not can_spend:
            return TransferResponse(
                success=False,
                amount=transfer_request.amount,
                currency="USDC",
                recipient=transfer_request.recipient,
                error=spend_error,
            )

        # Execute transfer
        try:
            result = await provider.send(
                recipient=transfer_request.recipient,
                amount=amount,
                currency="USDC",
                memo=transfer_request.memo,
            )

            if result.success:
                logger.info(f"[WALLET_TRANSFER] Success: tx_id={result.transaction_id}")
                return TransferResponse(
                    success=True,
                    transaction_id=result.transaction_id,
                    tx_hash=result.confirmation.get("tx_hash") if result.confirmation else None,
                    amount=transfer_request.amount,
                    currency="USDC",
                    recipient=transfer_request.recipient,
                )
            else:
                return TransferResponse(
                    success=False,
                    amount=transfer_request.amount,
                    currency="USDC",
                    recipient=transfer_request.recipient,
                    error=result.error or "Transfer failed",
                )

        except Exception as e:
            logger.error(f"[WALLET_TRANSFER] Send failed: {e}", exc_info=True)
            return TransferResponse(
                success=False,
                amount=transfer_request.amount,
                currency="USDC",
                recipient=transfer_request.recipient,
                error=str(e),
            )

    except Exception as e:
        logger.error(f"[WALLET_TRANSFER] Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transfer failed: {str(e)}",
        )


@router.post("/swap-for-gas")
async def swap_usdc_for_eth(
    swap_request: SwapRequest,
    request: Request,
    auth: AuthAdminDep,
) -> SwapResponse:
    """
    Swap USDC for ETH to pay for gas fees.

    This is a self-custody swap - the user's wallet signs the swap
    transaction via Uniswap V3 on Base. CIRIS does not custody or
    touch the funds; we only facilitate the user's signed transaction.

    Typical usage: Swap $2 USDC for ~0.0005 ETH (enough for ~10-20 transfers).
    """
    # Log swap request without user-controlled data to prevent log injection
    logger.info("[WALLET_SWAP] Swap request received")

    try:
        provider = _get_wallet_provider_from_app(request)

        if not provider:
            return SwapResponse(
                success=False,
                usdc_spent="0",
                eth_received="0",
                error="Wallet provider not available",
            )

        # Parse amount
        try:
            usdc_amount = Decimal(swap_request.usdc_amount)
            if usdc_amount <= 0:
                raise ValueError("Amount must be positive")
            if usdc_amount > Decimal("10"):
                raise ValueError("Max swap amount is $10 USDC")
        except ValueError as e:
            return SwapResponse(
                success=False,
                usdc_spent="0",
                eth_received="0",
                error=str(e),
            )

        # Check spending authority (same as transfer)
        spending_authority = getattr(provider, '_spending_authority', None)
        if not spending_authority:
            from ciris_adapters.wallet.providers.x402_provider import SpendingAuthority
            spending_authority = SpendingAuthority.from_attestation(0)

        can_spend, error_msg = spending_authority.can_spend(usdc_amount)
        if not can_spend:
            return SwapResponse(
                success=False,
                usdc_spent="0",
                eth_received="0",
                error=f"Cannot swap: {error_msg}",
            )

        # Execute swap via provider's chain client
        # This calls Uniswap V3 on Base - user signs the swap tx
        chain_client = getattr(provider, '_chain_client', None)
        if not chain_client:
            return SwapResponse(
                success=False,
                usdc_spent="0",
                eth_received="0",
                error="Chain client not available",
            )

        # For MVP: Return "not implemented" until we add Uniswap integration
        # The actual implementation would:
        # 1. Build Uniswap V3 exactInputSingle call data
        # 2. Sign with user's key via provider._signing_callback
        # 3. Submit to chain via chain_client.send_raw_transaction
        #
        # This is a placeholder that shows the intended flow
        logger.warning("[WALLET_SWAP] Swap not yet implemented - returning placeholder")
        return SwapResponse(
            success=False,
            usdc_spent="0",
            eth_received="0",
            error="USDC→ETH swap coming soon. For now, send a small amount of ETH to your wallet address for gas.",
        )

    except Exception as e:
        logger.error(f"[WALLET_SWAP] Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Swap failed: {str(e)}",
        )
