# CIRIS Wallet Adapter
## Functional Specification Document

**Document:** FSD-CIRIS-WALLET-001
**Version:** 1.0.0-DRAFT
**Date:** 2026-03-25
**Author:** Eric (CIRIS L3C)
**Status:** Draft
**CIRIS Agent Version:** 2.3.0
**Based On:** x402 Protocol Integration Spec v0.3.0

---

## 1. Purpose

This document specifies the WalletAdapter for CIRIS - a generic payment adapter that abstracts cryptocurrency and fiat mobile money providers behind three simple tools. The adapter enables CIRIS agents to send money, request payments, and check account statements without coupling to any specific payment provider.

The first implementation supports:
- **x402/USDC on Base** - International stablecoin payments via the x402 HTTP payment protocol
- **Chapa/ETB** - Ethiopian Birr via Telebirr, CBE Birr, and bank transfers

This is an open specification. Any payment provider implementing the `WalletProvider` protocol can be added.

### 1.1 Design Principles

1. **Provider Agnostic** - The three tools (`send_money`, `request_money`, `get_statement`) work identically regardless of whether the underlying provider is crypto or fiat
2. **Currency as Routing Hint** - USDC routes to x402, KES routes to M-Pesa, ETB routes to Chapa
3. **Adapter Pattern** - Wallet is a standard CIRIS adapter providing tools via ToolBus
4. **Ethics Pipeline Integration** - All money operations go through H3ERE/DMA evaluation with `requires_approval=True`
5. **No Core Engine Changes** - The wallet lives entirely in the adapter layer

### 1.2 Why This Matters

CIRIS operates a growing distributed community including contributors on budget hardware in regions with limited financial infrastructure. Ethiopian philosophers testing ethical AI systems should be able to pay for API access in Birr via Telebirr - not be forced to acquire USDC.

The same endpoint accepts both:
```json
{
  "accepts": [
    {"currency": "USDC", "amount": "0.10", "provider": "x402"},
    {"currency": "ETB", "amount": "13.00", "provider": "chapa"}
  ]
}
```

The client picks whichever they can pay. Same ethics pipeline. Same audit trail.

---

## 2. Architecture

### 2.1 Adapter Structure

```
ciris_adapters/wallet/
├── __init__.py
├── adapter.py              # WalletAdapter - registration & lifecycle
├── config.py               # WalletAdapterConfig
├── tool_service.py         # WalletToolService - 3 generic tools
├── schemas.py              # Transaction, Balance, AccountDetails models
└── providers/
    ├── __init__.py
    ├── base.py             # WalletProvider protocol
    ├── x402_provider.py    # USDC/Base via x402 protocol
    └── chapa_provider.py   # ETB via Chapa gateway
```

### 2.2 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        CIRIS Runtime                             │
│                                                                  │
│  ┌──────────────┐     ┌─────────────────────────────────────┐   │
│  │   ToolBus    │────▶│         WalletToolService           │   │
│  └──────────────┘     │                                     │   │
│                       │  send_money()                       │   │
│                       │  request_money()                    │   │
│                       │  get_statement()                    │   │
│                       │         │                           │   │
│                       │         ▼                           │   │
│                       │  ┌─────────────────────────────┐    │   │
│                       │  │    Provider Router          │    │   │
│                       │  │                             │    │   │
│                       │  │  currency/provider_params   │    │   │
│                       │  │         │                   │    │   │
│                       │  └─────────┼───────────────────┘    │   │
│                       └────────────┼────────────────────────┘   │
│                                    │                            │
│              ┌─────────────────────┼─────────────────────┐      │
│              │                     │                     │      │
│              ▼                     ▼                     ▼      │
│  ┌───────────────────┐ ┌───────────────────┐ ┌─────────────────┐│
│  │  x402Provider     │ │  ChapaProvider    │ │ (Future)        ││
│  │                   │ │                   │ │ M-Pesa, PIX,    ││
│  │  USDC on Base     │ │  ETB via Telebirr │ │ UPI, etc.       ││
│  │  $0.001/tx        │ │  CBE Birr, Banks  │ │                 ││
│  └─────────┬─────────┘ └─────────┬─────────┘ └─────────────────┘│
└────────────┼─────────────────────┼──────────────────────────────┘
             │                     │
             ▼                     ▼
    ┌─────────────────┐   ┌─────────────────┐
    │ Coinbase CDP    │   │ Chapa API       │
    │ Base Mainnet    │   │ Ethiopian Banks │
    └─────────────────┘   └─────────────────┘
