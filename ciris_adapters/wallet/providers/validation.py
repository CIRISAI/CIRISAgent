"""
Wallet Validation Module.

Mission-Critical Safety Constraints (MDD):
- Protect user funds through rigorous input validation
- Prevent accidental fund loss through dust/zero/negative checks
- Ensure cryptographic correctness via EIP-55 checksum validation
- Enforce spending limits to prevent unauthorized large transfers
- Detect and prevent duplicate transactions

This module embeds the wallet's safety mission directly into the validation logic,
making it impossible to bypass safety checks without explicitly overriding them.
"""

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Set

from .chain_client import keccak256

logger = logging.getLogger(__name__)


# =============================================================================
# Mission Constants
# =============================================================================

# Minimum transaction amounts (dust thresholds) by currency
DUST_THRESHOLDS: Dict[str, Decimal] = {
    "USDC": Decimal("0.01"),  # 1 cent minimum
    "ETH": Decimal("0.0001"),  # ~$0.20 at $2000/ETH
}

# Gas requirements for transaction types
GAS_REQUIREMENTS: Dict[str, int] = {
    "eth_transfer": 21000,
    "erc20_transfer": 65000,
}

# Maximum gas price multiplier (reject if gas is absurdly high)
MAX_GAS_PRICE_GWEI = 500  # 500 gwei is extreme even for Ethereum mainnet

# Default spending limits (can be overridden by attestation level)
DEFAULT_MAX_TRANSACTION = Decimal("100.00")
DEFAULT_DAILY_LIMIT = Decimal("1000.00")
DEFAULT_SESSION_LIMIT = Decimal("500.00")

# Transaction deduplication window (seconds)
DUPLICATE_WINDOW_SECONDS = 300  # 5 minutes


# =============================================================================
# Validation Errors
# =============================================================================


@dataclass
class ValidationError:
    """Validation error with code and message."""

    code: str
    message: str
    field: Optional[str] = None

    def __str__(self) -> str:
        if self.field:
            return f"[{self.code}] {self.field}: {self.message}"
        return f"[{self.code}] {self.message}"


