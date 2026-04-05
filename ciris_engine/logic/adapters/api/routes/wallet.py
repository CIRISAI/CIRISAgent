"""
Wallet API routes for CIRIS.

Provides endpoints for wallet status and transfers:
- GET /v1/wallet/status - Get wallet address, balance, limits, and spending tracking
- POST /v1/wallet/transfer - Send USDC to another Base address
- POST /v1/wallet/validate-address - Validate EIP-55 checksum
- GET /v1/wallet/transactions - Get transaction history
- POST /v1/wallet/swap-for-gas - Swap USDC for ETH gas

Read endpoints require any authentication, write endpoints require ADMIN.
All sends/transfers/receives are audited via the audit service with spam prevention.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..dependencies.auth import AuthContext, get_auth_context, require_admin

logger = logging.getLogger(__name__)


# ============================================================================
# Audit Helper
# ============================================================================


def _get_wallet_audit_helper(request: Request) -> Any:
    """Get the wallet audit helper with audit service from runtime."""
    try:
        from ciris_adapters.wallet.audit import get_wallet_audit_helper

        # Get audit service from runtime
        audit_service = None
        runtime = getattr(request.app.state, "runtime", None)
        if runtime:
            audit_service = getattr(runtime, "audit_service", None)

        return get_wallet_audit_helper(audit_service)
    except ImportError:
        logger.warning("[WALLET_AUDIT] Could not import wallet audit helper")
        return None
    except Exception as e:
        logger.warning(f"[WALLET_AUDIT] Could not get wallet audit helper: {e}")
        return None


# Type aliases for authentication dependencies
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]  # Any authenticated user
AuthAdminDep = Annotated[AuthContext, Depends(require_admin)]  # Admin only

router = APIRouter(prefix="/wallet", tags=["wallet"])


# ============================================================================
# Request/Response Models
# ============================================================================


class GasEstimate(BaseModel):
    """Gas cost estimate for a standard transfer."""

    gas_price_gwei: str = Field(description="Current gas price in gwei")
    usdc_transfer_gas: int = Field(default=65000, description="Gas units for USDC transfer")
    eth_transfer_gas: int = Field(default=21000, description="Gas units for ETH transfer")
    usdc_transfer_cost_eth: str = Field(description="Cost in ETH for USDC transfer")
    usdc_transfer_cost_usd: str = Field(description="Cost in USD for USDC transfer")
    eth_price_usd: str = Field(description="Current ETH/USD price estimate")


class SpendingProgress(BaseModel):
    """Spending progress for session and daily limits."""

    session_spent: str = Field(default="0.00", description="Amount spent in current session")
    session_remaining: str = Field(description="Remaining session allowance")
    session_limit: str = Field(default="500.00", description="Session spending limit")
    session_reset_minutes: int = Field(description="Minutes until session resets")
    daily_spent: str = Field(default="0.00", description="Amount spent today")
    daily_remaining: str = Field(description="Remaining daily allowance")
    daily_reset_hours: int = Field(description="Hours until daily resets")


class TransactionSummary(BaseModel):
    """Summary of a recent transaction."""

    transaction_id: str = Field(description="Transaction ID or hash")
    type: str = Field(description="Transaction type (send, receive)")
    amount: str = Field(description="Transaction amount")
    currency: str = Field(description="Currency code")
    recipient: Optional[str] = Field(default=None, description="Recipient address (for sends)")
    sender: Optional[str] = Field(default=None, description="Sender address (for receives)")
    status: str = Field(description="Transaction status")
    timestamp: str = Field(description="ISO timestamp")
    explorer_url: Optional[str] = Field(default=None, description="Block explorer URL")


class SecurityAdvisory(BaseModel):
    """Security advisory affecting hardware trust."""

    cve: Optional[str] = Field(default=None, description="CVE identifier")
    title: str = Field(description="Advisory title")
    impact: str = Field(description="Impact description")
    remediation: Optional[str] = Field(default=None, description="Remediation steps")


class WalletStatusResponse(BaseModel):
    """Wallet status response with comprehensive state."""

    # Core wallet info
    has_wallet: bool = Field(description="Whether wallet is configured")
    provider: str = Field(description="Wallet provider (x402, chapa, etc.)")
    network: str = Field(description="Network (base-mainnet, base-sepolia)")
    currency: str = Field(description="Primary currency (USDC)")
    balance: str = Field(description="Current USDC balance")
    eth_balance: str = Field(default="0.00", description="ETH balance for gas fees")
    needs_gas: bool = Field(default=True, description="True if ETH balance is too low for transfers")
    address: Optional[str] = Field(default=None, description="Wallet address (EVM format)")

    # Paymaster status (ERC-4337 gasless transactions)
    paymaster_enabled: bool = Field(default=False, description="Whether paymaster is enabled in config")
    paymaster_key_configured: bool = Field(default=False, description="Whether Arka API key is configured")

    # Attestation and limits
    is_receive_only: bool = Field(description="True if sending is disabled")
    attestation_level: int = Field(description="Current attestation level (0-5)")
    max_transaction_limit: str = Field(description="Max per-transaction limit")
    daily_limit: str = Field(description="Daily spending limit")

    # Hardware trust status
    hardware_trust_degraded: bool = Field(description="True if hardware trust compromised")
    trust_degradation_reason: Optional[str] = Field(default=None, description="Reason for trust degradation")
    security_advisories: List[SecurityAdvisory] = Field(default_factory=list, description="Security advisories")

    # Spending progress (new)
    spending: Optional[SpendingProgress] = Field(default=None, description="Spending progress tracking")

    # Gas estimates (new)
    gas_estimate: Optional[GasEstimate] = Field(default=None, description="Gas cost estimates")

    # Recent transactions (new)
    recent_transactions: List[TransactionSummary] = Field(default_factory=list, description="Last 5 transactions")


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


class AddressValidationRequest(BaseModel):
    """Address validation request."""

    address: str = Field(description="EVM address to validate")


class AddressValidationResponse(BaseModel):
    """Address validation response with EIP-55 checksum details."""

    valid: bool = Field(description="Whether address is valid")
    checksum_valid: bool = Field(description="Whether EIP-55 checksum is valid")
    computed_checksum: Optional[str] = Field(default=None, description="Properly checksummed address")
    is_zero_address: bool = Field(default=False, description="True if zero address (would burn funds)")
    error: Optional[str] = Field(default=None, description="Validation error message")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")


class TransactionHistoryResponse(BaseModel):
    """Transaction history response."""

    transactions: List[TransactionSummary] = Field(description="Transaction history")
    total_count: int = Field(description="Total number of transactions")
    has_more: bool = Field(description="Whether more transactions exist")


class DuplicateCheckRequest(BaseModel):
    """Duplicate transaction check request."""

    recipient: str = Field(description="Recipient address")
    amount: str = Field(description="Transaction amount")
    currency: str = Field(default="USDC", description="Currency code")


class DuplicateCheckResponse(BaseModel):
    """Duplicate transaction check response."""

    is_duplicate: bool = Field(description="True if similar transaction exists in window")
    last_tx_seconds_ago: Optional[int] = Field(default=None, description="Seconds since last similar tx")
    window_seconds: int = Field(default=300, description="Duplicate detection window")
    warning: Optional[str] = Field(default=None, description="Warning message if duplicate")


# ============================================================================
# Helper Functions
# ============================================================================


def _get_wallet_provider_from_app(request: Request) -> Any:
    """Get the x402 wallet provider from the app state."""
    logger.info("[WALLET_PROVIDER] Starting provider lookup...")

    try:
        # Get runtime from app state
        runtime = getattr(request.app.state, "runtime", None)
        logger.info(f"[WALLET_PROVIDER] runtime: {runtime is not None}")

        if runtime:
            # runtime.adapters is a List, not a Dict
            adapters = getattr(runtime, "adapters", [])
            logger.info(f"[WALLET_PROVIDER] runtime.adapters count: {len(adapters)}")

            for adapter in adapters:
                adapter_name = type(adapter).__name__
                logger.info(f"[WALLET_PROVIDER] Checking adapter: {adapter_name}")

                # Check if this adapter has a _providers dict with 'x402'
                if hasattr(adapter, "_providers"):
                    providers = getattr(adapter, "_providers", {})
                    logger.info(f"[WALLET_PROVIDER] {adapter_name} has _providers: {list(providers.keys())}")
                    if "x402" in providers:
                        logger.info(f"[WALLET_PROVIDER] Found x402 in {adapter_name}!")
                        return providers["x402"]

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
    spending_authority = getattr(provider, "_spending_authority", None)
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
    auth: AuthDep,
) -> WalletStatusResponse:
    """
    Get wallet status including address, balance, spending limits, and tracking.

    Returns comprehensive wallet state including:
    - Balance and gas status
    - Attestation level and limits
    - Session/daily spending progress
    - Gas cost estimates
    - Recent transactions (last 5)
    - Hardware trust status with security advisories
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
                paymaster_enabled=False,
                paymaster_key_configured=False,
                is_receive_only=True,
                hardware_trust_degraded=False,
                trust_degradation_reason=None,
                attestation_level=0,
                max_transaction_limit="0.00",
                daily_limit="0.00",
            )

        # Get provider details
        address = getattr(provider, "_evm_address", None)
        network = getattr(provider.config, "network", "base-mainnet") if hasattr(provider, "config") else "base-mainnet"

        # Get attestation level from auth_service's cached attestation (same source as trust badge)
        attestation_level = 0
        max_tx = "0.00"
        daily = "0.00"
        is_receive_only = True
        hardware_degraded = False
        degradation_reason = None
        security_advisories_list: List[SecurityAdvisory] = []

        auth_service = getattr(request.app.state, "authentication_service", None)
        if auth_service:
            try:
                cached_result = auth_service.get_cached_attestation(allow_stale=True)
                if cached_result:
                    attestation_level = cached_result.max_level
                    hardware_degraded = getattr(cached_result, "hardware_trust_degraded", False)
                    degradation_reason = getattr(cached_result, "trust_degradation_reason", None)

                    # Extract security advisories if available
                    raw_advisories = getattr(cached_result, "security_advisories", None)
                    if raw_advisories:
                        for adv in raw_advisories:
                            security_advisories_list.append(
                                SecurityAdvisory(
                                    cve=adv.get("cve"),
                                    title=adv.get("title", "Unknown"),
                                    impact=adv.get("impact", "Unknown"),
                                    remediation=adv.get("remediation"),
                                )
                            )

                    logger.info(f"[WALLET_STATUS] Using cached attestation: level={attestation_level}")

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
        if hasattr(provider, "_balance"):
            balance = str(provider._balance.available)
            if provider._balance.metadata:
                eth_balance = provider._balance.metadata.get("eth_balance", "0.00")

        # Determine if user needs gas
        try:
            eth_decimal = Decimal(eth_balance)
            needs_gas = eth_decimal < Decimal("0.0001")
        except Exception:
            needs_gas = True

        # Get spending progress from validator
        spending_progress = None
        validator = getattr(provider, "_validator", None)
        if validator:
            try:
                import time

                tracker = validator.spending_tracker

                # Calculate time until resets
                now = time.time()
                session_elapsed = now - tracker.session_start_timestamp
                session_remaining_secs = max(0, 3600 - session_elapsed)  # 1 hour sessions
                daily_elapsed = now - tracker.daily_reset_timestamp
                daily_remaining_secs = max(0, 86400 - daily_elapsed)

                session_spent = tracker.session_spent.get("USDC", Decimal("0"))
                daily_spent = tracker.daily_spent.get("USDC", Decimal("0"))

                spending_progress = SpendingProgress(
                    session_spent=str(session_spent),
                    session_remaining=str(max(Decimal("0"), tracker.session_limit - session_spent)),
                    session_limit=str(tracker.session_limit),
                    session_reset_minutes=int(session_remaining_secs / 60),
                    daily_spent=str(daily_spent),
                    daily_remaining=str(max(Decimal("0"), tracker.daily_limit - daily_spent)),
                    daily_reset_hours=int(daily_remaining_secs / 3600),
                )
            except Exception as e:
                logger.debug(f"[WALLET_STATUS] Could not get spending progress: {e}")

        # Get gas estimates from chain client
        gas_estimate = None
        chain_client = getattr(provider, "_chain_client", None)
        if chain_client:
            try:
                gas_price = await chain_client.get_gas_price()
                gas_price_gwei = gas_price / 10**9

                # Calculate costs (assume ETH ~ $2000 for estimate)
                eth_price_usd = Decimal("2000")  # Could fetch from oracle
                usdc_gas = 65000
                usdc_cost_eth = Decimal(usdc_gas * gas_price) / Decimal(10**18)
                usdc_cost_usd = usdc_cost_eth * eth_price_usd

                gas_estimate = GasEstimate(
                    gas_price_gwei=f"{gas_price_gwei:.2f}",
                    usdc_transfer_gas=65000,
                    eth_transfer_gas=21000,
                    usdc_transfer_cost_eth=f"{usdc_cost_eth:.6f}",
                    usdc_transfer_cost_usd=f"{usdc_cost_usd:.4f}",
                    eth_price_usd=str(eth_price_usd),
                )
            except Exception as e:
                logger.debug(f"[WALLET_STATUS] Could not get gas estimates: {e}")

        # Get recent transactions
        recent_transactions: List[TransactionSummary] = []
        transactions = getattr(provider, "_transactions", [])
        for tx in transactions[:5]:
            try:
                explorer_url = None
                if tx.confirmation and tx.confirmation.get("explorer_url"):
                    explorer_url = tx.confirmation["explorer_url"]

                recent_transactions.append(
                    TransactionSummary(
                        transaction_id=tx.transaction_id,
                        type=tx.type.value if hasattr(tx.type, "value") else str(tx.type),
                        amount=str(abs(tx.amount)),
                        currency=tx.currency,
                        recipient=tx.recipient,
                        sender=tx.sender,
                        status=tx.status.value if hasattr(tx.status, "value") else str(tx.status),
                        timestamp=tx.timestamp.isoformat(),
                        explorer_url=explorer_url,
                    )
                )
            except Exception as e:
                logger.debug(f"[WALLET_STATUS] Could not parse transaction: {e}")

        # Get paymaster status (check both Coinbase and Arka paymasters)
        paymaster_enabled = False
        paymaster_key_configured = False

        # Check for Coinbase Paymaster first (preferred)
        coinbase_paymaster = getattr(provider, "_coinbase_paymaster", None)
        if coinbase_paymaster is not None:
            paymaster_enabled = True
            paymaster_key_configured = True  # Coinbase uses embedded URL, no separate key needed
            logger.debug("[WALLET_STATUS] Coinbase Paymaster is active")

        # Fall back to Arka paymaster
        if not paymaster_enabled:
            paymaster_config = getattr(provider, "paymaster_config", None)
            if paymaster_config:
                paymaster_enabled = getattr(paymaster_config, "enabled", False)
                # Check if key is configured (via _get_arka_api_key method or config)
                if hasattr(provider, "_get_arka_api_key"):
                    key = provider._get_arka_api_key()
                    paymaster_key_configured = key is not None and len(key) > 0
                elif paymaster_config.arka_api_key:
                    paymaster_key_configured = True

        logger.info(
            f"[WALLET_STATUS] Returning status: address={address}, balance={balance}, eth={eth_balance}, level={attestation_level}, paymaster={paymaster_enabled}"
        )

        return WalletStatusResponse(
            has_wallet=True,
            provider="x402",
            network=network,
            currency="USDC",
            balance=balance,
            eth_balance=eth_balance,
            needs_gas=needs_gas,
            address=address,
            paymaster_enabled=paymaster_enabled,
            paymaster_key_configured=paymaster_key_configured,
            is_receive_only=is_receive_only,
            attestation_level=attestation_level,
            max_transaction_limit=max_tx,
            daily_limit=daily,
            hardware_trust_degraded=hardware_degraded,
            trust_degradation_reason=degradation_reason,
            security_advisories=security_advisories_list,
            spending=spending_progress,
            gas_estimate=gas_estimate,
            recent_transactions=recent_transactions,
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

                # Audit successful transfer
                audit_helper = _get_wallet_audit_helper(request)
                if audit_helper and amount:
                    tx_hash = result.confirmation.get("tx_hash") if result.confirmation else None
                    await audit_helper.audit_send(
                        recipient=transfer_request.recipient,
                        amount=amount,
                        currency="USDC",
                        tx_hash=tx_hash,
                        tx_id=result.transaction_id,
                    )

                return TransferResponse(
                    success=True,
                    transaction_id=result.transaction_id,
                    tx_hash=result.confirmation.get("tx_hash") if result.confirmation else None,
                    amount=transfer_request.amount,
                    currency="USDC",
                    recipient=transfer_request.recipient,
                )
            else:
                # Audit failed transfer (rate limited)
                audit_helper = _get_wallet_audit_helper(request)
                if audit_helper and amount:
                    await audit_helper.audit_send_failed(
                        recipient=transfer_request.recipient,
                        amount=amount,
                        currency="USDC",
                        error=result.error or "Transfer failed",
                    )

                return TransferResponse(
                    success=False,
                    amount=transfer_request.amount,
                    currency="USDC",
                    recipient=transfer_request.recipient,
                    error=result.error or "Transfer failed",
                )

        except Exception as e:
            logger.error(f"[WALLET_TRANSFER] Send failed: {e}", exc_info=True)

            # Audit exception (rate limited)
            audit_helper = _get_wallet_audit_helper(request)
            if audit_helper and amount:
                await audit_helper.audit_send_failed(
                    recipient=transfer_request.recipient,
                    amount=amount,
                    currency="USDC",
                    error=str(e),
                )

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


@router.post("/validate-address")
async def validate_address(
    validation_request: AddressValidationRequest,
    request: Request,
    auth: AuthDep,
) -> AddressValidationResponse:
    """
    Validate an EVM address with EIP-55 checksum verification.

    Returns:
    - Whether the address format is valid
    - Whether the EIP-55 checksum is correct
    - The properly checksummed address
    - Warnings for zero address or other issues
    """
    logger.info("[WALLET_VALIDATE] Validating address")
    address = validation_request.address

    try:
        from ciris_adapters.wallet.providers.validation import (
            compute_checksum_address,
            is_zero_address,
            validate_eip55_checksum,
        )

        warnings: List[str] = []

        # Basic format validation
        if not address.startswith("0x"):
            return AddressValidationResponse(
                valid=False,
                checksum_valid=False,
                error="Address must start with 0x",
            )

        if len(address) != 42:
            return AddressValidationResponse(
                valid=False,
                checksum_valid=False,
                error=f"Address must be 42 characters, got {len(address)}",
            )

        # Check hex characters
        hex_part = address[2:]
        try:
            int(hex_part, 16)
        except ValueError:
            return AddressValidationResponse(
                valid=False,
                checksum_valid=False,
                error="Address contains invalid hex characters",
            )

        # Zero address check
        zero_addr = is_zero_address(address)
        if zero_addr:
            warnings.append("This is the zero address - sending funds here will burn them permanently!")

        # EIP-55 checksum validation
        checksum_valid = validate_eip55_checksum(address)
        computed_checksum = compute_checksum_address(address)

        if not checksum_valid:
            warnings.append(f"Checksum invalid. Did you mean: {computed_checksum}?")

        return AddressValidationResponse(
            valid=True,
            checksum_valid=checksum_valid,
            computed_checksum=computed_checksum,
            is_zero_address=zero_addr,
            warnings=warnings,
        )

    except Exception as e:
        logger.error(f"[WALLET_VALIDATE] Error: {e}", exc_info=True)
        return AddressValidationResponse(
            valid=False,
            checksum_valid=False,
            error=str(e),
        )


@router.get("/transactions")
async def get_transactions(
    request: Request,
    auth: AuthDep,
    limit: int = 50,
    offset: int = 0,
) -> TransactionHistoryResponse:
    """
    Get wallet transaction history.

    Args:
        limit: Maximum transactions to return (default 50, max 100)
        offset: Offset for pagination

    Returns:
        List of transactions with pagination info
    """
    logger.info(f"[WALLET_TRANSACTIONS] Fetching transactions, limit={limit}, offset={offset}")

    try:
        provider = _get_wallet_provider_from_app(request)

        if not provider:
            return TransactionHistoryResponse(
                transactions=[],
                total_count=0,
                has_more=False,
            )

        # Cap limit at 100
        limit = min(limit, 100)

        # Get transactions from provider
        transactions = getattr(provider, "_transactions", [])
        total_count = len(transactions)

        # Apply pagination
        paginated = transactions[offset : offset + limit]

        # Convert to summaries
        tx_summaries: List[TransactionSummary] = []
        for tx in paginated:
            try:
                explorer_url = None
                if tx.confirmation and tx.confirmation.get("explorer_url"):
                    explorer_url = tx.confirmation["explorer_url"]

                tx_summaries.append(
                    TransactionSummary(
                        transaction_id=tx.transaction_id,
                        type=tx.type.value if hasattr(tx.type, "value") else str(tx.type),
                        amount=str(abs(tx.amount)),
                        currency=tx.currency,
                        recipient=tx.recipient,
                        sender=tx.sender,
                        status=tx.status.value if hasattr(tx.status, "value") else str(tx.status),
                        timestamp=tx.timestamp.isoformat(),
                        explorer_url=explorer_url,
                    )
                )
            except Exception as e:
                logger.debug(f"[WALLET_TRANSACTIONS] Could not parse transaction: {e}")

        return TransactionHistoryResponse(
            transactions=tx_summaries,
            total_count=total_count,
            has_more=offset + limit < total_count,
        )

    except Exception as e:
        logger.error(f"[WALLET_TRANSACTIONS] Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get transactions: {str(e)}",
        )


@router.post("/check-duplicate")
async def check_duplicate_transaction(
    check_request: DuplicateCheckRequest,
    request: Request,
    auth: AuthAdminDep,
) -> DuplicateCheckResponse:
    """
    Check if a transaction would be a duplicate.

    Helps prevent accidental double-sends by checking if a similar
    transaction (same recipient, amount, currency) was sent recently.
    """
    logger.info("[WALLET_DUPLICATE] Checking for duplicate transaction")

    try:
        provider = _get_wallet_provider_from_app(request)

        if not provider:
            return DuplicateCheckResponse(
                is_duplicate=False,
                window_seconds=300,
            )

        # Get validator's duplicate protection
        validator = getattr(provider, "_validator", None)
        if not validator:
            return DuplicateCheckResponse(
                is_duplicate=False,
                window_seconds=300,
            )

        # Parse amount
        try:
            amount = Decimal(check_request.amount)
        except Exception:
            return DuplicateCheckResponse(
                is_duplicate=False,
                window_seconds=300,
                warning="Invalid amount format",
            )

        # Check for duplicate
        from ciris_adapters.wallet.providers.validation import DuplicateProtection

        dup_protection = validator.duplicate_protection

        # Compute fingerprint and check
        fingerprint = dup_protection._compute_tx_fingerprint(
            check_request.recipient,
            amount,
            check_request.currency,
        )

        dup_protection._cleanup_old()

        if fingerprint in dup_protection.recent_transactions:
            import time

            elapsed = int(time.time() - dup_protection.recent_transactions[fingerprint])
            return DuplicateCheckResponse(
                is_duplicate=True,
                last_tx_seconds_ago=elapsed,
                window_seconds=int(dup_protection.window_seconds),
                warning=f"You sent {check_request.amount} {check_request.currency} to this address {elapsed} seconds ago. "
                f"Are you sure you want to send again?",
            )

        return DuplicateCheckResponse(
            is_duplicate=False,
            window_seconds=int(dup_protection.window_seconds),
        )

    except Exception as e:
        logger.error(f"[WALLET_DUPLICATE] Error: {e}", exc_info=True)
        return DuplicateCheckResponse(
            is_duplicate=False,
            window_seconds=300,
            warning=f"Could not check for duplicates: {str(e)}",
        )


class PaymasterKeyRequest(BaseModel):
    """Request to set Arka paymaster API key."""

    api_key: str = Field(description="Etherspot Arka API key")


class PaymasterKeyResponse(BaseModel):
    """Response for paymaster key operations."""

    success: bool
    key_configured: bool = Field(description="Whether a key is now configured")
    message: Optional[str] = None
    error: Optional[str] = None


@router.post("/paymaster/configure")
async def configure_paymaster_key(
    key_request: PaymasterKeyRequest,
    request: Request,
    auth: AuthAdminDep,
) -> PaymasterKeyResponse:
    """
    Configure the Arka paymaster API key for gasless transactions.

    This key enables ERC-4337 sponsored transactions so users don't need ETH for gas.
    The key is stored securely and used for all subsequent transactions.
    """
    logger.info("[WALLET_PAYMASTER] Configuring paymaster key")

    try:
        # Validate key format (Etherspot keys start with specific prefixes)
        api_key = key_request.api_key.strip()
        if not api_key:
            return PaymasterKeyResponse(
                success=False,
                key_configured=False,
                error="API key cannot be empty",
            )

        # Basic validation - Etherspot keys have a specific format
        if not api_key.startswith("etherspot_"):
            logger.warning("[WALLET_PAYMASTER] Key doesn't match expected format")
            # Still allow it, but warn
            pass

        # Store in secrets service
        runtime = getattr(request.app.state, "runtime", None)
        if not runtime:
            return PaymasterKeyResponse(
                success=False,
                key_configured=False,
                error="Runtime not available",
            )

        # Store the key using secrets tool service
        secrets_tool = getattr(runtime, "secrets_tool_service", None)
        if secrets_tool:
            await secrets_tool.set_secret("arka_api_key", api_key, category="wallet")
            logger.info("[WALLET_PAYMASTER] Key stored via secrets tool service")
        else:
            # Fallback: try to store in config
            logger.warning("[WALLET_PAYMASTER] Secrets tool not available, trying config fallback")

            # Update the provider's paymaster config directly
            provider = _get_wallet_provider_from_app(request)
            if provider and hasattr(provider, "paymaster_config"):
                from pydantic import SecretStr

                provider.paymaster_config.arka_api_key = SecretStr(api_key)

                # Reinitialize Arka client with new key
                if hasattr(provider, "_arka_client") and provider._arka_client:
                    chain_id = provider._chain_client.chain_id
                    from ciris_adapters.wallet.providers.paymaster_client import ArkaClient

                    provider._arka_client = ArkaClient(
                        arka_url=provider.paymaster_config.arka_url,
                        api_key=api_key,
                        chain_id=chain_id,
                    )
                logger.info("[WALLET_PAYMASTER] Key stored in provider config")
            else:
                return PaymasterKeyResponse(
                    success=False,
                    key_configured=False,
                    error="No storage mechanism available for paymaster key",
                )

        return PaymasterKeyResponse(
            success=True,
            key_configured=True,
            message="Paymaster key configured successfully. Gasless transfers are now enabled.",
        )

    except Exception as e:
        logger.error(f"[WALLET_PAYMASTER] Error configuring key: {e}", exc_info=True)
        return PaymasterKeyResponse(
            success=False,
            key_configured=False,
            error=f"Failed to configure paymaster key: {str(e)}",
        )


@router.get("/paymaster/status")
async def get_paymaster_status(
    request: Request,
    auth: AuthDep,
) -> PaymasterKeyResponse:
    """
    Get the current paymaster configuration status.

    Returns whether a paymaster key is configured without exposing the key itself.
    """
    logger.info("[WALLET_PAYMASTER] Checking paymaster status")

    try:
        provider = _get_wallet_provider_from_app(request)

        if not provider:
            return PaymasterKeyResponse(
                success=True,
                key_configured=False,
                message="Wallet provider not available",
            )

        # Check if key is configured
        key_configured = False
        if hasattr(provider, "_get_arka_api_key"):
            key = provider._get_arka_api_key()
            key_configured = key is not None and len(key) > 0
        elif hasattr(provider, "paymaster_config") and provider.paymaster_config:
            if provider.paymaster_config.arka_api_key:
                key_configured = True

        # Check if paymaster is enabled in config
        paymaster_enabled = False
        if hasattr(provider, "paymaster_config") and provider.paymaster_config:
            paymaster_enabled = getattr(provider.paymaster_config, "enabled", False)

        message = None
        if paymaster_enabled and key_configured:
            message = "Gasless transfers enabled"
        elif paymaster_enabled and not key_configured:
            message = "Paymaster enabled but no API key configured"
        else:
            message = "Paymaster not enabled - ETH required for gas"

        return PaymasterKeyResponse(
            success=True,
            key_configured=key_configured,
            message=message,
        )

    except Exception as e:
        logger.error(f"[WALLET_PAYMASTER] Error checking status: {e}", exc_info=True)
        return PaymasterKeyResponse(
            success=False,
            key_configured=False,
            error=f"Failed to check paymaster status: {str(e)}",
        )