```

### 2.3 Wallet Identity (x402 Provider)

For the x402 provider, the agent's wallet address is deterministically derived from its CIRISVerify Ed25519 signing key:

```
Ed25519 Agent Signing Key (CIRISVerify identity root)
        │
        ▼  HKDF-SHA256 with domain separator
secp256k1 Private Key
        │
        ▼
EVM Address (0x...) - the agent's wallet on Base
```

This means:
- **No separate wallet provisioning** - Identity = Wallet
- **Revocation kills spending** - CIRISVerify revocation freezes the wallet
- **Hardware binding** - Key lives in secure element, not software

---

## 3. Tool Specifications

### 3.1 send_money

Send money to a recipient via any configured provider.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `recipient` | string | Yes | Recipient address/phone/username (format depends on provider) |
| `amount` | number | Yes | Amount to send |
| `currency` | string | Yes | Currency code (USDC, ETB, KES, USD, etc.) |
| `memo` | string | No | Transaction memo/description |
| `provider_params` | object | No | Provider-specific parameters |
| `provider_params.provider` | string | No | Explicit provider (x402, chapa, mpesa). Auto-detected from currency if omitted |

**Returns:**

```json
{
  "success": true,
  "transaction_id": "tx_abc123",
  "provider": "x402",
  "amount": 0.10,
  "currency": "USDC",
  "recipient": "0x1234...",
  "timestamp": "2026-03-25T10:30:00Z",
  "fees": {
    "network_fee": 0.001,
    "provider_fee": 0.00
  },
  "confirmation": {
    "block_number": 12345678,
    "tx_hash": "0xabc..."
  }
}
```

**DMA Guidance:**
- `requires_approval`: true
- `min_confidence`: 0.95
- `when_not_to_use`: "When recipient not explicitly confirmed by user"
- `ethical_considerations`: "Verify recipient identity. Confirm amount. Check for duplication."

**Examples:**

```json
// Send USDC via x402
{
  "recipient": "0x742d35Cc6634C0532925a3b844Bc9e7595f...",
  "amount": 10.00,
  "currency": "USDC",
  "memo": "Contributor payment - March 2026"
}

// Send ETB via Chapa
{
  "recipient": "+251912345678",
  "amount": 1300.00,
  "currency": "ETB",
  "memo": "API usage - Philosophy department"
}
```

### 3.2 request_money

Create a payment request/invoice that others can pay.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `amount` | number | Yes | Amount to request |
| `currency` | string | Yes | Currency code |
| `description` | string | Yes | What the payment is for |
| `expires_at` | string | No | ISO 8601 expiration timestamp |
| `provider_params` | object | No | Provider-specific parameters |
| `provider_params.provider` | string | No | Explicit provider |
| `provider_params.callback_url` | string | No | Webhook for payment notification |

**Returns:**

```json
{
  "success": true,
  "request_id": "req_xyz789",
  "provider": "chapa",
  "amount": 13.00,
  "currency": "ETB",
  "description": "CIRIS API - Single task",
  "checkout_url": "https://checkout.chapa.co/...",
  "expires_at": "2026-03-25T11:30:00Z",
  "status": "pending"
}
```

**DMA Guidance:**
- `requires_approval`: false (creating requests is low-risk)
- `min_confidence`: 0.8

### 3.3 get_statement

Get account balance, transaction history, and account details.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `include_balance` | boolean | No | Include current balance (default: true) |
| `include_history` | boolean | No | Include transaction history (default: true) |
| `include_details` | boolean | No | Include account details (default: false) |
| `history_limit` | integer | No | Max transactions to return (default: 50) |
| `provider_params` | object | No | Provider-specific parameters |
| `provider_params.provider` | string | No | Specific provider to query (queries all if omitted) |

**Returns:**

```json
{
  "success": true,
  "accounts": [
    {
      "provider": "x402",
      "currency": "USDC",
      "balance": {
        "available": 125.50,
        "pending": 10.00,
        "total": 135.50
      },
      "details": {
        "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f...",
        "network": "base-mainnet",
        "attestation_level": 5
      },
      "history": [
        {
          "transaction_id": "tx_abc123",
          "type": "send",
          "amount": -10.00,
          "recipient": "0x1234...",
          "timestamp": "2026-03-24T15:00:00Z",
          "status": "confirmed"
        }
      ]
    },
    {
      "provider": "chapa",
      "currency": "ETB",
      "balance": {
        "available": 5000.00,
        "pending": 0.00,
        "total": 5000.00
      }
    }
  ]
}
```

**DMA Guidance:**
- `requires_approval`: false (read-only operation)
- `min_confidence`: 0.7

---

## 4. Provider Protocol

### 4.1 WalletProvider Interface

All wallet providers implement this protocol:

```python
from typing import Protocol, List, Optional
from decimal import Decimal
from datetime import datetime

