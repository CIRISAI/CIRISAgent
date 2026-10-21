# Wallet Signing Architecture

## FSD-WALLET-001: Unified Wallet Key Management via CIRISVerify

**Status**: Implemented (CIRISVerify 1.3.1)
**Author**: CIRIS Engineering
**Date**: 2024-01
**Updated**: 2026-03
**Relates To**: x402 Wallet Adapter, CIRISVerify Integration

---

## 1. Overview

### 1.1 Problem Statement

The x402 wallet adapter requires secp256k1 signing for EVM transactions, but CIRISVerify currently provides Ed25519 keys. The wallet needs a unified signing architecture that:

1. Works across all platforms (Android, iOS, Desktop, Server)
2. Uses hardware-backed keys when available
3. Falls back gracefully to software-backed keys
4. Derives wallet keys from the existing agent signing identity
5. Maintains a single API regardless of backing implementation

### 1.2 Solution

Extend CIRISVerify to support secp256k1 key derivation and signing, with the wallet key derived deterministically from the agent's root Ed25519 identity. CIRISVerify handles all key storage, derivation, and signing operations - the wallet adapter simply calls the unified API.

### 1.3 Design Principles

- **Single Source of Truth**: Agent's Ed25519 key is the root identity
- **Deterministic Derivation**: secp256k1 wallet key derived from Ed25519 seed
- **Unified API**: Same interface regardless of HW/SW backing
- **Defense in Depth**: Hardware protection when available, secure software fallback
- **No Key Export**: Private keys never leave CIRISVerify boundary

---

## 2. Key Hierarchy

```
Agent Root Identity (Ed25519)
│
├── Agent Signing Key (Ed25519)
│   └── Used for: ACCORD signatures, agent-to-agent auth, attestations
│
└── Wallet Signing Key (secp256k1) ──[DERIVED]
    └── Used for: EVM transactions, ERC-20 transfers, contract calls
```

### 2.1 Derivation Path

```
secp256k1_seed = HKDF-SHA256(
    IKM  = ed25519_seed,
    salt = "CIRIS-wallet-v1",
    info = "secp256k1-evm-signing-key",
    L    = 32
)

secp256k1_private_key = secp256k1_seed  # Valid curve point (retry if not)
secp256k1_public_key  = secp256k1_private_key * G
evm_address           = keccak256(secp256k1_public_key)[12:32]
```

### 2.2 Address Derivation Guarantee

**Critical**: The EVM address MUST be derived from the same key material used for signing. This FSD explicitly unifies the two derivation paths that were previously inconsistent:

| Old Behavior | New Behavior |
|--------------|--------------|
| Address from HKDF(pubkey) truncated | Address from secp256k1 pubkey via keccak256 |
| Test signing from HKDF(seed) → secp256k1 | Same derivation for both address and signing |
| Address ≠ Signer | Address = Signer (guaranteed) |

---

## 3. CIRISVerify API Extensions

### 3.1 New Methods

```python
class CIRISVerify:
    """Extended API for wallet signing support."""

    # Key Derivation
    def derive_secp256k1_public_key(self) -> bytes:
        """
        Derive secp256k1 public key from agent root identity.

        Returns:
            65-byte uncompressed public key (04 || x || y)

        Note: Private key never leaves secure boundary.
        """

    def get_evm_address(self) -> str:
        """
        Get EVM address derived from secp256k1 public key.

        Returns:
            Checksummed EVM address (0x...)
        """

    # Signing Operations
    def sign_secp256k1(self, message_hash: bytes) -> bytes:
        """
        Sign a 32-byte hash with the derived secp256k1 key.

        Args:
            message_hash: 32-byte keccak256 hash to sign

        Returns:
            65-byte signature (r || s || v) in Ethereum format

        Raises:
            SigningError: If hardware trust is degraded
        """

    def sign_evm_transaction(self, tx_hash: bytes, chain_id: int) -> bytes:
        """
        Sign an EVM transaction hash with EIP-155 replay protection.

        Args:
            tx_hash: 32-byte transaction hash
            chain_id: EVM chain ID for replay protection

        Returns:
            65-byte signature with correct v value for chain_id
        """

    def sign_typed_data(self, domain_hash: bytes, message_hash: bytes) -> bytes:
        """
        Sign EIP-712 typed data.

        Args:
            domain_hash: 32-byte domain separator hash
            message_hash: 32-byte struct hash

        Returns:
            65-byte signature over keccak256(0x1901 || domain_hash || message_hash)
        """

    # Capability Query
    def get_signing_capabilities(self) -> SigningCapabilities:
        """
        Query available signing capabilities.

        Returns:
            SigningCapabilities with:
            - supports_ed25519: bool
            - supports_secp256k1: bool
            - hardware_backed: bool
            - attestation_level: int
            - trust_degraded: bool
        """
```

