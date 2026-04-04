"""
Coinbase Paymaster Client for ERC-4337 Gas Sponsorship.

Uses Coinbase Developer Platform (CDP) for gas sponsorship on Base.
Part of the Commons Credits system - see FSD/COMMONS_CREDITS.md

Key benefits over self-hosted Arka:
- Regulated US entity handles sponsorship (compliance)
- Native contract allowlisting support
- $10k/month free tier on Base
- 7% fee on mainnet (paid from sponsored amounts)

References:
- CDP Docs: https://docs.cdp.coinbase.com/
- Paymaster: https://docs.cdp.coinbase.com/paymaster/docs/welcome
"""

import hashlib
import hmac
import logging
import time
from decimal import Decimal
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field

from .paymaster_client import SponsorshipResult, UserOperation

logger = logging.getLogger(__name__)


class CoinbasePaymasterConfig(BaseModel):
    """Configuration for Coinbase Paymaster."""

    enabled: bool = Field(
        default=False,
        description="Enable Coinbase Paymaster for gas sponsorship",
    )
    api_key_name: Optional[str] = Field(
        None,
        description="Coinbase CDP API key name",
    )
    api_key_secret: Optional[str] = Field(
        None,
        description="Coinbase CDP API key secret (keep secure!)",
    )
    base_url: str = Field(
        default="https://api.developer.coinbase.com/rpc/v1/base",
        description="Coinbase RPC endpoint for Base",
    )
    timeout: float = Field(
        default=30.0,
        description="Request timeout in seconds",
    )


class CoinbasePaymaster:
    """
    Client for Coinbase Developer Platform Paymaster service.

    Sponsors gas fees for UserOperations on Base, allowing users
    to transact without holding ETH.
    """

    # EntryPoint v0.6 on Base
    ENTRY_POINT_V06 = "0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789"

    def __init__(self, config: CoinbasePaymasterConfig):
        """
        Initialize Coinbase Paymaster client.

        Args:
            config: Coinbase CDP configuration
        """
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate configuration."""
        if self.config.enabled:
            if not self.config.api_key_name:
                raise ValueError("Coinbase API key name required when enabled")
            if not self.config.api_key_secret:
                raise ValueError("Coinbase API key secret required when enabled")

    def _build_auth_headers(self, body: str) -> dict[str, str]:
        """
        Build JWT authentication headers for Coinbase CDP.

        Uses ES256 JWT signing as per CDP docs.
        For simplicity, we use the API key directly in header.
        Production should use proper JWT signing.
        """
        # Simple API key auth (CDP supports this for server-to-server)
        timestamp = str(int(time.time()))
        message = f"{timestamp}.{body}"

        # HMAC signature
        signature = hmac.new(
            self.config.api_key_secret.encode() if self.config.api_key_secret else b"",
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        return {
            "Content-Type": "application/json",
            "X-CDP-API-Key": self.config.api_key_name or "",
            "X-CDP-Timestamp": timestamp,
            "X-CDP-Signature": signature,
        }

    async def sponsor(
        self,
        user_op: UserOperation,
        entry_point: Optional[str] = None,
    ) -> SponsorshipResult:
        """
        Request gas sponsorship from Coinbase Paymaster.

        The transaction must pass Coinbase's configured policies:
        - Contract allowlist (we configure for USDC only)
        - Global budget limits

        Args:
            user_op: The UserOperation to sponsor
            entry_point: EntryPoint address (defaults to v0.6)

        Returns:
            SponsorshipResult with paymasterAndData

        Raises:
            PaymasterError: If sponsorship request fails
        """
        if not self.config.enabled:
            raise PaymasterError("Coinbase Paymaster is not enabled")

        entry_point = entry_point or self.ENTRY_POINT_V06

        # Build JSON-RPC payload
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "pm_sponsorUserOperation",
            "params": [
                user_op.to_bundler_dict(),
                entry_point,
            ],
        }

        import json
        body = json.dumps(payload)
        headers = self._build_auth_headers(body)

        logger.debug(f"[CoinbasePaymaster] Requesting sponsorship for sender={user_op.sender}")

        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                self.config.base_url,
                content=body,
                headers=headers,
            )

            if response.status_code != 200:
                raise PaymasterError(
                    f"Coinbase request failed: {response.status_code} - {response.text}"
                )

            result = response.json()

            if "error" in result:
                error = result["error"]
                error_msg = error.get("message", str(error))
                raise PaymasterError(f"Coinbase sponsorship failed: {error_msg}")

            data = result.get("result", {})

            if not data.get("paymasterAndData"):
                raise PaymasterError("Coinbase returned empty paymasterAndData")

            logger.info(
                f"[CoinbasePaymaster] Sponsorship approved for sender={user_op.sender}"
            )

            return SponsorshipResult(
                paymaster_and_data=data.get("paymasterAndData", "0x"),
                pre_verification_gas=data.get("preVerificationGas"),
                verification_gas_limit=data.get("verificationGasLimit"),
                call_gas_limit=data.get("callGasLimit"),
            )

    async def get_paymaster_data(
        self,
        user_op: UserOperation,
        entry_point: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get full paymaster data including gas estimates.

        This is a convenience method that returns the raw response
        for debugging or advanced use cases.
        """
        result = await self.sponsor(user_op, entry_point)
        return {
            "paymasterAndData": result.paymaster_and_data,
            "preVerificationGas": result.pre_verification_gas,
            "verificationGasLimit": result.verification_gas_limit,
            "callGasLimit": result.call_gas_limit,
        }

    async def estimate_gas_cost_usd(
        self,
        user_op: UserOperation,
        eth_price_usd: Decimal = Decimal("3000"),
        gas_price_gwei: Decimal = Decimal("0.01"),
    ) -> Decimal:
        """
        Estimate gas cost in USD for a UserOperation.

        This is used by sponsorship policy to check budget.
        Base L2 gas is very cheap (~$0.001 per tx).

        Args:
            user_op: UserOperation to estimate
            eth_price_usd: Current ETH price
            gas_price_gwei: Current gas price on Base

        Returns:
            Estimated gas cost in USD
        """
        # Parse gas limits from UserOp
        call_gas = int(user_op.call_gas_limit, 16) if user_op.call_gas_limit else 100000
        verification_gas = int(user_op.verification_gas_limit, 16) if user_op.verification_gas_limit else 100000
        pre_verification_gas = int(user_op.pre_verification_gas, 16) if user_op.pre_verification_gas else 50000

        total_gas = call_gas + verification_gas + pre_verification_gas

        # Gas cost in ETH
        gas_price_eth = gas_price_gwei / Decimal("1000000000")  # gwei to ETH
        gas_cost_eth = Decimal(total_gas) * gas_price_eth

        # Convert to USD
        gas_cost_usd = gas_cost_eth * eth_price_usd

        return gas_cost_usd.quantize(Decimal("0.0001"))


