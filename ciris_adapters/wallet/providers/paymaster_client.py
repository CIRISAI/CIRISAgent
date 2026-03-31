"""
ERC-4337 Paymaster and Bundler Client.

Minimal Python implementation for gas-sponsored transactions using:
- Etherspot Arka (MIT licensed paymaster service)
- ERC-4337 bundler JSON-RPC API

Regulatory Note: Gas sponsorship is infrastructure expense, not money transmission.
See FSD/WALLET_REGULATORY_COMPLIANCE.md Section 10.

References:
- ERC-4337: https://eips.ethereum.org/EIPS/eip-4337
- ERC-7769 (Bundler API): https://eips.ethereum.org/EIPS/eip-7769
- Arka: https://github.com/etherspot/arka
"""

import logging
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# UserOperation Schema (ERC-4337 v0.6)
# =============================================================================


class UserOperation(BaseModel):
    """
    ERC-4337 UserOperation for account abstraction.

    This represents a pseudo-transaction that gets submitted to a bundler
    instead of directly to the network.
    """

    sender: str = Field(..., description="Smart account address")
    nonce: str = Field(..., description="Anti-replay nonce (hex)")
    init_code: str = Field(
        default="0x",
        alias="initCode",
        description="Account factory + init data (0x if account exists)",
    )
    call_data: str = Field(
        ...,
        alias="callData",
        description="Encoded call to execute",
    )
    call_gas_limit: str = Field(
        ...,
        alias="callGasLimit",
        description="Gas for the main execution (hex)",
    )
    verification_gas_limit: str = Field(
        ...,
        alias="verificationGasLimit",
        description="Gas for verification (hex)",
    )
    pre_verification_gas: str = Field(
        ...,
        alias="preVerificationGas",
        description="Gas for bundler overhead (hex)",
    )
    max_fee_per_gas: str = Field(
        ...,
        alias="maxFeePerGas",
        description="Maximum fee per gas (hex)",
    )
    max_priority_fee_per_gas: str = Field(
        ...,
        alias="maxPriorityFeePerGas",
        description="Maximum priority fee (hex)",
    )
    paymaster_and_data: str = Field(
        default="0x",
        alias="paymasterAndData",
        description="Paymaster address + data (0x if self-paying)",
    )
    signature: str = Field(
        default="0x",
        description="UserOp signature from account owner",
    )

    class Config:
        populate_by_name = True

    def to_bundler_dict(self) -> dict[str, str]:
        """Convert to bundler-compatible dict with camelCase keys."""
        return {
            "sender": self.sender,
            "nonce": self.nonce,
            "initCode": self.init_code,
            "callData": self.call_data,
            "callGasLimit": self.call_gas_limit,
            "verificationGasLimit": self.verification_gas_limit,
            "preVerificationGas": self.pre_verification_gas,
            "maxFeePerGas": self.max_fee_per_gas,
            "maxPriorityFeePerGas": self.max_priority_fee_per_gas,
            "paymasterAndData": self.paymaster_and_data,
            "signature": self.signature,
        }


class UserOperationReceipt(BaseModel):
    """Receipt returned after UserOperation execution."""

    user_op_hash: str = Field(..., alias="userOpHash")
    sender: str
    nonce: str
    success: bool
    actual_gas_used: str = Field(..., alias="actualGasUsed")
    actual_gas_cost: str = Field(..., alias="actualGasCost")
    receipt: dict[str, Any] = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class SponsorshipResult(BaseModel):
    """Result from paymaster sponsorship request."""

    paymaster_and_data: str = Field(..., alias="paymasterAndData")
    pre_verification_gas: Optional[str] = Field(None, alias="preVerificationGas")
    verification_gas_limit: Optional[str] = Field(None, alias="verificationGasLimit")
    call_gas_limit: Optional[str] = Field(None, alias="callGasLimit")

    class Config:
        populate_by_name = True


