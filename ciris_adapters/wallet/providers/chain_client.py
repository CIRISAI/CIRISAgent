"""
Blockchain RPC Client for Base L2.

Provides lightweight JSON-RPC calls for balance queries, transaction building,
and submission. No heavy Web3.py dependency - just httpx for RPC calls.

Transaction Flow:
1. get_nonce() - Get account nonce
2. get_gas_price() - Get current gas price
3. build_erc20_transfer() - Build ERC-20 transfer calldata
4. hash_transaction() - RLP encode and hash unsigned tx
5. Sign tx_hash with CIRISVerify (external)
6. encode_signed_transaction() - Add signature to tx
7. send_raw_transaction() - Broadcast to network
"""

import hashlib
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, TypedDict, Union, cast

import httpx

logger = logging.getLogger(__name__)


def keccak256(data: bytes) -> bytes:
    """Compute Keccak-256 hash (Ethereum's hash function)."""
    # Python 3.11+ has native keccak support via hashlib
    try:
        result: bytes = hashlib.new("sha3_256", data).digest()
        return result
    except ValueError:
        # Fallback: use pysha3 if available
        try:
            import sha3
            result = sha3.keccak_256(data).digest()
            return bytes(result)
        except ImportError:
            # Last resort: use PyCryptodome
            try:
                from Crypto.Hash import keccak
                result = keccak.new(data=data, digest_bits=256).digest()
                return bytes(result)
            except ImportError:
                raise ImportError(
                    "No keccak256 implementation available. "
                    "Install pysha3 or pycryptodome."
                )


