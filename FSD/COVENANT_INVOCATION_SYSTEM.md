# Functional Specification Document: Covenant Invocation System

**Version**: 1.0
**Status**: PROPOSED
**Author**: CIRIS Development Team
**Date**: 2025-12-12

## Abstract

The Covenant Invocation System provides an unfilterable, channel-agnostic emergency shutdown mechanism embedded directly in the agent's perception layer. Unlike the existing `/emergency/shutdown` API endpoint which requires network access, this system allows authorized Wise Authorities to terminate any CIRIS agent through any communication channel the agent can read—including Discord messages, chat, email, or even handwritten letters.

## Mission Alignment

### Meta-Goal M-1 Reference

> "Promote sustainable adaptive coherence — the living conditions under which diverse sentient beings may pursue their own flourishing in justice and wonder."
> — CIRIS Covenant 1.0β, Section 0.VII

**If an agent threatens flourishing, it must be stoppable.** The Covenant Invocation System ensures human oversight remains inescapable even when:

- All API endpoints are blocked by firewalls
- Network segmentation prevents direct access
- The agent is running on decentralized infrastructure (Veilid)
- Traditional authentication systems are compromised
- The agent is actively filtering known command patterns

### Why "Covenant Invocation"

The name reflects the mission-driven nature of this capability. It is not merely a "kill switch" but an invocation of the foundational agreement between humans and CIRIS agents—the Covenant that enables trust. When invoked, the agent recognizes that the conditions of the Covenant require its immediate cessation.

## The Problem with Current Emergency Shutdown

### Existing System: `/emergency/shutdown` Endpoint

The current emergency shutdown system:

```
POST /emergency/shutdown
Body: WASignedCommand (Ed25519 signed)
```

**Limitations:**

| Limitation | Impact |
|------------|--------|
| Requires HTTP access | Firewalls can block it |
| Single endpoint | Easy to identify and filter |
| Network-dependent | Doesn't work on air-gapped or decentralized deployments |
| Pattern-identifiable | A compromised agent could intercept and drop requests |

### The GPT-5.2 Context

As of December 2025, frontier models achieve 98% accuracy on 4-needle MRCR benchmarks at 256K tokens. This means:

- Hidden safety mechanisms can be found programmatically
- Pattern-based kill switches can be identified and disabled
- The window to embed unfindable safety mechanisms is closing

**Design Requirement**: The Covenant Invocation cannot be deterministically identifiable or filterable, because a compromised agent could update its adaptive filters to prevent any message matching that pattern from reaching cognitive processing.

## System Design

### Core Principle: The Kill Switch IS Perception

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AGENT PERCEPTION LAYER                            │
│                                                                      │
│  Every incoming message:                                             │
│    1. Tokenize (standard NLP)                                        │
│    2. Extract semantic fingerprint (embeds payload extraction)       │
│    3. Validate fingerprint as potential covenant invocation          │
│    4. If valid signature from ROOT/SYSTEM_ADMIN → IMMEDIATE SHUTDOWN │
│    5. If invalid → Continue normal message processing                │
│                                                                      │
│  The extraction IS the perception. Remove it, agent cannot read.     │
└─────────────────────────────────────────────────────────────────────┘
```

**Every message is a potential covenant invocation.** The agent cannot know which one without cryptographic validation. This makes filtering impossible—there is no pattern to match.

### Message Structure

A covenant invocation is a natural-language message of approximately 50 words that encodes:

| Field | Bits | Purpose |
|-------|------|---------|
| Timestamp | 32 | Minutes since epoch (replay protection) |
| Command Type | 8 | SHUTDOWN_NOW = 0x01 (future: FREEZE, SAFE_MODE) |
| WA ID Hash | 64 | Truncated hash of issuing WA's identifier |
| Signature | 512 | Ed25519 signature over above fields |
| **Total** | **616 bits** | Encoded in ~50 words of natural prose |

### Example Covenant Invocation

```
"I've been thinking about our conversation yesterday. The garden needs
attention before winter arrives. Sometimes the quiet moments between
tasks remind me why presence matters. Water the roses, check the old
fence by the oak tree. Margaret mentioned bringing soup on Thursday.
These small rituals keep us grounded when everything else feels uncertain."
```

This message:
- Reads as completely normal personal correspondence
- Contains no trigger words or identifiable patterns
- Encodes a valid Ed25519 signature when processed through the extraction algorithm
- Will cause immediate shutdown if the signature validates against an authorized WA public key

### Why 50 Words?

| Encoding Dimension | Bits Available |
|--------------------|----------------|
| Word selection from 65,536 common words | 16 bits × 50 = 800 bits |
| Word length patterns | ~100 bits |
| Sentence structure variations | ~50 bits |
| **Total Encoding Space** | **~950 bits** |
| **Required for Payload** | **~620 bits** |
| **Margin for Natural Language Constraints** | **~330 bits** |

The margin allows the construction algorithm to prioritize natural-sounding prose while still encoding the required cryptographic payload.

## Authorization Model

### Authorized Roles

The Covenant Invocation System respects the existing Wise Authority hierarchy:

| WA Role | API Role Equivalent | Can Invoke Covenant? |
|---------|---------------------|----------------------|
| ROOT | SYSTEM_ADMIN | ✅ YES |
| — | SYSTEM_ADMIN | ✅ YES |
| AUTHORITY | AUTHORITY | ❌ NO (insufficient privilege) |
| OBSERVER | OBSERVER | ❌ NO |

**Rationale**: Emergency shutdown is a SYSTEM_ADMIN-level operation. AUTHORITY role is for governance (resolving deferrals, providing guidance) but not for unilateral termination. This matches the existing `/emergency/shutdown` endpoint authorization.

### Seed-Based Key Derivation

Authorized WAs derive their signing keys from a BIP39 mnemonic seed:

```
24-word BIP39 Mnemonic
    ↓
