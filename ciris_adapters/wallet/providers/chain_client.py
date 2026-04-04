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
    """Compute Keccak-256 hash (Ethereum's hash function).

    IMPORTANT: Keccak-256 is NOT the same as SHA3-256!
    - SHA3-256: NIST standard with domain separation padding
    - Keccak-256: Original algorithm before NIST standardization

    Ethereum uses the original Keccak-256, so we must NOT use hashlib.sha3_256.
    """
    # Try pysha3 first (has correct keccak_256)
    try:
        import sha3  # type: ignore[import-not-found]

        result = sha3.keccak_256(data).digest()
        return bytes(result)
    except ImportError:
        pass

    # Try PyCryptodome (has correct Keccak)
    try:
        from Crypto.Hash import keccak

        result = keccak.new(data=data, digest_bits=256).digest()
        return bytes(result)
    except ImportError:
        pass

    # Last resort: try eth_hash if available (from eth-utils)
    try:
        from eth_hash.auto import keccak as eth_keccak  # type: ignore[import-not-found]

        result = eth_keccak(data)
        return bytes(result)
    except ImportError:
        pass

    raise ImportError(
        "No keccak256 implementation available. " "Install one of: pysha3, pycryptodome, or eth-hash[pycryptodome]"
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
            return bytes([0xB7 + len(len_bytes)]) + len_bytes + item

    elif isinstance(item, list):
        encoded_items = b"".join(rlp_encode(i) for i in item)
        if len(encoded_items) < 56:
            return bytes([0xC0 + len(encoded_items)]) + encoded_items
        else:
            len_bytes = _encode_length(len(encoded_items))
            return bytes([0xF7 + len(len_bytes)]) + len_bytes + encoded_items

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
TRANSFER_SELECTOR = "0xa9059cbb"  # keccak256("transfer(address,uint256)")[:4]
APPROVE_SELECTOR = "0x095ea7b3"  # keccak256("approve(address,uint256)")[:4]
ALLOWANCE_SELECTOR = "0xdd62ed3e"  # keccak256("allowance(address,address)")[:4]

# USDC has 6 decimals
USDC_DECIMALS = 6

# ERC-4337 EntryPoint v0.6 (same on all EVM chains)
ENTRYPOINT_V06 = "0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789"

# Simple Account Factory (for creating smart accounts)
SIMPLE_ACCOUNT_FACTORY: Dict[str, str] = {
    "base-mainnet": "0x9406Cc6185a346906296840746125a0E44976454",
    "base-sepolia": "0x9406Cc6185a346906296840746125a0E44976454",
}

# Execute function selector for SimpleAccount
# execute(address dest, uint256 value, bytes calldata func)
EXECUTE_SELECTOR = "0xb61d27f6"


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

        # ERC-4337 contracts
        self.entrypoint: str = ENTRYPOINT_V06
        self.account_factory: str = SIMPLE_ACCOUNT_FACTORY.get(network, SIMPLE_ACCOUNT_FACTORY["base-mainnet"])

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

    # =========================================================================
    # ERC-20 Approval Methods
    # =========================================================================

    def build_erc20_approve(
        self,
        spender: str,
        amount: int,
    ) -> bytes:
        """
        Build ERC-20 approve calldata.

        Args:
            spender: Address to approve spending
            amount: Amount to approve (in raw units, e.g., 1000000 for 1 USDC)

        Returns:
            ABI-encoded calldata for approve(address,uint256)
        """
        selector = bytes.fromhex(APPROVE_SELECTOR[2:])
        padded_spender = bytes.fromhex(spender.lower().replace("0x", "").zfill(64))
        padded_amount = amount.to_bytes(32, "big")

        return selector + padded_spender + padded_amount

    async def get_allowance(self, owner: str, spender: str, token_address: str) -> int:
        """
        Get current ERC-20 allowance.

        Args:
            owner: Token owner address
            spender: Approved spender address
            token_address: ERC-20 token contract address

        Returns:
            Current allowance in raw token units
        """
        try:
            # Encode allowance(address,address) call
            padded_owner = owner.lower().replace("0x", "").zfill(64)
            padded_spender = spender.lower().replace("0x", "").zfill(64)
            call_data = f"{ALLOWANCE_SELECTOR}{padded_owner}{padded_spender}"

            result = await self._rpc_call(
                "eth_call",
                [{"to": token_address, "data": call_data}, "latest"],
            )

            allowance = int(result, 16)
            logger.debug(f"[ChainClient] Allowance for {owner} → {spender}: {allowance}")
            return allowance
        except Exception as e:
            logger.error(f"[ChainClient] Failed to get allowance: {e}")
            return 0

    # =========================================================================
    # ERC-4337 UserOperation Building Methods
    # =========================================================================

    def build_execute_calldata(
        self,
        dest: str,
        value: int,
        func_data: bytes,
    ) -> bytes:
        """
        Build execute() calldata for SimpleAccount.

        This wraps the actual transaction (e.g., ERC-20 transfer) in the
        smart account's execute function.

        Args:
            dest: Target contract address
            value: ETH value to send (usually 0 for ERC-20)
            func_data: Encoded function call (e.g., transfer calldata)

        Returns:
            ABI-encoded calldata for execute(address,uint256,bytes)
        """
        selector = bytes.fromhex(EXECUTE_SELECTOR[2:])

        # Encode parameters:
        # address dest (32 bytes)
        # uint256 value (32 bytes)
        # bytes func offset (32 bytes) -> points to 96 (0x60)
        # bytes func length (32 bytes)
        # bytes func data (padded to 32 bytes)
        padded_dest = bytes.fromhex(dest.lower().replace("0x", "").zfill(64))
        padded_value = value.to_bytes(32, "big")
        func_offset = (96).to_bytes(32, "big")  # Offset to func data (after 3 * 32 bytes)
        func_length = len(func_data).to_bytes(32, "big")

        # Pad func_data to 32-byte boundary
        padding_needed = (32 - (len(func_data) % 32)) % 32
        padded_func = func_data + (b"\x00" * padding_needed)

        return selector + padded_dest + padded_value + func_offset + func_length + padded_func

    def build_userop_calldata_for_transfer(
        self,
        recipient: str,
        amount: Decimal,
        token_address: Optional[str] = None,
    ) -> bytes:
        """
        Build UserOperation calldata for a token transfer.

        This creates the nested calldata structure:
        execute(USDC, 0, transfer(recipient, amount))

        Args:
            recipient: Recipient address
            amount: Amount in token units (e.g., 1.5 USDC)
            token_address: Token contract (defaults to USDC)

        Returns:
            Encoded calldata for the UserOperation
        """
        token = token_address or self.usdc_address

        # First build the inner transfer call
        transfer_calldata = self.build_erc20_transfer(recipient, amount, USDC_DECIMALS)

        # Wrap in execute() for SimpleAccount
        return self.build_execute_calldata(
            dest=token,
            value=0,
            func_data=transfer_calldata,
        )

    async def get_smart_account_nonce(self, account: str) -> int:
        """
        Get the ERC-4337 nonce for a smart account from EntryPoint.

        Args:
            account: Smart account address

        Returns:
            Current nonce (key=0)
        """
        # getNonce(address sender, uint192 key)
        # selector = 0x35567e1a
        padded_account = account.lower().replace("0x", "").zfill(64)
        padded_key = "0".zfill(64)  # key = 0
        call_data = f"0x35567e1a{padded_account}{padded_key}"

        try:
            result = await self._rpc_call(
                "eth_call",
                [{"to": self.entrypoint, "data": call_data}, "latest"],
            )
            nonce = int(result, 16)
            logger.debug(f"[ChainClient] Smart account nonce for {account}: {nonce}")
            return nonce
        except Exception as e:
            logger.error(f"[ChainClient] Failed to get smart account nonce: {e}")
            return 0

    def compute_smart_account_address(self, owner: str, salt: int = 0) -> str:
        """
        Compute the counterfactual smart account address for an owner.

        Uses CREATE2 deterministic deployment.

        Args:
            owner: EOA owner address
            salt: Salt for address generation (default 0)

        Returns:
            Smart account address (may not be deployed yet)
        """
        # This is a simplified computation - the actual address depends
        # on the factory's implementation. For SimpleAccountFactory:
        # createAccount(owner, salt) -> address

        # For now, we'll query the factory's getAddress function
        # getAddress(address owner, uint256 salt)
        # selector = 0x8cb84e18 (example - actual may vary)

        # Note: In production, we'd call the factory to get the address
        # For MVP, we assume the account already exists
        logger.debug(f"[ChainClient] Computing smart account for owner={owner}")
        return owner  # Placeholder - actual implementation queries factory

    async def get_fee_data(self) -> tuple[int, int]:
        """
        Get current fee data for EIP-1559 transactions.

        Returns:
            Tuple of (maxFeePerGas, maxPriorityFeePerGas) in wei
        """
        try:
            # Get base fee from latest block
            block = await self._rpc_call("eth_getBlockByNumber", ["latest", False])
            base_fee = int(block.get("baseFeePerGas", "0x0"), 16)

            # Priority fee (tip) - Base L2 typically needs minimal tip
            priority_fee = 1_000_000  # 0.001 gwei - Base is cheap

            # Max fee = base fee * 2 + priority fee (buffer for price fluctuation)
            max_fee = base_fee * 2 + priority_fee

            logger.debug(
                f"[ChainClient] Fee data: baseFee={base_fee}, " f"maxFee={max_fee}, priorityFee={priority_fee}"
            )
            return max_fee, priority_fee
        except Exception as e:
            logger.error(f"[ChainClient] Failed to get fee data: {e}")
            # Fallback to reasonable defaults for Base
            return 100_000_000, 1_000_000  # 0.1 gwei max, 0.001 gwei priority