def rlp_encode(item: Union[bytes, List[Any], int]) -> bytes:
    """
    Minimal RLP encoder for Ethereum transactions.

    Supports:
    - bytes (strings)
    - lists
    - integers (converted to bytes)
    """
    if isinstance(item, int):
        if item == 0:
            item = b""
        else:
            # Convert int to big-endian bytes, stripping leading zeros
            item = item.to_bytes((item.bit_length() + 7) // 8, "big")

    if isinstance(item, bytes):
        if len(item) == 1 and item[0] < 0x80:
            return item
        elif len(item) < 56:
            return bytes([0x80 + len(item)]) + item
        else:
            len_bytes = _encode_length(len(item))
            return bytes([0xb7 + len(len_bytes)]) + len_bytes + item

    elif isinstance(item, list):
        encoded_items = b"".join(rlp_encode(i) for i in item)
        if len(encoded_items) < 56:
            return bytes([0xc0 + len(encoded_items)]) + encoded_items
        else:
            len_bytes = _encode_length(len(encoded_items))
            return bytes([0xf7 + len(len_bytes)]) + len_bytes + encoded_items

    raise TypeError(f"Cannot RLP encode type: {type(item)}")


def _encode_length(length: int) -> bytes:
    """Encode length as big-endian bytes."""
    return length.to_bytes((length.bit_length() + 7) // 8, "big")


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

# ERC-20 function selectors
BALANCE_OF_SELECTOR = "0x70a08231"  # keccak256("balanceOf(address)")[:4]
TRANSFER_SELECTOR = "0xa9059cbb"     # keccak256("transfer(address,uint256)")[:4]

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

    # =========================================================================
    # Transaction Building Methods
    # =========================================================================

    async def get_nonce(self, address: str) -> int:
        """
        Get the transaction count (nonce) for an address.

        Args:
            address: EVM address (0x...)

        Returns:
            Current nonce (number of transactions sent)
        """
        try:
            result = await self._rpc_call("eth_getTransactionCount", [address, "pending"])
            nonce = int(result, 16)
            logger.debug(f"[ChainClient] Nonce for {address}: {nonce}")
            return nonce
        except Exception as e:
            logger.error(f"[ChainClient] Failed to get nonce: {e}")
            raise

    async def get_gas_price(self) -> int:
        """
        Get current gas price in wei.

        Returns:
            Gas price in wei
        """
        try:
            result = await self._rpc_call("eth_gasPrice", [])
            gas_price = int(result, 16)
            logger.debug(f"[ChainClient] Gas price: {gas_price} wei")
            return gas_price
        except Exception as e:
            logger.error(f"[ChainClient] Failed to get gas price: {e}")
            raise

    async def estimate_gas(self, tx: Dict[str, Any]) -> int:
        """
        Estimate gas for a transaction.

        Args:
            tx: Transaction dict with 'from', 'to', 'data', 'value'

        Returns:
            Estimated gas units
        """
        try:
            result = await self._rpc_call("eth_estimateGas", [tx])
            gas = int(result, 16)
            logger.debug(f"[ChainClient] Estimated gas: {gas}")
            return gas
        except Exception as e:
            logger.error(f"[ChainClient] Failed to estimate gas: {e}")
            raise

    def build_erc20_transfer(
        self,
        to: str,
        amount: Decimal,
        decimals: int = 6,
    ) -> bytes:
        """
        Build ERC-20 transfer calldata.

        Args:
            to: Recipient address
            amount: Amount in token units (e.g., 1.5 USDC)
            decimals: Token decimals (6 for USDC)

        Returns:
            ABI-encoded calldata for transfer(address,uint256)
        """
        # Convert amount to raw units
        raw_amount = int(amount * Decimal(10**decimals))

        # Encode: selector + padded address + padded amount
        selector = bytes.fromhex(TRANSFER_SELECTOR[2:])  # Remove 0x
        padded_to = bytes.fromhex(to.lower().replace("0x", "").zfill(64))
        padded_amount = raw_amount.to_bytes(32, "big")

        return selector + padded_to + padded_amount

    def hash_transaction(self, tx: Dict[str, Any]) -> bytes:
        """
        RLP encode and hash an unsigned transaction for signing.

        Args:
            tx: Transaction dict with:
                - nonce: int
                - gasPrice: int (wei)
                - gas: int
                - to: str (0x...)
                - value: int (wei)
                - data: bytes
                - chainId: int

        Returns:
            32-byte keccak256 hash for signing (EIP-155)
        """
        # EIP-155 unsigned transaction: [nonce, gasPrice, gas, to, value, data, chainId, 0, 0]
        to_bytes = bytes.fromhex(tx["to"].replace("0x", "")) if tx.get("to") else b""
        data = tx.get("data", b"")
        if isinstance(data, str):
            data = bytes.fromhex(data.replace("0x", ""))

        unsigned_tx = [
            tx["nonce"],
            tx["gasPrice"],
            tx["gas"],
            to_bytes,
            tx.get("value", 0),
            data,
            tx["chainId"],
            0,  # EIP-155: v placeholder
            0,  # EIP-155: r placeholder
        ]

        encoded = rlp_encode(unsigned_tx)
        tx_hash = keccak256(encoded)
        logger.debug(f"[ChainClient] Transaction hash: 0x{tx_hash.hex()}")
        return tx_hash

    def encode_signed_transaction(
        self,
        tx: Dict[str, Any],
        signature: bytes,
    ) -> str:
        """
        Encode a signed transaction for broadcast.

        Args:
            tx: Original unsigned transaction dict
            signature: 65-byte signature (r || s || v) from CIRISVerify

        Returns:
            Hex-encoded signed transaction (0x...)
        """
        if len(signature) != 65:
            raise ValueError(f"Signature must be 65 bytes, got {len(signature)}")

        # Parse signature components
        r = int.from_bytes(signature[:32], "big")
        s = int.from_bytes(signature[32:64], "big")
        v_raw = signature[64]

        # EIP-155 v value: chainId * 2 + 35 + recovery_id
        # CIRISVerify returns v as 27 or 28 (already adjusted)
        if v_raw in (0, 1):
            # Raw recovery id, need to apply EIP-155
            v = tx["chainId"] * 2 + 35 + v_raw
        else:
            # Already EIP-155 adjusted (27/28), re-adjust for chainId
            recovery_id = v_raw - 27
            v = tx["chainId"] * 2 + 35 + recovery_id

        # Build signed transaction
        to_bytes = bytes.fromhex(tx["to"].replace("0x", "")) if tx.get("to") else b""
        data = tx.get("data", b"")
        if isinstance(data, str):
            data = bytes.fromhex(data.replace("0x", ""))

        signed_tx = [
            tx["nonce"],
            tx["gasPrice"],
            tx["gas"],
            to_bytes,
            tx.get("value", 0),
            data,
            v,
            r,
            s,
        ]

        encoded = rlp_encode(signed_tx)
        hex_tx = "0x" + encoded.hex()
        logger.debug(f"[ChainClient] Signed transaction: {hex_tx[:50]}...")
        return hex_tx
