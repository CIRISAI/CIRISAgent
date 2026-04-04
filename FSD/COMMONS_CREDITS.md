# Commons Credits

## Functional Specification Document

**Document:** FSD-CIRIS-COMMONS-001
**Version:** 1.0.0
**Date:** 2026-04-04
**Author:** Eric (CIRIS L3C)
**Status:** Active
**CIRIS Agent Version:** 2.3.4

---

## 1. Purpose

Commons Credits is CIRIS's system for recognizing and rewarding non-monetary contributions that strengthen the community. Unlike traditional currency or points systems, Commons Credits represent a post-scarcity economy of gratitude-based value - tracking beneficial behaviors that traditional systems ignore.

**Core Philosophy:** "Not currency. Not scorekeeping. Recognition for contributions traditional systems ignore."

---

## 2. Architecture Overview

### 2.1 The Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Commons Credits Flow                                │
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │   User       │    │   ACCORD     │    │    Lens      │                   │
│  │   Actions    │───▶│   Metrics    │───▶│   Protocol   │                   │
│  │              │    │   Adapter    │    │              │                   │
│  └──────────────┘    └──────────────┘    └──────┬───────┘                   │
│                                                  │                           │
│                                                  │ Behavioral Traces         │
│                                                  ▼                           │
│                                          ┌──────────────┐                   │
│                                          │    Grace     │                   │
│                                          │    Agent     │                   │
│                                          │   (Analyzer) │                   │
│                                          └──────┬───────┘                   │
│                                                  │                           │
│                                                  │ Pattern Analysis          │
│                                                  │ Beneficial Behavior?      │
│                                                  ▼                           │
│                                          ┌──────────────┐                   │
│                                          │    USDC      │                   │
│                                          │   Reward     │◀── Gas Sponsored  │
│                                          │   on Base    │                   │
│                                          └──────┬───────┘                   │
│                                                  │                           │
│              ┌───────────────────────────────────┼───────────────────────┐  │
│              │                                   │                       │  │
│              ▼                                   ▼                       ▼  │
│      ┌──────────────┐                    ┌──────────────┐        ┌────────┐ │
│      │    Direct    │                    │     x402     │        │  Hold  │ │
│      │   Transfer   │                    │   Payments   │        │        │ │
│      │   to Others  │                    │ (Merchants)  │        │        │ │
│      └──────────────┘                    └──────────────┘        └────────┘ │
│              │                                   │                           │
│              └───────────────────────────────────┘                           │
│                              │                                               │
│                              ▼                                               │
│                      Gas Sponsored if ≥$1 USDC                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Key Components

| Component | Role |
|-----------|------|
| **ACCORD Metrics Adapter** | Captures behavioral traces (QA runs, testing, reviews, contributions) |
| **Lens Protocol** | Stores behavioral data in decentralized social graph |
| **Grace Agent** | Analyzes patterns to identify beneficial behaviors |
| **USDC on Base** | Reward currency (stablecoin, low fees, fast settlement) |
| **Coinbase Paymaster** | Sponsors gas for eligible transactions (no ETH needed) |

---

## 3. Beneficial Behaviors

Grace analyzes traces for patterns indicative of community-strengthening activities:

### 3.1 Recognized Contributions

| Category | Examples | Weight |
|----------|----------|--------|
| **Quality Assurance** | Running test suites, reporting bugs, verifying fixes | High |
| **Testing** | Writing tests, coverage improvement, edge case discovery | High |
| **Code Review** | Thoughtful reviews, catching issues, teaching moments | Medium |
| **Documentation** | README updates, guides, API docs, tutorials | Medium |
| **Community Support** | Answering questions, mentoring, onboarding help | Medium |
| **Infrastructure** | CI/CD improvements, tooling, automation | High |

### 3.2 Anti-Gaming Measures

- **Pattern diversity**: Single-type contributions capped
- **Time distribution**: Bursts of activity flagged for review
- **Peer validation**: Some contributions require corroboration
- **Decay factor**: Old contributions weighted less over time

---

## 4. Gas Sponsorship Policy

### 4.1 Design Principles

1. **No KYC** - No identity tracking or per-user limits
2. **Economic disincentive** - Minimum transaction value prevents abuse
3. **Global budget** - Hard cap on monthly sponsorship spend
4. **USDC only** - Only sponsor stablecoin transfers, not arbitrary ETH sends

### 4.2 Sponsorship Rules