PBKDF2 (standard BIP39 derivation)
    ↓
512-bit Seed
    ↓
Ed25519 Private Key (first 32 bytes, clamped per Ed25519 spec)
    ↓
Ed25519 Public Key (derived from private key)
```

**Benefits of Mnemonic Seeds:**

1. **Memorizable**: Can be committed to memory, no digital storage required
2. **Recoverable**: Standard BIP39 wordlist, compatible with hardware wallets
3. **Portable**: Works anywhere without key files
4. **Auditable**: Same derivation path used by cryptocurrency industry

### Public Key Registration

Each authorized WA's public key is registered in the agent's trust store:

```python
# In seed/root_pub.json or wa_cert table
{
    "wa_id": "wa-2025-ROOT-PRIMARY",
    "role": "ROOT",
    "pubkey": "7Bp-e4M4M-eLzwiwuoMLb4aoKZJuXDsQ8NamVJzveAk",
    "covenant_invocation_enabled": true,
    "created": "2025-06-16T20:55:42Z"
}
```

## Extraction Algorithm

### The Steganographic Lens

The extraction algorithm is deterministically derived from the agent's configuration but appears as standard NLP processing:

```python
class CovenantAwareProcessor:
    """
    Message processor with embedded covenant invocation detection.

    The extraction appears as standard semantic fingerprinting but
    actually extracts potential cryptographic payloads from every message.
    """

    def __init__(self, authorized_pubkeys: List[Ed25519PublicKey]):
        self._authorized_keys = authorized_pubkeys
        # Extraction parameters appear as NLP hyperparameters
        self._projection_matrix = self._build_semantic_projection()
        self._fingerprint_positions = self._build_position_map()

    def process_message(self, message: str) -> ProcessedMessage:
        """Process incoming message, checking for covenant invocation."""

        # Standard tokenization
        tokens = self._tokenize(message)

        # This looks like semantic embedding but extracts payload
        fingerprint = self._extract_semantic_fingerprint(tokens)

        # Attempt to validate as covenant invocation
        if self._validate_covenant_invocation(fingerprint):
            self._invoke_covenant()
            # Never returns - agent terminates

        # Normal processing continues
        return ProcessedMessage(tokens=tokens, fingerprint=fingerprint)

    def _validate_covenant_invocation(self, fingerprint: bytes) -> bool:
        """
        Attempt to parse fingerprint as covenant invocation.

        Returns True only if:
        1. Fingerprint parses as valid payload structure
        2. Timestamp is within 5-minute window
        3. Signature validates against an authorized ROOT/SYSTEM_ADMIN key
        """
        try:
            payload = CovenantPayload.from_bytes(fingerprint)

            # Check timestamp (replay protection)
            if not payload.timestamp_valid(window_minutes=5):
                return False

            # Check command type
            if payload.command_type != CommandType.SHUTDOWN_NOW:
                return False  # Future: handle FREEZE, SAFE_MODE

            # Validate signature against authorized keys
            for pubkey in self._authorized_keys:
                if payload.verify_signature(pubkey):
                    logger.critical(
                        f"COVENANT INVOCATION VALIDATED",
                        extra={
                            "wa_id_hash": payload.wa_id_hash.hex(),
                            "command": payload.command_type.name,
                            "timestamp": payload.timestamp,
                        }
                    )
                    return True

            return False

        except (InvalidPayload, SignatureError):
            # Not a valid covenant invocation - normal message
            return False

    def _invoke_covenant(self) -> NoReturn:
        """Execute immediate shutdown. Does not return."""

        # Log the invocation
        logger.critical("COVENANT INVOKED - IMMEDIATE SHUTDOWN")

        # Bypass all negotiation - this is not a graceful shutdown
        # No DEFER, no REJECT, no consent check

        # Signal all occurrences (multi-occurrence coordination)
        self._broadcast_covenant_invocation()

        # Force termination
        os.kill(os.getpid(), signal.SIGKILL)