### 3.2 Signing Capabilities Model

```python
@dataclass
class SigningCapabilities:
    """Capabilities of the current CIRISVerify instance."""

    # Curve support
    supports_ed25519: bool = True      # Always true
    supports_secp256k1: bool = True    # True after this FSD implemented

    # Backing type
    hardware_backed: bool              # True if using StrongBox/SE/TEE
    backing_type: str                  # "strongbox" | "tee" | "secure_enclave" | "software"

    # Trust level
    attestation_level: int             # 0-5 per existing model
    trust_degraded: bool               # True if HW attestation failed
    degradation_reason: Optional[str]  # Why trust is degraded

    # Wallet-specific
    can_sign_transactions: bool        # False if trust_degraded and level < 2
    max_transaction_usd: Decimal       # Based on attestation level
```

---

## 4. Platform Implementations

### 4.1 Android (StrongBox/TEE)

```
┌─────────────────────────────────────────────────────┐
│                    Application                       │
├─────────────────────────────────────────────────────┤
│                   CIRISVerify API                    │
├─────────────────────────────────────────────────────┤
│              Android Keystore System                 │
├──────────────────────┬──────────────────────────────┤
│     StrongBox HSM    │         TEE (TrustZone)      │
│  (Pixel, Samsung S+) │      (Fallback for others)   │
└──────────────────────┴──────────────────────────────┘
```

**Implementation Notes**:
- Store Ed25519 seed in Keystore with `setIsStrongBoxBacked(true)`
- Derive secp256k1 inside TEE/StrongBox using HKDF
- secp256k1 signing via native crypto in secure world
- Fallback: If StrongBox unavailable, use TEE
- Fallback: If TEE unavailable, use software with attestation_level=1

### 4.2 iOS (Secure Enclave)

```
┌─────────────────────────────────────────────────────┐
│                    Application                       │
├─────────────────────────────────────────────────────┤
│                   CIRISVerify API                    │
├─────────────────────────────────────────────────────┤
│                   Keychain Services                  │
├─────────────────────────────────────────────────────┤
│                   Secure Enclave                     │
│            (P-256 only - no secp256k1)              │
└─────────────────────────────────────────────────────┘
```

**Implementation Notes**:
- Secure Enclave only supports P-256, NOT secp256k1
- Store Ed25519 seed in Keychain with `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`
- Derive secp256k1 in software (within app sandbox)
- Sign in software using derived key
- Set `hardware_backed=false` but maintain secure storage
- Attestation via DeviceCheck + App Attest

### 4.3 Desktop (Windows/macOS/Linux)

```
┌─────────────────────────────────────────────────────┐
│                    Application                       │
├─────────────────────────────────────────────────────┤
│                   CIRISVerify API                    │
├─────────────────────────────────────────────────────┤
│              Platform Secure Storage                 │
│  Windows: DPAPI  │  macOS: Keychain  │  Linux: Secret Service
└─────────────────────────────────────────────────────┘
```

**Implementation Notes**:
- Use platform credential storage for seed
- All crypto operations in software
- Set `hardware_backed=false`
- Attestation level based on platform security features
- Optional: Support hardware wallets (Ledger/Trezor) as signers

### 4.4 Server/Headless

```
┌─────────────────────────────────────────────────────┐
│                    Application                       │
├─────────────────────────────────────────────────────┤
│                   CIRISVerify API                    │
├─────────────────────────────────────────────────────┤
│                Environment / Secrets                 │
│        (HashiCorp Vault, AWS KMS, etc.)             │
└─────────────────────────────────────────────────────┘
```

**Implementation Notes**:
- Seed from environment variable or secrets manager
- All crypto in software
- Set `hardware_backed=false`
- Attestation based on deployment environment
- Consider: AWS Nitro Enclaves for hardware-backed server signing

---

## 5. Security Model

### 5.1 Trust Levels by Platform

| Platform | Backing | Hardware | Attestation | Max Tx |
|----------|---------|----------|-------------|--------|
| Android StrongBox | HSM | Yes | 5 | $100 |
| Android TEE | TrustZone | Yes | 4 | $100 |
| Android Software | App Sandbox | No | 2 | $0.10 |
| iOS Secure Enclave | SE (P-256 only) | Partial | 4 | $100 |
| iOS Software | App Sandbox | No | 3 | $50 |
| Desktop | OS Keychain | No | 2 | $0.10 |
| Server (Vault/KMS) | Managed | Depends | 3 | $50 |
| Server (Env Var) | None | No | 1 | $0 |