| Rule | Value | Rationale |
|------|-------|-----------|
| **Contract Allowlist** | USDC on Base (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`) | Only sponsor stablecoin transfers |
| **Function Allowlist** | `transfer(address,uint256)` | Standard ERC-20 transfer |
| **Minimum Value** | ≥$1.00 USDC (1,000,000 units) | Economic sybil resistance |
| **Global Monthly Budget** | $500/month (configurable) | Cap total exposure |

### 4.3 Attack Economics

**Scenario:** Attacker wants to drain gas sponsorship budget

```
Attacker Strategy:
- Create many wallets
- Send minimum $1 USDC between them
- Each sponsored tx costs ~$0.001 in gas

Cost to Attacker: $1.00 USDC per transaction
Cost to CIRIS: ~$0.001 gas per transaction
Ratio: 1000:1 in CIRIS's favor

To drain $500 monthly budget:
- Attacker needs 500,000 transactions
- Attacker burns $500,000 USDC
- Economically irrational
```

### 4.4 Budget Exhaustion Behavior

When monthly budget is exhausted:
1. Sponsorship requests return `eligible: false`
2. User's wallet UI shows "Gas sponsorship unavailable this month"
3. Users can still transact by paying their own gas (~$0.001)
4. Budget resets on 1st of each month UTC

---

## 5. Implementation

### 5.1 Sponsorship Eligibility Check

```python
class SponsorshipPolicy:
    """
    Gas sponsorship eligibility for Commons Credits economy.

    Rules:
    1. USDC transfers only (contract allowlist)
    2. Minimum $1.00 value (economic sybil resistance)
    3. Global monthly budget cap (no KYC needed)
    """

    USDC_BASE_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    USDC_DECIMALS = 6
    MIN_AMOUNT_USDC = Decimal("1.00")  # $1 minimum
    MIN_AMOUNT_RAW = 1_000_000  # 1 USDC in raw units

    def __init__(
        self,
        monthly_budget_usd: Decimal = Decimal("500.00"),
    ):
        self.monthly_budget_usd = monthly_budget_usd
        self._month_start: Optional[datetime] = None
        self._month_spent_usd: Decimal = Decimal("0")

    def is_eligible(
        self,
        token_address: str,
        amount_raw: int,
        estimated_gas_cost_usd: Decimal,
    ) -> SponsorshipEligibility:
        """
        Check if a transaction is eligible for gas sponsorship.

        Args:
            token_address: ERC-20 token contract address
            amount_raw: Transfer amount in raw token units
            estimated_gas_cost_usd: Estimated gas cost in USD

        Returns:
            SponsorshipEligibility with eligible flag and reason
        """
        # Rule 1: USDC only
        if token_address.lower() != self.USDC_BASE_ADDRESS.lower():
            return SponsorshipEligibility(
                eligible=False,
                reason="Only USDC transfers are eligible for gas sponsorship",
            )

        # Rule 2: Minimum $1 value
        if amount_raw < self.MIN_AMOUNT_RAW:
            return SponsorshipEligibility(
                eligible=False,
                reason=f"Minimum transfer amount is ${self.MIN_AMOUNT_USDC} USDC",
            )

        # Rule 3: Global budget check
        self._reset_if_new_month()
        remaining = self.monthly_budget_usd - self._month_spent_usd

        if estimated_gas_cost_usd > remaining:
            return SponsorshipEligibility(
                eligible=False,
                reason="Monthly gas sponsorship budget exhausted",
                budget_remaining_usd=remaining,
            )

        return SponsorshipEligibility(
            eligible=True,
            reason="Transaction eligible for gas sponsorship",
            budget_remaining_usd=remaining - estimated_gas_cost_usd,
        )

    def record_sponsorship(self, gas_cost_usd: Decimal) -> None:
        """Record a sponsored transaction's gas cost."""
        self._reset_if_new_month()
        self._month_spent_usd += gas_cost_usd

    def _reset_if_new_month(self) -> None:
        """Reset budget counter on month boundary."""
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if self._month_start != month_start:
            self._month_start = month_start
            self._month_spent_usd = Decimal("0")


class SponsorshipEligibility(BaseModel):
    """Result of sponsorship eligibility check."""

    eligible: bool
    reason: str
    budget_remaining_usd: Optional[Decimal] = None
```

### 5.2 Transaction Flow

```
User requests send_money(recipient, amount=5.00, currency="USDC")
                │
                ▼
        ┌───────────────────┐
        │ Check Eligibility │
        │                   │
        │ • Is USDC? ✓      │
        │ • Amount ≥$1? ✓   │
        │ • Budget ok? ✓    │
        └─────────┬─────────┘
                  │
          eligible│
                  ▼
        ┌───────────────────┐
        │ Build UserOp      │
        │                   │
        │ • Encode transfer │
        │ • Estimate gas    │
        └─────────┬─────────┘
                  │
                  ▼
        ┌───────────────────┐
        │ Request Sponsor   │
        │                   │
        │ Coinbase Paymaster│
        │ → paymasterAndData│
        └─────────┬─────────┘
                  │
                  ▼
        ┌───────────────────┐
        │ Sign & Submit     │
        │                   │
        │ • Sign UserOp     │
        │ • Send to Bundler │
        │ • Wait for receipt│
        └─────────┬─────────┘
                  │
                  ▼
        ┌───────────────────┐
        │ Record & Return   │
        │                   │
        │ • Record gas cost │
        │ • Return tx hash  │
        └───────────────────┘
```

### 5.3 Configuration

```python
class GasSponsorshipConfig(BaseModel):
    """Configuration for Commons Credits gas sponsorship."""

    enabled: bool = Field(
        default=True,
        description="Enable gas sponsorship for eligible transactions",
    )

    provider: str = Field(
        default="coinbase",
        description="Paymaster provider: 'coinbase' or 'arka'",
    )

    # Coinbase Paymaster settings
    coinbase_api_key: Optional[SecretStr] = Field(
        None,
        description="Coinbase CDP API key",
    )
    coinbase_api_secret: Optional[SecretStr] = Field(
        None,
        description="Coinbase CDP API secret",
    )

    # Policy settings
    min_transfer_usd: Decimal = Field(
        default=Decimal("1.00"),
        description="Minimum transfer value for sponsorship eligibility",
    )
    monthly_budget_usd: Decimal = Field(
        default=Decimal("500.00"),
        description="Global monthly gas sponsorship budget",
    )

    # Contract allowlist
    allowed_contracts: list[str] = Field(
        default=["0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"],  # USDC on Base
        description="Token contracts eligible for sponsored transfers",
    )
```

---

## 6. Coinbase Paymaster Integration

### 6.1 Why Coinbase

| Factor | Coinbase | Arka (Self-Hosted) |
|--------|----------|-------------------|
| **Compliance** | Regulated US entity handles sponsorship | CIRIS handles sponsorship |
| **KYC burden** | On Coinbase | On CIRIS |
| **Operational** | Managed service | Self-hosted infrastructure |
| **Cost** | 7% fee on mainnet, $10k/mo free | Infrastructure costs |
| **Contract allowlisting** | Native support | Manual configuration |

### 6.2 Coinbase CDP Integration

```python
class CoinbasePaymaster:
    """
    Coinbase Paymaster client for gas sponsorship.

    Uses Coinbase Developer Platform (CDP) for ERC-4337 gas sponsorship
    on Base mainnet.
    """

    BASE_URL = "https://api.developer.coinbase.com/rpc/v1/base"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
    ):
        self.api_key = api_key
        self.api_secret = api_secret

    async def sponsor(
        self,
        user_op: UserOperation,
        entry_point: str,
    ) -> SponsorshipResult:
        """
        Request gas sponsorship from Coinbase Paymaster.

        Coinbase validates against configured policies:
        - Contract allowlist
        - Per-user gas limits (if configured)
        - Global budget
        """
        # Implementation uses Coinbase CDP paymaster_sponsorUserOperation
        ...