class PaymasterError(Exception):
    """Error from Coinbase Paymaster service."""
    pass


# =============================================================================
# Factory function for paymaster selection
# =============================================================================


async def get_paymaster_sponsorship(
    user_op: UserOperation,
    provider: str = "coinbase",
    coinbase_config: Optional[CoinbasePaymasterConfig] = None,
    arka_url: Optional[str] = None,
    arka_api_key: Optional[str] = None,
    chain_id: int = 8453,
) -> SponsorshipResult:
    """
    Get gas sponsorship from configured paymaster provider.

    Args:
        user_op: UserOperation to sponsor
        provider: "coinbase" or "arka"
        coinbase_config: Config for Coinbase (if using coinbase)
        arka_url: URL for Arka (if using arka)
        arka_api_key: API key for Arka (if using arka)
        chain_id: Chain ID (8453 for Base mainnet)

    Returns:
        SponsorshipResult with paymasterAndData

    Raises:
        PaymasterError: If sponsorship fails
    """
    if provider == "coinbase":
        if not coinbase_config:
            raise PaymasterError("Coinbase config required for coinbase provider")
        paymaster = CoinbasePaymaster(coinbase_config)
        return await paymaster.sponsor(user_op)

    elif provider == "arka":
        # Use existing Arka client
        from .paymaster_client import ArkaClient

        client = ArkaClient(
            arka_url=arka_url or "https://arka.etherspot.io",
            api_key=arka_api_key,
            chain_id=chain_id,
        )
        return await client.sponsor(
            user_op,
            entry_point="0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789",
        )

    else:
        raise PaymasterError(f"Unknown paymaster provider: {provider}")