@dataclass
class ValidationResult:
    """Result of validation with errors list."""

    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, code: str, message: str, field: Optional[str] = None) -> None:
        """Add an error and mark as invalid."""
        self.errors.append(ValidationError(code=code, message=message, field=field))
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning (doesn't affect validity)."""
        self.warnings.append(message)

    def error_message(self) -> str:
        """Get combined error message."""
        return "; ".join(str(e) for e in self.errors)


# =============================================================================
# EIP-55 Checksum Validation
# =============================================================================


def compute_checksum_address(address: str) -> str:
    """
    Compute EIP-55 checksummed address.

    Args:
        address: Raw hex address (with or without 0x prefix)

    Returns:
        Checksummed address with 0x prefix
    """
    # Normalize: lowercase, no prefix
    address_lower = address.lower().replace("0x", "")

    # Compute keccak256 hash of the lowercase hex string
    # NOTE: Must use keccak256, NOT sha3_256 - they have different padding!
    hash_bytes = keccak256(address_lower.encode("ascii"))

    # Build checksummed address
    result = "0x"
    for i, char in enumerate(address_lower):
        if char in "0123456789":
            result += char
        else:
            # Check the corresponding nibble in the hash
            nibble = hash_bytes[i // 2]
            if i % 2 == 0:
                nibble = nibble >> 4
            else:
                nibble = nibble & 0x0F

            if nibble >= 8:
                result += char.upper()
            else:
                result += char

    return result


def validate_eip55_checksum(address: str) -> bool:
    """
    Validate that an address has correct EIP-55 checksum.

    Args:
        address: Address to validate (must have 0x prefix)

    Returns:
        True if checksum is valid or address is all lowercase/uppercase
    """
    if not address.startswith("0x") or len(address) != 42:
        return False

    # Extract hex part
    hex_part = address[2:]

    # If all lowercase or all uppercase, checksum doesn't apply
    if hex_part.islower() or hex_part.isupper():
        return True

    # Mixed case must match computed checksum
    expected = compute_checksum_address(address)
    return address == expected


def is_zero_address(address: str) -> bool:
    """Check if address is the zero address."""
    return address.lower() == "0x" + "0" * 40


# =============================================================================
# Amount Validation
# =============================================================================


def validate_amount(
    amount: Decimal,
    currency: str,
    max_transaction: Optional[Decimal] = None,
) -> ValidationResult:
    """
    Validate transaction amount.

    Checks:
    - Not negative
    - Not zero
    - Above dust threshold
    - Below max transaction limit

    Args:
        amount: Transaction amount
        currency: Currency code (USDC, ETH)
        max_transaction: Maximum allowed transaction (None = use default)

    Returns:
        ValidationResult with any errors
    """
    result = ValidationResult(valid=True)

    # Check negative
    if amount < 0:
        result.add_error(code="NEGATIVE_AMOUNT", message=f"Amount cannot be negative: {amount}", field="amount")
        return result

    # Check zero
    if amount == 0:
        result.add_error(code="ZERO_AMOUNT", message="Amount cannot be zero", field="amount")
        return result

    # Check dust threshold
    dust_threshold = DUST_THRESHOLDS.get(currency.upper(), Decimal("0.01"))
    if amount < dust_threshold:
        result.add_error(
            code="DUST_AMOUNT",
            message=f"Amount {amount} {currency} below minimum {dust_threshold} {currency}",
            field="amount",
        )
        return result

    # Check max transaction
    max_tx = max_transaction or DEFAULT_MAX_TRANSACTION
    if amount > max_tx:
        result.add_error(
            code="EXCEEDS_MAX_TRANSACTION",
            message=f"Amount {amount} exceeds max transaction limit {max_tx}",
            field="amount",
        )

    return result


# =============================================================================
# Recipient Validation
# =============================================================================


def validate_recipient(address: str) -> ValidationResult:
    """
    Validate recipient EVM address.

    Checks:
    - Has 0x prefix
    - Is 42 characters (0x + 40 hex)
    - Contains only valid hex characters
    - Has valid EIP-55 checksum (if mixed case)
    - Is not the zero address

    Args:
        address: Recipient address

    Returns:
        ValidationResult with any errors
    """
    result = ValidationResult(valid=True)

    # Check prefix
    if not address.startswith("0x"):
        result.add_error(code="MISSING_PREFIX", message="Address must start with 0x", field="recipient")
        return result

    # Check length
    if len(address) != 42:
        result.add_error(
            code="INVALID_LENGTH", message=f"Address must be 42 characters, got {len(address)}", field="recipient"
        )
        return result

    # Check hex characters
    hex_part = address[2:]
    if not re.match(r"^[0-9a-fA-F]{40}$", hex_part):
        result.add_error(code="INVALID_HEX", message="Address contains invalid characters", field="recipient")
        return result

    # Check zero address
    if is_zero_address(address):
        result.add_error(
            code="ZERO_ADDRESS", message="Cannot send to zero address (would burn funds)", field="recipient"
        )
        return result

    # Check EIP-55 checksum
    if not validate_eip55_checksum(address):
        result.add_error(
            code="INVALID_CHECKSUM",
            message="Invalid EIP-55 checksum. Verify the address is correct.",
            field="recipient",
        )

    return result


# =============================================================================
# Gas Validation
# =============================================================================


def validate_gas(
    eth_balance: Decimal,
    gas_needed: int,
    gas_price: int,
    currency: str,
) -> ValidationResult:
    """
    Validate that sufficient ETH exists for gas.

    When gas_price is 0, this indicates a paymaster is sponsoring gas fees
    and validation is skipped. See FSD/WALLET_REGULATORY_COMPLIANCE.md Section 10.

    Args:
        eth_balance: Current ETH balance
        gas_needed: Estimated gas units needed
        gas_price: Current gas price in wei (0 = paymaster enabled)
        currency: Transaction currency (affects gas estimate)

    Returns:
        ValidationResult with any errors
    """
    result = ValidationResult(valid=True)

    # Skip gas validation when paymaster is enabled (gas_price=0)
    # Paymaster sponsors gas fees as infrastructure expense
    if gas_price == 0:
        logger.debug("[Validation] Paymaster enabled - skipping gas validation")
        return result

    # Calculate gas cost in ETH
    gas_cost_wei = gas_needed * gas_price
    gas_cost_eth = Decimal(gas_cost_wei) / Decimal(10**18)

    # Add 20% buffer for gas price fluctuation
    gas_with_buffer = gas_cost_eth * Decimal("1.2")

    if eth_balance < gas_with_buffer:
        result.add_error(
            code="INSUFFICIENT_GAS",
            message=f"Insufficient ETH for gas. Have: {eth_balance:.6f} ETH, need: ~{gas_with_buffer:.6f} ETH",
            field="eth_balance",
        )
        # Add helpful suggestion
        result.add_warning(f"Send at least {gas_with_buffer:.6f} ETH to this wallet address for gas.")

    # Check for absurdly high gas price
    gas_price_gwei = gas_price / 10**9
    if gas_price_gwei > MAX_GAS_PRICE_GWEI:
        result.add_error(
            code="GAS_PRICE_TOO_HIGH",
            message=f"Gas price {gas_price_gwei:.0f} gwei is abnormally high. Network may be congested.",
            field="gas_price",
        )

    return result


# =============================================================================
# Spending Limit Enforcement
# =============================================================================


@dataclass
class SpendingTracker:
    """
    Track spending for limit enforcement.

    Mission: Prevent unauthorized large transfers by enforcing
    daily and session limits.
    """

    daily_spent: Dict[str, Decimal] = field(default_factory=dict)  # currency -> amount
    session_spent: Dict[str, Decimal] = field(default_factory=dict)
    daily_reset_timestamp: float = field(default_factory=time.time)
    session_start_timestamp: float = field(default_factory=time.time)

    # Limits (can be adjusted per attestation level)
    daily_limit: Decimal = DEFAULT_DAILY_LIMIT
    session_limit: Decimal = DEFAULT_SESSION_LIMIT

    def _check_daily_reset(self) -> None:
        """Reset daily counters if new day."""
        now = time.time()
        # Reset if more than 24 hours since last reset
        if now - self.daily_reset_timestamp > 86400:
            self.daily_spent.clear()
            self.daily_reset_timestamp = now
            logger.info("[SpendingTracker] Daily spending reset")

    def _check_session_reset(self, session_timeout: float = 3600) -> None:
        """Reset session counters if session expired."""
        now = time.time()
        if now - self.session_start_timestamp > session_timeout:
            self.session_spent.clear()
            self.session_start_timestamp = now
            logger.info("[SpendingTracker] Session spending reset")

    def check_and_record(
        self,
        amount: Decimal,
        currency: str,
    ) -> ValidationResult:
        """
        Check if transaction is within limits and record if allowed.

        Args:
            amount: Transaction amount
            currency: Currency code

        Returns:
            ValidationResult with any limit violations
        """
        result = ValidationResult(valid=True)
        currency = currency.upper()

        # Check resets
        self._check_daily_reset()
        self._check_session_reset()

        # Get current totals
        daily_total = self.daily_spent.get(currency, Decimal("0"))
        session_total = self.session_spent.get(currency, Decimal("0"))

        # Check daily limit
        if daily_total + amount > self.daily_limit:
            result.add_error(
                code="DAILY_LIMIT_EXCEEDED",
                message=f"Daily limit exceeded. Spent: {daily_total}, limit: {self.daily_limit}",
                field="amount",
            )

        # Check session limit
        if session_total + amount > self.session_limit:
            result.add_error(
                code="SESSION_LIMIT_EXCEEDED",
                message=f"Session limit exceeded. Spent: {session_total}, limit: {self.session_limit}",
                field="amount",
            )

        # Record if valid
        if result.valid:
            self.daily_spent[currency] = daily_total + amount
            self.session_spent[currency] = session_total + amount
            logger.info(
                f"[SpendingTracker] Recorded {amount} {currency}. "
                f"Daily: {self.daily_spent[currency]}, Session: {self.session_spent[currency]}"
            )

        return result

    def get_remaining_daily(self, currency: str) -> Decimal:
        """Get remaining daily allowance."""
        self._check_daily_reset()
        spent = self.daily_spent.get(currency.upper(), Decimal("0"))
        return max(Decimal("0"), self.daily_limit - spent)

    def get_remaining_session(self, currency: str) -> Decimal:
        """Get remaining session allowance."""
        self._check_session_reset()
        spent = self.session_spent.get(currency.upper(), Decimal("0"))
        return max(Decimal("0"), self.session_limit - spent)


# =============================================================================
# Duplicate Transaction Protection
# =============================================================================


@dataclass
class DuplicateProtection:
    """
    Prevent duplicate transactions.

    Mission: Protect against accidental double-sends by tracking
    recent transactions and rejecting duplicates within a time window.
    """

    recent_transactions: Dict[str, float] = field(default_factory=dict)  # tx_hash -> timestamp
    window_seconds: float = DUPLICATE_WINDOW_SECONDS

    def _compute_tx_fingerprint(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
    ) -> str:
        """Compute fingerprint for a transaction."""
        # Normalize inputs
        data = f"{recipient.lower()}:{amount}:{currency.upper()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _cleanup_old(self) -> None:
        """Remove transactions outside the window."""
        now = time.time()
        cutoff = now - self.window_seconds
        self.recent_transactions = {k: v for k, v in self.recent_transactions.items() if v > cutoff}

    def check_duplicate(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
    ) -> ValidationResult:
        """
        Check if this is a duplicate transaction.

        Args:
            recipient: Recipient address
            amount: Transaction amount
            currency: Currency code

        Returns:
            ValidationResult with error if duplicate
        """
        result = ValidationResult(valid=True)

        self._cleanup_old()

        fingerprint = self._compute_tx_fingerprint(recipient, amount, currency)

        if fingerprint in self.recent_transactions:
            elapsed = time.time() - self.recent_transactions[fingerprint]
            result.add_error(
                code="DUPLICATE_TRANSACTION",
                message=f"Duplicate transaction detected ({elapsed:.0f}s ago). "
                f"Same recipient, amount, and currency within {self.window_seconds}s window.",
                field="transaction",
            )

        return result

    def record_transaction(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
    ) -> None:
        """Record a transaction to prevent future duplicates."""
        fingerprint = self._compute_tx_fingerprint(recipient, amount, currency)
        self.recent_transactions[fingerprint] = time.time()
        logger.debug(f"[DuplicateProtection] Recorded tx fingerprint: {fingerprint}")


# =============================================================================
# Combined Validator
# =============================================================================


class WalletValidator:
    """
    Combined wallet validator with all safety checks.

    Mission: Ensure every transaction passes all safety checks before
    being signed and broadcast. This is the last line of defense.
    """

    def __init__(
        self,
        max_transaction: Optional[Decimal] = None,
        daily_limit: Optional[Decimal] = None,
        session_limit: Optional[Decimal] = None,
    ):
        """Initialize validator with limits."""
        self.max_transaction = max_transaction or DEFAULT_MAX_TRANSACTION

        self.spending_tracker = SpendingTracker(
            daily_limit=daily_limit or DEFAULT_DAILY_LIMIT,
            session_limit=session_limit or DEFAULT_SESSION_LIMIT,
        )

        self.duplicate_protection = DuplicateProtection()

    def update_limits_from_attestation(
        self,
        max_transaction: Decimal,
        daily_limit: Decimal,
    ) -> None:
        """Update limits based on attestation level."""
        self.max_transaction = max_transaction
        self.spending_tracker.daily_limit = daily_limit
        logger.info(f"[WalletValidator] Limits updated: max_tx={max_transaction}, daily={daily_limit}")

    def validate_send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        eth_balance: Decimal,
        gas_price: int,
    ) -> ValidationResult:
        """
        Validate a send transaction with all safety checks.

        Args:
            recipient: Recipient address
            amount: Transaction amount
            currency: Currency code
            eth_balance: Current ETH balance for gas check
            gas_price: Current gas price in wei

        Returns:
            ValidationResult with all errors and warnings
        """
        result = ValidationResult(valid=True)

        # 1. Validate recipient address
        recipient_result = validate_recipient(recipient)
        if not recipient_result.valid:
            result.errors.extend(recipient_result.errors)
            result.valid = False
        result.warnings.extend(recipient_result.warnings)

        # 2. Validate amount
        amount_result = validate_amount(amount, currency, self.max_transaction)
        if not amount_result.valid:
            result.errors.extend(amount_result.errors)
            result.valid = False
        result.warnings.extend(amount_result.warnings)

        # 3. Check gas (only if amount is valid to avoid confusing errors)
        if result.valid:
            gas_needed = GAS_REQUIREMENTS.get("erc20_transfer" if currency.upper() == "USDC" else "eth_transfer", 65000)
            gas_result = validate_gas(eth_balance, gas_needed, gas_price, currency)
            if not gas_result.valid:
                result.errors.extend(gas_result.errors)
                result.valid = False
            result.warnings.extend(gas_result.warnings)

        # 4. Check for duplicate
        dup_result = self.duplicate_protection.check_duplicate(recipient, amount, currency)
        if not dup_result.valid:
            result.errors.extend(dup_result.errors)
            result.valid = False

        # 5. Check spending limits (only if all other checks pass)
        if result.valid:
            limit_result = self.spending_tracker.check_and_record(amount, currency)
            if not limit_result.valid:
                result.errors.extend(limit_result.errors)
                result.valid = False

        return result

    def record_successful_send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
    ) -> None:
        """Record a successful send for duplicate protection."""
        self.duplicate_protection.record_transaction(recipient, amount, currency)