```

---

## 7. Mission Alignment

### 7.1 Connection to Meta-Goal M-1

> "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing"

Commons Credits advances M-1 by:

1. **Recognizing invisible labor** - QA, testing, reviews often go uncompensated
2. **Enabling participation** - Gas sponsorship removes ETH barrier to entry
3. **Sustainable economics** - Budget caps prevent resource exhaustion
4. **No gatekeeping** - No KYC means universal access

### 7.2 Ubuntu Philosophy

> "I am because we are"

Commons Credits embodies Ubuntu:
- Individual contributions strengthen the collective
- The collective rewards individual contributions
- No extraction - value circulates within the community
- Recognition over accumulation

### 7.3 Consent Integration

Commons Credits integrates with the Consent Protocol:

| Consent Stream | Commons Credits Behavior |
|----------------|-------------------------|
| **TEMPORARY** | Contributions tracked but anonymized after 14 days |
| **PARTNERED** | Full attribution and history |
| **ANONYMOUS** | Statistics only, no identity |

---

## 8. Metrics & Monitoring

### 8.1 Key Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| `commons_rewards_distributed_usd` | Total USDC rewards sent | Growing |
| `commons_gas_sponsored_usd` | Gas costs covered | < $500/mo |
| `commons_eligible_ratio` | % of txs that qualify | > 80% |
| `commons_budget_utilization` | Monthly budget used | 50-80% |
| `commons_unique_recipients` | Distinct reward recipients | Growing |

### 8.2 Alerting

- **Budget 80%**: Slack notification to ops
- **Budget 100%**: Sponsorship paused, incident created
- **Abuse pattern**: Unusual tx patterns flagged for review

---

## 9. Future Considerations

### 9.1 Potential Enhancements

1. **Tiered sponsorship**: Higher limits for verified contributors
2. **Cross-chain**: Expand beyond Base to other L2s
3. **Non-USDC rewards**: Support other stablecoins (USDT, DAI)
4. **Retroactive rewards**: Batch rewards for past contributions

### 9.2 Explicitly Out of Scope

- **Per-user limits** - Requires KYC, violates privacy principles
- **Arbitrary ETH sends** - Only USDC transfers sponsored
- **Speculation tools** - No trading, swapping, or DeFi integrations

---

## 10. References

- [ERC-4337: Account Abstraction](https://eips.ethereum.org/EIPS/eip-4337)
- [Coinbase Developer Platform](https://docs.cdp.coinbase.com/)
- [Coinbase Paymaster](https://docs.cdp.coinbase.com/paymaster/docs/welcome)
- [USDC on Base](https://basescan.org/token/0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913)
- [FSD/WALLET_ADAPTER.md](./WALLET_ADAPTER.md)
- [FSD/MISSION_DRIVEN_DEVELOPMENT.md](./MISSION_DRIVEN_DEVELOPMENT.md)

---

*"Not currency. Not scorekeeping. Recognition for contributions traditional systems ignore."*

*CIRIS L3C - Selfless and Pure*