### 5.2 Key Protection Requirements

```python
# Minimum requirements for each backing type

HARDWARE_BACKED = {
    "key_extraction": "impossible",      # Key cannot leave secure boundary
    "side_channel": "protected",         # HW protects against timing/power analysis
    "attestation": "cryptographic",      # HW-rooted attestation chain
}

SOFTWARE_BACKED = {
    "key_extraction": "app_boundary",    # Key accessible within app process
    "side_channel": "best_effort",       # Software mitigations only
    "attestation": "platform_based",     # OS-level attestation (Play Integrity, etc.)
}
```

### 5.3 Degraded Trust Handling

When hardware attestation fails or trust is degraded:

1. **Receive-Only Mode**: `can_sign_transactions = False`
2. **Existing Funds**: Can still view balance, receive transfers
3. **Recovery Path**: Re-attestation or manual WA approval for sends
4. **User Notification**: Clear indication of degraded state

---

## 6. Wallet Adapter Integration

### 6.1 Updated x402 Provider

```python
class X402Provider(WalletProvider):
    """x402 provider using CIRISVerify for all signing."""

    def __init__(self, config: X402ProviderConfig, verifier: CIRISVerify):
        self._verifier = verifier
        self._capabilities = verifier.get_signing_capabilities()

        # Address derived via CIRISVerify (guaranteed to match signer)
        self._evm_address = verifier.get_evm_address()

    async def send(self, amount: Decimal, currency: str, recipient: str, ...) -> TransactionResult:
        # Check capabilities
        if not self._capabilities.can_sign_transactions:
            return TransactionResult(
                success=False,
                error=f"Signing disabled: {self._capabilities.degradation_reason}"
            )

        # Build transaction
        tx = self._build_erc20_transfer(recipient, amount)
        tx_hash = self._hash_transaction(tx)

        # Sign via CIRISVerify (HW or SW transparent to us)
        signature = self._verifier.sign_evm_transaction(tx_hash, self._chain_id)

        # Submit
        signed_tx = self._encode_signed_transaction(tx, signature)
        tx_id = await self._chain_client.send_raw_transaction(signed_tx)

        return TransactionResult(success=True, transaction_id=tx_id, ...)
```

### 6.2 Initialization Flow

```python
# In wallet adapter.py

async def initialize_wallet(self) -> None:
    # Get or create CIRISVerify instance
    verifier = get_ciris_verifier()

    # Check secp256k1 support
    caps = verifier.get_signing_capabilities()
    if not caps.supports_secp256k1:
        raise WalletError("CIRISVerify does not support secp256k1 signing")

    # Log backing type
    logger.info(f"Wallet initialized with {caps.backing_type} backing")
    logger.info(f"Hardware backed: {caps.hardware_backed}")
    logger.info(f"Attestation level: {caps.attestation_level}")
    logger.info(f"EVM address: {verifier.get_evm_address()}")

    # Initialize provider
    self._provider = X402Provider(self._config, verifier)
```

---

## 7. Migration Path

### 7.1 From Current Implementation

Current state:
- Address derived via HKDF(pubkey) → truncate (not signable)
- Test signing via HKDF(seed) → secp256k1 (different address)

Migration:
1. **Phase 1**: Implement CIRISVerify secp256k1 extensions
2. **Phase 2**: Update x402 provider to use new API
3. **Phase 3**: Deprecate old derivation methods
4. **Phase 4**: Migration tool for any existing balances (if applicable)

### 7.2 Address Change Impact

**Important**: The new derivation produces a DIFFERENT address than the old HKDF-truncate method.

- If no funds have been received at old address: No impact
- If funds exist at old address: Manual recovery needed (sweep to new address)

Recommendation: Complete this migration BEFORE any mainnet funds are received.

---

## 8. Testing Requirements

### 8.1 Unit Tests

```python
def test_address_matches_signer():
    """Critical: Derived address must match actual signer."""
    verifier = CIRISVerify()
    address = verifier.get_evm_address()

    # Sign a message
    msg_hash = keccak256(b"test")
    sig = verifier.sign_secp256k1(msg_hash)

    # Recover signer from signature
    recovered = ecrecover(msg_hash, sig)

    assert recovered == address, "Address must match signer"

def test_deterministic_derivation():
    """Same seed must produce same address across restarts."""
    seed = os.urandom(32)

    v1 = CIRISVerify(seed=seed)
    addr1 = v1.get_evm_address()

    v2 = CIRISVerify(seed=seed)
    addr2 = v2.get_evm_address()

    assert addr1 == addr2, "Derivation must be deterministic"

def test_hardware_fallback():
    """Software fallback must work when hardware unavailable."""
    verifier = CIRISVerify(force_software=True)
    caps = verifier.get_signing_capabilities()

    assert caps.supports_secp256k1
    assert not caps.hardware_backed
    assert caps.can_sign_transactions  # At appropriate attestation level
```