class GasEstimate(BaseModel):
    """Gas estimates from bundler."""

    pre_verification_gas: str = Field(..., alias="preVerificationGas")
    verification_gas_limit: str = Field(..., alias="verificationGasLimit")
    call_gas_limit: str = Field(..., alias="callGasLimit")

    class Config:
        populate_by_name = True


# =============================================================================
# Arka Paymaster Client
# =============================================================================


class ArkaClient:
    """
    Client for Etherspot Arka paymaster service.

    Arka sponsors gas fees for UserOperations, allowing users to transact
    without holding ETH for gas.
    """

    def __init__(
        self,
        arka_url: str = "https://arka.etherspot.io",
        api_key: Optional[str] = None,
        chain_id: int = 8453,  # Base mainnet
        timeout: float = 30.0,
    ):
        """
        Initialize Arka client.

        Args:
            arka_url: Arka service URL (or self-hosted instance)
            api_key: API key for hosted service (optional for self-hosted)
            chain_id: Target chain ID (8453 for Base mainnet)
            timeout: Request timeout in seconds
        """
        self.arka_url = arka_url.rstrip("/")
        self.api_key = api_key
        self.chain_id = chain_id
        self.timeout = timeout

    async def sponsor(
        self,
        user_op: UserOperation,
        entry_point: str,
    ) -> SponsorshipResult:
        """
        Request gas sponsorship for a UserOperation.

        Args:
            user_op: The UserOperation to sponsor
            entry_point: EntryPoint contract address

        Returns:
            SponsorshipResult with paymasterAndData to include in UserOp

        Raises:
            PaymasterError: If sponsorship request fails
        """
        # Build request payload
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "pm_sponsorUserOperation",
            "params": [
                user_op.to_bundler_dict(),
                entry_point,
                {"mode": "sponsor"},
            ],
        }

        # Build URL with API key if provided
        url = f"{self.arka_url}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        # Add chain ID as query param
        url = f"{url}?chainId={self.chain_id}"

        logger.debug(f"[Arka] Requesting sponsorship for sender={user_op.sender}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code != 200:
                raise PaymasterError(
                    f"Arka request failed: {response.status_code} - {response.text}"
                )

            result = response.json()

            if "error" in result:
                error = result["error"]
                raise PaymasterError(
                    f"Arka sponsorship failed: {error.get('message', error)}"
                )

            data = result.get("result", {})
            logger.info(f"[Arka] Sponsorship approved for sender={user_op.sender}")

            return SponsorshipResult(
                paymaster_and_data=data.get("paymasterAndData", "0x"),
                pre_verification_gas=data.get("preVerificationGas"),
                verification_gas_limit=data.get("verificationGasLimit"),
                call_gas_limit=data.get("callGasLimit"),
            )

    async def check_whitelist(self, address: str) -> bool:
        """Check if an address is whitelisted for sponsorship."""
        url = f"{self.arka_url}/whitelist/{address}?chainId={self.chain_id}"
        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                result = response.json()
                return bool(result.get("whitelisted", False))
            return False


# =============================================================================
# Bundler Client
# =============================================================================


class BundlerClient:
    """
    Client for ERC-4337 bundler JSON-RPC API.

    Bundlers collect UserOperations and submit them on-chain via
    the EntryPoint contract.
    """

    def __init__(
        self,
        bundler_url: str = "https://bundler.etherspot.io/8453",
        entry_point: str = "0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789",
        timeout: float = 60.0,
    ):
        """
        Initialize bundler client.

        Args:
            bundler_url: Bundler JSON-RPC URL
            entry_point: EntryPoint contract address (v0.6)
            timeout: Request timeout in seconds
        """
        self.bundler_url = bundler_url
        self.entry_point = entry_point
        self.timeout = timeout
        self._request_id = 0

    def _next_id(self) -> int:
        """Get next JSON-RPC request ID."""
        self._request_id += 1
        return self._request_id

    async def _rpc_call(
        self,
        method: str,
        params: list[Any],
    ) -> Any:
        """Make JSON-RPC call to bundler."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.bundler_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code != 200:
                raise BundlerError(
                    f"Bundler request failed: {response.status_code} - {response.text}"
                )

            result = response.json()

            if "error" in result:
                error = result["error"]
                raise BundlerError(
                    f"Bundler RPC error: {error.get('message', error)}"
                )

            return result.get("result")

    async def estimate_user_operation_gas(
        self,
        user_op: UserOperation,
    ) -> GasEstimate:
        """
        Estimate gas for a UserOperation.

        Args:
            user_op: The UserOperation to estimate

        Returns:
            GasEstimate with gas limits
        """
        logger.debug(f"[Bundler] Estimating gas for sender={user_op.sender}")

        result = await self._rpc_call(
            "eth_estimateUserOperationGas",
            [user_op.to_bundler_dict(), self.entry_point],
        )

        return GasEstimate(
            pre_verification_gas=result.get("preVerificationGas", "0x0"),
            verification_gas_limit=result.get("verificationGasLimit", "0x0"),
            call_gas_limit=result.get("callGasLimit", "0x0"),
        )

    async def send_user_operation(
        self,
        user_op: UserOperation,
    ) -> str:
        """
        Submit a signed UserOperation to the bundler.

        Args:
            user_op: The signed UserOperation

        Returns:
            UserOperation hash (userOpHash)
        """
        logger.info(f"[Bundler] Sending UserOp for sender={user_op.sender}")

        result = await self._rpc_call(
            "eth_sendUserOperation",
            [user_op.to_bundler_dict(), self.entry_point],
        )

        if isinstance(result, str):
            logger.info(f"[Bundler] UserOp submitted: {result}")
            return result

        raise BundlerError(f"Unexpected response from bundler: {result}")

    async def get_user_operation_receipt(
        self,
        user_op_hash: str,
    ) -> Optional[UserOperationReceipt]:
        """
        Get receipt for a submitted UserOperation.

        Args:
            user_op_hash: The userOpHash from send_user_operation

        Returns:
            UserOperationReceipt if found, None if pending
        """
        result = await self._rpc_call(
            "eth_getUserOperationReceipt",
            [user_op_hash],
        )

        if result is None:
            return None

        return UserOperationReceipt(
            user_op_hash=result.get("userOpHash", user_op_hash),
            sender=result.get("sender", ""),
            nonce=result.get("nonce", "0x0"),
            success=result.get("success", False),
            actual_gas_used=result.get("actualGasUsed", "0x0"),
            actual_gas_cost=result.get("actualGasCost", "0x0"),
            receipt=result.get("receipt", {}),
        )

    async def get_supported_entry_points(self) -> list[str]:
        """Get EntryPoint addresses supported by this bundler."""
        result = await self._rpc_call("eth_supportedEntryPoints", [])
        return result if isinstance(result, list) else []

    async def wait_for_receipt(
        self,
        user_op_hash: str,
        timeout_seconds: float = 120.0,
        poll_interval: float = 2.0,
    ) -> UserOperationReceipt:
        """
        Wait for UserOperation to be included on-chain.

        Args:
            user_op_hash: The userOpHash to wait for
            timeout_seconds: Maximum time to wait
            poll_interval: Time between polls

        Returns:
            UserOperationReceipt once included

        Raises:
            BundlerError: If timeout exceeded or operation failed
        """
        import asyncio

        elapsed = 0.0
        while elapsed < timeout_seconds:
            receipt = await self.get_user_operation_receipt(user_op_hash)
            if receipt is not None:
                if not receipt.success:
                    raise BundlerError(
                        f"UserOperation failed on-chain: {user_op_hash}"
                    )
                return receipt

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise BundlerError(
            f"Timeout waiting for UserOperation receipt: {user_op_hash}"
        )


# =============================================================================
# Errors
# =============================================================================


class PaymasterError(Exception):
    """Error from paymaster service."""

    pass


class BundlerError(Exception):
    """Error from bundler service."""

    pass


# =============================================================================
# Helper Functions
# =============================================================================


def hex_int(value: int) -> str:
    """Convert int to hex string."""
    return hex(value)


def int_from_hex(value: str) -> int:
    """Convert hex string to int."""
    return int(value, 16)