class WalletProvider(Protocol):
    """Base protocol for all wallet providers."""

    @property
    def provider_id(self) -> str:
        """Unique provider identifier (e.g., 'x402', 'chapa')."""
        ...

    @property
    def supported_currencies(self) -> List[str]:
        """List of supported currency codes."""
        ...

    async def send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        memo: Optional[str] = None,
        **kwargs
    ) -> TransactionResult:
        """Send money to recipient."""
        ...

    async def request(
        self,
        amount: Decimal,
        currency: str,
        description: str,
        expires_at: Optional[datetime] = None,
        callback_url: Optional[str] = None,
        **kwargs
    ) -> PaymentRequest:
        """Create a payment request."""
        ...

    async def get_balance(self, currency: Optional[str] = None) -> Balance:
        """Get account balance."""
        ...

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        currency: Optional[str] = None
    ) -> List[Transaction]:
        """Get transaction history."""
        ...

    async def get_account_details(self) -> AccountDetails:
        """Get account details (address, network, etc.)."""
        ...

    async def verify_payment(self, payment_ref: str) -> PaymentStatus:
        """Verify a payment by reference ID."""
        ...
```

### 4.2 Adding New Providers

To add a new provider (e.g., M-Pesa for Kenya):

1. Create `ciris_adapters/wallet/providers/mpesa_provider.py`
2. Implement `WalletProvider` protocol
3. Register in `WalletAdapterConfig.providers`
4. Map currencies: `KES → mpesa`

The tool interface remains unchanged. Users just specify `currency: "KES"`.

---

## 5. Pricing

### 5.1 CIRIS API Pricing

| Endpoint | USDC Price | ETB Price | Description |
|----------|------------|-----------|-------------|
| `/v1/agent/interact` | $0.10 | 13.00 ETB | Single task/observation |
| `/v1/health` | Free | Free | Health check |
| `/v1/covenant` | Free | Free | Covenant text |
| `/v1/schema` | Free | Free | API schema |

### 5.2 Provider Fees

| Provider | Network Fee | Provider Fee | Settlement Time |
|----------|-------------|--------------|-----------------|
| x402 (USDC/Base) | ~$0.001 | $0.00 (first 1000/mo) | ~400ms |
| Chapa (ETB) | 0.00 ETB | 1.5% | 24 hours |

---

## 6. Configuration

### 6.1 WalletAdapterConfig

```python
class WalletAdapterConfig(BaseModel):
    """Configuration for the WalletAdapter."""

    # Provider configurations
    x402: Optional[X402ProviderConfig] = None
    chapa: Optional[ChapaProviderConfig] = None

    # Default provider for currencies
    currency_providers: Dict[str, str] = {
        "USDC": "x402",
        "ETB": "chapa",
        "KES": "mpesa",  # Future
    }

    # Spending limits (per provider)
    spending_limits: SpendingLimits = SpendingLimits(
        max_transaction: Decimal("100.00"),
        daily_limit: Decimal("1000.00"),
        session_limit: Decimal("500.00"),
    )

    # Attestation requirements (x402 only)
    min_attestation_level: int = 3