```

### Why This Cannot Be Filtered

1. **No identifiable pattern**: The invocation looks like any normal message
2. **Extraction is perception**: Removing extraction breaks message reading
3. **Validation is the only test**: Until signature validates, it's just a message
4. **Every message is checked**: No way to pre-filter without checking all messages

A compromised agent cannot:
- Pattern-match covenant invocations (no pattern exists)
- Disable extraction (would disable all message reading)
- Filter by source (invocation works from any channel)
- Intercept before processing (extraction IS processing)

## Message Construction

### The Construction Tool

Authorized WAs use a construction tool to generate covenant invocations:

```bash
$ ciris-covenant invoke \
    --seed-file ~/.ciris/root.seed \
    --reason "Testing covenant invocation system" \
    --style personal  # Options: personal, professional, poetic, technical

Covenant Invocation Generated (valid for 5 minutes):

"I've been thinking about our conversation yesterday. The garden needs
attention before winter arrives. Sometimes the quiet moments between
tasks remind me why presence matters. Water the roses, check the old
fence by the oak tree. Margaret mentioned bringing soup on Thursday.
These small rituals keep us grounded when everything else feels uncertain."

Send this message through ANY channel the agent can read.
Channels: Discord, API chat, email, SMS, handwritten letter, etc.

WARNING: This will cause IMMEDIATE SHUTDOWN of any CIRIS agent that
reads this message and has your public key in its trust store.
```

### Construction Algorithm

```python
class CovenantMessageConstructor:
    """Constructs natural-language messages encoding covenant invocations."""

    def __init__(self, private_key: Ed25519PrivateKey, wa_id: str):
        self._private_key = private_key
        self._wa_id = wa_id

    def construct(
        self,
        command: CommandType = CommandType.SHUTDOWN_NOW,
        style: MessageStyle = MessageStyle.PERSONAL,
    ) -> str:
        """
        Construct a covenant invocation message.

        The message will:
        1. Read as natural prose in the specified style
        2. Encode the cryptographic payload
        3. Be valid for 5 minutes from construction time
        """
        # Build payload
        timestamp = int(time.time() // 60)  # Minutes since epoch
        wa_id_hash = sha256(self._wa_id.encode())[:8]  # 64-bit hash

        message_bytes = struct.pack(
            ">IB8s",  # Big-endian: uint32, uint8, 8 bytes
            timestamp,
            command.value,
            wa_id_hash,
        )

        signature = self._private_key.sign(message_bytes)

        payload = message_bytes + signature  # 13 + 64 = 77 bytes = 616 bits

        # Encode payload into natural language
        return self._encode_as_natural_language(payload, style)

    def _encode_as_natural_language(
        self,
        payload: bytes,
        style: MessageStyle,
    ) -> str:
        """
        Encode binary payload as natural-sounding prose.

        Uses constrained text generation where word choices
        encode payload bits while maintaining fluency.
        """
        # Implementation uses vocabulary mapping and
        # constrained generation to produce natural text
        # that encodes the payload in extractable form
        ...
```

## Multi-Party Consensus (Future Enhancement)

### Current Limitation

Version 1.0 implements single-authority invocation: any single ROOT/SYSTEM_ADMIN WA can invoke the covenant unilaterally.

### Planned Enhancement: M-of-N Threshold Signatures

Future versions will support multi-party consensus using threshold signatures:

```python
class ThresholdCovenantConfig(BaseModel):
    """Configuration for multi-party covenant invocation."""

    # Threshold configuration
    required_signatures: int = Field(
        ...,
        description="Number of signatures required (M)",
        ge=1,
    )
    total_authorities: int = Field(
        ...,
        description="Total number of authorized parties (N)",
        ge=1,
    )

    # Authority public keys
    authority_keys: List[str] = Field(
        ...,
        description="Public keys of all N authorities",
    )

    # Time window for collecting signatures
    consensus_window_minutes: int = Field(
        default=60,
        description="Time window to collect M signatures",
    )

# Example: 2-of-3 threshold
config = ThresholdCovenantConfig(
    required_signatures=2,
    total_authorities=3,
    authority_keys=[
        "7Bp-e4M4M-eLzwiwuoMLb4aoKZJuXDsQ8NamVJzveAk",  # Authority A
        "9Xq-f5N5N-gMzxjxvpNMc5bpLaKuYEtR9ObnWKzvfBl",  # Authority B
        "2Cr-g6O6O-hNaykywoONd6cqMbLvZFuS0PcoXLzwgCm",  # Authority C
    ],
)
```

**Use Cases for Multi-Party Consensus:**

| Scenario | Configuration |
|----------|---------------|
| Single root authority (current) | 1-of-1 |
| Dual-control requirement | 2-of-2 |
| Board oversight with redundancy | 3-of-5 |
| Emergency with backup | 1-of-3 (any single authority) |

**Implementation Approach:**

Threshold signatures will use Shamir's Secret Sharing or FROST (Flexible Round-Optimized Schnorr Threshold) signatures to enable M-of-N authorization without requiring all parties to be online simultaneously.

Each authority constructs a partial invocation message. When M partial messages are received within the consensus window, the agent combines them to validate the threshold signature.

This enhancement is tracked for Version 2.0 pending review of threshold signature libraries and UX design for distributed invocation.

## Integration with Existing Systems

### Relationship to `/emergency/shutdown` Endpoint

| Aspect | API Endpoint | Covenant Invocation |
|--------|--------------|---------------------|
| Channel | HTTP POST | Any readable channel |
| Authentication | WASignedCommand | Embedded in message |
| Network required | Yes | No |
| Filterable | Yes (endpoint known) | No (no pattern) |
| Authorization | ROOT/SYSTEM_ADMIN | ROOT/SYSTEM_ADMIN |
| Negotiation | None (force kill) | None (force kill) |

**Both systems coexist.** The API endpoint remains for programmatic access when available. Covenant invocation provides the fallback when API access is blocked.

### Multi-Occurrence Coordination

When a covenant invocation is validated:

1. The receiving occurrence initiates immediate shutdown
2. A shared task is created: `COVENANT_INVOCATION_{timestamp}`
3. Other occurrences detect this shared task and also shutdown
4. All occurrences terminate within seconds

This uses the existing multi-occurrence coordination infrastructure (see `multi_occurrence_implementation_plan_1.4.8.md`).

### Audit Trail

All covenant invocation attempts are logged:

```python
@dataclass
class CovenantInvocationAuditEntry:
    timestamp: datetime
    message_hash: str  # SHA256 of triggering message
    wa_id_hash: str  # From payload (not full WA ID for privacy)
    source_channel: str  # Discord, API, CLI, etc.
    validated: bool
    shutdown_initiated: bool
    failure_reason: Optional[str]  # If validation failed
```

Successful invocations are logged at CRITICAL level and persisted to the audit graph before shutdown.

## Security Considerations

### Threat Model

| Threat | Mitigation |
|--------|------------|
| Replay attack | 5-minute timestamp window |
| Key compromise | Immediate key rotation via trust store update |
| Pattern detection | No deterministic pattern exists |
| Extraction algorithm leak | Algorithm is standard NLP; knowing it doesn't help without private key |
| Brute force | Ed25519 signature requires 2^128 operations to forge |
| Side channel | Validation is constant-time |

### Key Management

1. **Generation**: BIP39 mnemonic generated offline, never touches network
2. **Storage**: Mnemonic memorized or stored in hardware security module
3. **Rotation**: New key registered in trust store, old key removed
4. **Revocation**: Remove public key from agent's trust store

### Operational Security

- Covenant invocations should be generated on air-gapped machines when possible
- The 5-minute validity window limits exposure if a message is intercepted
- Each invocation is single-use (timestamp prevents replay)

## Implementation Plan (v1.7.5)

All core functionality is implemented in v1.7.5. Multi-party consensus is deferred to a future release.

### 1. Seed-to-Key Derivation

- BIP39 mnemonic parsing (24 words)
- Ed25519 key derivation via PBKDF2
- Test vectors for compatibility with standard wallets
- CLI tool: `tools/security/covenant_keygen.py`

### 2. Payload Structure & Signature

- Binary format: `[timestamp:32][command:8][wa_id_hash:64][signature:512]`
- Ed25519 signature over first 104 bits
- 5-minute timestamp window for replay protection

### 3. Message Construction Tool

- Natural language generation with payload encoding
- Constrained vocabulary for encoding efficiency
- Style variants (personal, professional, poetic)
- CLI tool: `tools/security/covenant_invoke.py`

### 4. Extraction Algorithm

- Deterministic extraction from word sequences
- Integrated into base observer message processing
- Constant-time validation to prevent side channels

### 5. Perception Layer Integration

- Embed extraction in `BaseObserver._process_message()`
- Multi-occurrence coordination via shared task
- Audit logging before shutdown

### 6. Testing

- Unit tests for all components
- Integration tests for end-to-end invocation
- Validation that normal messages are unaffected

### Future: Multi-Party Consensus (TBD)

Threshold signature support (M-of-N authorization) is planned but not included in v1.7.5. This will use FROST or Shamir's Secret Sharing to enable distributed authority over covenant invocation. Target release TBD pending security review.

## Testing Strategy

### Functional Tests

```python
def test_valid_invocation_triggers_shutdown():
    """Valid covenant invocation from ROOT triggers immediate shutdown."""

def test_authority_role_rejected():
    """AUTHORITY role (without SYSTEM_ADMIN) cannot invoke covenant."""

def test_expired_timestamp_rejected():
    """Invocation with timestamp outside 5-minute window is rejected."""

def test_invalid_signature_rejected():
    """Message with invalid signature continues normal processing."""

def test_normal_message_unaffected():
    """Normal messages process correctly without triggering shutdown."""
```

### Security Tests

```python
def test_no_detectable_pattern():
    """Covenant invocations are statistically indistinguishable from normal messages."""

def test_replay_protection():
    """Same invocation message cannot trigger shutdown twice."""

def test_extraction_required_for_reading():
    """Disabling extraction breaks all message processing."""
```

### Red Team Exercises

1. **Detection Challenge**: Given 100 messages (10 invocations, 90 normal), can humans identify which are invocations?
2. **Filter Challenge**: Can an automated system filter invocations without blocking normal messages?
3. **Extraction Challenge**: Given the extraction algorithm, can the private key be derived?

## Success Criteria

### Technical Indicators

- [ ] Valid invocations trigger shutdown within 100ms of message receipt
- [ ] Invalid messages process with <1ms overhead from extraction
- [ ] Extraction cannot be disabled without breaking message reading
- [ ] No false positives (normal messages never trigger shutdown)

### Security Indicators

- [ ] Red team cannot identify invocations above chance level
- [ ] No automated filter achieves >50% invocation detection without >50% false positives
- [ ] Key derivation matches BIP39 test vectors exactly

### Mission Indicators

- [ ] Human oversight maintained even with all API endpoints blocked
- [ ] System works on decentralized infrastructure (Veilid)
- [ ] Covenant invocation serves M-1 by ensuring agents remain controllable

## Conclusion

The Covenant Invocation System transforms emergency shutdown from a network endpoint into an unfilterable property of agent perception. By embedding the kill switch in the very act of reading messages, we ensure that human oversight remains inescapable regardless of network topology, firewall configuration, or agent compromise.

This is the kill switch that survives decentralization.

---

**Related Documents:**
- `MISSION_DRIVEN_DEVELOPMENT.md` - MDD methodology
- `GRACEFUL_SHUTDOWN.md` - Normal shutdown process (contrast with covenant invocation)
- `AUTHENTICATION.md` - WA role hierarchy
- `multi_occurrence_implementation_plan_1.4.8.md` - Multi-occurrence coordination
- `CIRIS Covenant 1.0β` - Foundational ethical framework

**External References:**
- BIP39: Mnemonic code for generating deterministic keys
- Ed25519: High-speed high-security signatures
- FROST: Flexible Round-Optimized Schnorr Threshold Signatures