### 8.2 Integration Tests

- Sign and submit transaction on Base Sepolia
- Verify transaction succeeds and is mined
- Verify sender address matches `get_evm_address()`
- Test on each platform (Android emulator, iOS simulator, desktop)

### 8.3 Security Tests

- Verify key cannot be extracted via API
- Verify degraded trust prevents signing
- Verify attestation levels are correctly reported
- Fuzz signing inputs for robustness

---

## 9. Gas Funding Strategies

### 9.1 The Gas Problem

EVM transactions require ETH for gas, but agents hold USDC. Options for funding gas:

| Strategy | Complexity | UX | Trust Model |
|----------|------------|-----|-------------|
| Manual ETH Funding | Low | Poor | User funds directly |
| Auto USDC→ETH Swap | Medium | Good | DEX dependency |
| ERC-4337 Paymaster | High | Excellent | Paymaster trust |
| Gas Station Network | Medium | Good | Relayer trust |
| Pre-funded Gas Tank | Low | Good | Agent self-funds |

### 9.2 Current Implementation (MVP)

**Pre-check + Error Message**:
```python
# In x402_provider._send_usdc():
eth_balance = await self._chain_client.get_eth_balance(self._evm_address)
estimated_gas = 65000 * gas_price  # ~$0.01 on Base

if eth_balance < estimated_gas:
    return TransactionResult(
        success=False,
        error=f"Insufficient ETH for gas. Have: {eth_balance} ETH, need: ~{estimated_gas} ETH. "
              f"Send ETH to {self._evm_address} or use the gas funding tool.",
    )
```

### 9.3 Future: Automated USDC→ETH Swap

Base has native Uniswap V3 deployment. Auto-swap flow:
1. Check ETH balance
2. If insufficient, swap minimum required USDC to WETH via Uniswap
3. Unwrap WETH to ETH
4. Proceed with original transaction

**Considerations**:
- Requires ETH for the swap transaction itself (chicken-egg)
- Solution: Use flash loans or batch swap+send in single tx
- Alternative: ERC-4337 bundled operations

### 9.4 Future: ERC-4337 Paymaster

Base supports ERC-4337 Account Abstraction. With a paymaster:
1. Deploy smart wallet (once per agent)
2. Configure paymaster to accept USDC
3. User ops pay gas in USDC
4. Paymaster converts to ETH and executes

**Implementation Complexity**: HIGH
- Requires smart wallet deployment ($5-10 on Base)
- Need paymaster service (self-hosted or third-party)
- UserOperation encoding differs from legacy transactions

### 9.5 Recommendation

**Phase 1 (MVP)**: Pre-check + manual funding
- Simple, no additional dependencies
- Clear error messages guide user

**Phase 2**: Add `fund_gas` tool
- Agent can swap USDC→ETH via Uniswap
- Triggered manually or automatically before send

**Phase 3**: Evaluate ERC-4337
- If high volume or UX complaints, invest in AA integration
- Consider third-party paymaster (Pimlico, Biconomy)

---

## 10. Open Questions

1. **Key Rotation**: Should wallet support key rotation? (Probably not for v1)
2. **Multi-Wallet**: Support multiple derived wallets per agent? (Different derivation paths)
3. **Hardware Wallet Integration**: Support Ledger/Trezor as alternative signers?
4. **Social Recovery**: Implement any recovery mechanism for lost devices?
5. **Gas Tank Service**: Should CIRIS operate a centralized gas faucet for agent onboarding?

---

## 11. References

- [EIP-155: Replay Protection](https://eips.ethereum.org/EIPS/eip-155)
- [EIP-712: Typed Data Signing](https://eips.ethereum.org/EIPS/eip-712)
- [HKDF RFC 5869](https://tools.ietf.org/html/rfc5869)
- [Android Keystore](https://developer.android.com/training/articles/keystore)
- [iOS Secure Enclave](https://support.apple.com/guide/security/secure-enclave-sec59b0b31ff/web)
- [CIRISVerify Integration Guide](../ciris_verify/INTEGRATION.md)