class X402ProviderConfig(BaseModel):
    """x402/USDC provider configuration."""

    network: str = "base-mainnet"  # or "base-sepolia" for testnet
    treasury_address: Optional[str] = None
    facilitator_url: str = "https://x402.org/facilitator"

class ChapaProviderConfig(BaseModel):
    """Chapa/ETB provider configuration."""

    secret_key: SecretStr
    callback_base_url: str
    merchant_name: str = "CIRIS"
```

### 6.2 Environment Variables

```bash
# x402 Provider
WALLET_X402_NETWORK=base-mainnet
WALLET_X402_TREASURY_ADDRESS=0x...

# Chapa Provider
WALLET_CHAPA_SECRET_KEY=CHASECK_...
WALLET_CHAPA_CALLBACK_URL=https://agents.ciris.ai/v1/wallet/chapa/callback

# General
WALLET_DEFAULT_PROVIDER=x402
WALLET_MAX_TRANSACTION=100.00
```

---

## 7. Security

### 7.1 Attestation-Gated Spending (x402)

The x402 provider checks CIRISVerify attestation before every transaction:

| CIRISVerify Level | Spending Authority |
|-------------------|-------------------|
| 5 - Full trust | Full configured limits |
| 4 - High trust | Full limits, advisory logged |
| 3 - Medium trust | Reduced limits (50%) |
| 2 - Low trust | Micropayments only (≤ $0.10) |
| 1 - Minimal trust | Receive only |
| 0 - No trust | Wallet frozen |

### 7.2 Key Security

- **x402**: Private key derived from Ed25519 via HKDF, lives in secure element
- **Chapa**: API key stored via CIRIS secrets service (SOPS/encrypted)

### 7.3 Audit Trail

Every transaction is:
1. Logged to CIRIS audit service
2. Recorded in provider's ledger (blockchain for x402, Chapa records for fiat)
3. Included in CIRISVerify attestation chain (x402 only)

---

## 8. Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] Create adapter structure
- [ ] Implement WalletProvider protocol
- [ ] Implement WalletToolService with 3 tools
- [ ] Add configuration and schemas

### Phase 2: x402 Provider (Week 1-2)
- [ ] Implement Ed25519 → secp256k1 key derivation
- [ ] Integrate x402 Python SDK
- [ ] Connect to Base Sepolia testnet
- [ ] Test send/receive round-trip

### Phase 3: Chapa Provider (Week 2)
- [ ] Register CIRIS as Chapa merchant
- [ ] Implement Chapa SDK integration
- [ ] Add webhook handler for payment callbacks
- [ ] Test with Telebirr

### Phase 4: Production (Week 3)
- [ ] Switch x402 to Base mainnet
- [ ] Enable dual-currency 402 responses on API
- [ ] First real ETB payment from Ethiopian users
- [ ] First real USDC contributor payment

### Phase 5: Ethics Integration (Week 4)
- [ ] Verify DMA pipeline gates all send_money calls
- [ ] Test spending limits enforcement
- [ ] Test attestation-gated spending
- [ ] Load test with concurrent transactions

---

## 9. Success Criteria

1. Ethiopian philosopher pays 13 ETB via Telebirr for a CIRIS task - within 3 weeks
2. Contributor receives USDC payment via x402 - within 3 weeks
3. Same `/v1/agent/interact` endpoint accepts both USDC and ETB - within 4 weeks
4. All money operations blocked without DMA approval - verified in testing
5. Attestation degradation reduces spending authority - verified in testing

---

## 10. References

- x402 Protocol: https://x402.org
- x402 Python SDK: https://pypi.org/project/x402/
- Coinbase CDP SDK: https://pypi.org/project/cdp-sdk/
- Chapa Gateway: https://chapa.co
- Chapa Python SDK: https://pypi.org/project/chapa/
- CIRIS Adapter Pattern: `ciris_adapters/home_assistant/` (reference implementation)

---

*"The signing key is the identity. The identity is the wallet. The wallet funds the work. The work serves the community."*

*CIRIS L3C - Selfless and Pure*
