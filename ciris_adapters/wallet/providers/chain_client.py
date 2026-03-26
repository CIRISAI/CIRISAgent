"""
Blockchain RPC Client for Base L2.

Provides lightweight JSON-RPC calls for balance queries and transaction submission.
No heavy Web3.py dependency - just httpx for RPC calls.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional, TypedDict, cast

import httpx

logger = logging.getLogger(__name__)


class ChainConfigEntry(TypedDict):
    """Type definition for chain configuration entries."""
    chain_id: int
    rpc_url: str
    usdc_address: str
    explorer: str


# Base L2 chain configuration
CHAIN_CONFIG: Dict[str, ChainConfigEntry] = {
    "base-mainnet": {
        "chain_id": 8453,
        "rpc_url": "https://mainnet.base.org",
        "usdc_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # Base USDC
        "explorer": "https://basescan.org",
    },
    "base-sepolia": {
        "chain_id": 84532,
        "rpc_url": "https://sepolia.base.org",
        "usdc_address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # Base Sepolia USDC
        "explorer": "https://sepolia.basescan.org",
    },
}

# ERC-20 balanceOf function selector: keccak256("balanceOf(address)")[:4]
BALANCE_OF_SELECTOR = "0x70a08231"

# USDC has 6 decimals
USDC_DECIMALS = 6


class ChainClient:
    """Lightweight JSON-RPC client for Base L2 blockchain queries."""

    def __init__(
        self,
        network: str = "base-mainnet",
        rpc_url: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        """
        Initialize the chain client.

        Args:
            network: Network name (base-mainnet, base-sepolia)
            rpc_url: Optional custom RPC URL (overrides default)
            timeout: HTTP request timeout in seconds
        """
        self.network = network
        config = CHAIN_CONFIG.get(network, CHAIN_CONFIG["base-mainnet"])
        self.chain_id: int = config["chain_id"]
        self.rpc_url: str = rpc_url or config["rpc_url"]
        self.usdc_address: str = config["usdc_address"]
        self.explorer: str = config["explorer"]
        self.timeout = timeout
        self._request_id = 0

        logger.info(f"ChainClient initialized for {network} (chain_id={self.chain_id})")

    def _next_id(self) -> int:
        """Get next JSON-RPC request ID."""
        self._request_id += 1
        return self._request_id

    async def _rpc_call(self, method: str, params: list[Any]) -> Any:
        """
        Make a JSON-RPC call to the blockchain node.

        Args:
            method: RPC method name (e.g., 'eth_call', 'eth_getBalance')
            params: Method parameters

        Returns:
            Result from RPC response

        Raises:
            Exception on RPC error
        """
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                error = data["error"]
                raise Exception(f"RPC error {error.get('code')}: {error.get('message')}")

            return data.get("result")

    async def get_eth_balance(self, address: str) -> Decimal:
        """
        Get ETH balance for an address.

        Args:
            address: EVM address (0x...)

        Returns:
            Balance in ETH (Decimal)
        """
        try:
            result = await self._rpc_call("eth_getBalance", [address, "latest"])
            # Result is hex string, convert to wei then to ETH
            wei = int(result, 16)
            eth = Decimal(wei) / Decimal(10**18)
            logger.debug(f"[ChainClient] ETH balance for {address}: {eth}")
            return eth
        except Exception as e:
            logger.error(f"[ChainClient] Failed to get ETH balance: {e}")
            return Decimal("0")

    async def get_usdc_balance(self, address: str) -> Decimal:
        """
        Get USDC balance for an address.

        Args:
            address: EVM address (0x...)

        Returns:
            Balance in USDC (Decimal, 6 decimals)
        """
        try:
            # Encode balanceOf(address) call
            # Selector (4 bytes) + address padded to 32 bytes
            padded_address = address.lower().replace("0x", "").zfill(64)
            call_data = f"{BALANCE_OF_SELECTOR}{padded_address}"

            result = await self._rpc_call(
                "eth_call",
                [
                    {"to": self.usdc_address, "data": call_data},
                    "latest",
                ],
            )

            # Result is hex string representing uint256
            raw_balance = int(result, 16)
            usdc = Decimal(raw_balance) / Decimal(10**USDC_DECIMALS)
            logger.debug(f"[ChainClient] USDC balance for {address}: {usdc}")
            return usdc
        except Exception as e:
            logger.error(f"[ChainClient] Failed to get USDC balance: {e}")
            return Decimal("0")

    async def get_transaction_receipt(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get transaction receipt by hash.

        Args:
            tx_hash: Transaction hash (0x...)

        Returns:
            Transaction receipt dict or None if not found/pending
        """
        try:
            result = await self._rpc_call("eth_getTransactionReceipt", [tx_hash])
            return cast(Optional[Dict[str, Any]], result)
        except Exception as e:
            logger.error(f"[ChainClient] Failed to get tx receipt: {e}")
            return None

    async def get_block_number(self) -> int:
        """Get current block number."""
        try:
            result = await self._rpc_call("eth_blockNumber", [])
            return int(result, 16)
        except Exception as e:
            logger.error(f"[ChainClient] Failed to get block number: {e}")
            return 0

    async def send_raw_transaction(self, signed_tx: str) -> str:
        """
        Submit a signed transaction to the network.

        Args:
            signed_tx: Hex-encoded signed transaction (0x...)

        Returns:
            Transaction hash

        Raises:
            Exception on submission error
        """
        result = await self._rpc_call("eth_sendRawTransaction", [signed_tx])
        logger.info(f"[ChainClient] Transaction submitted: {result}")
        return cast(str, result)

    def get_explorer_url(self, tx_hash: str) -> str:
        """Get block explorer URL for a transaction."""
        return f"{self.explorer}/tx/{tx_hash}"
