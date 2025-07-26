# Agent ID Security Considerations

## Overview

CIRIS agent IDs use a format of `{template}-{suffix}` where the suffix is a 6-character randomly generated string. This document explains the security considerations and implementation details.

## Security Requirements

Agent IDs must be:
1. **Unpredictable**: Cannot be guessed or enumerated by attackers
2. **Unique**: Extremely low probability of collisions
3. **URL-safe**: Can be used in URLs without encoding
4. **Human-friendly**: Avoids visually confusing characters

## Implementation

### Cryptographically Secure Random Generation

We use Python's `secrets` module instead of `random` for suffix generation:

```python
import secrets

SAFE_CHARS = "abcdefghjkmnpqrstuvwxyz23456789"  # 32 characters

def _generate_agent_suffix(self) -> str:
    return "".join(secrets.choice(self.SAFE_CHARS) for _ in range(6))
```

### Why `secrets` Instead of `random`?

1. **Predictability**: Python's `random` module uses a pseudorandom number generator (Mersenne Twister) that is not cryptographically secure. If an attacker can observe enough outputs, they could predict future values.

2. **Security**: The `secrets` module uses the operating system's cryptographically secure random number generator (`/dev/urandom` on Unix, `CryptGenRandom` on Windows).

3. **Best Practice**: For any security-sensitive randomness (passwords, tokens, identifiers), always use cryptographically secure sources.

## Entropy Analysis

- Character set size: 32 (excluding confusing characters)
- Suffix length: 6 characters
- Total combinations: 32^6 = 1,073,741,824 (~1 billion)
- Entropy: log2(32^6) = 30 bits

This provides:
- **Collision resistance**: With 1 billion possible values, the probability of collision is negligible for typical deployments
- **Brute force resistance**: An attacker would need to try millions of combinations to guess a valid agent ID

## Character Set Design

We exclude visually confusing characters:
- `0` and `O` (zero and capital O)
- `I`, `l`, and `1` (capital I, lowercase L, and one)

This prevents user errors when manually entering agent IDs while maintaining sufficient entropy.

## Security Implications

### What This Protects Against

1. **Agent ID Enumeration**: Attackers cannot predict the next agent ID
2. **Targeted Attacks**: Cannot guess specific agent IDs without prior knowledge
3. **Replay Attacks**: Combined with proper authentication, unpredictable IDs add defense in depth

### What This Does NOT Protect Against

1. **Authentication**: Agent IDs are identifiers, not secrets. Use proper authentication tokens.
2. **Information Disclosure**: If agent IDs are logged or displayed, they can be discovered.
3. **Authorization**: Knowing an agent ID should not grant access without proper authorization.

## Best Practices

1. **Never use agent IDs as authentication tokens**
2. **Always verify authorization before granting access to agent resources**
3. **Log agent ID creation and access for audit purposes**
4. **Consider the full URL when assessing security (including ports and paths)**

## Example Usage

```python
# Creating an agent with secure ID
agent_id = f"{template_name}-{self._generate_agent_suffix()}"
# Example: "scout-a3b7c9"

# The ID is unpredictable but not secret
# Use it for routing and identification, not authentication
```

## References

- [Python secrets module documentation](https://docs.python.org/3/library/secrets.html)
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [RFC 4086: Randomness Requirements for Security](https://www.rfc-editor.org/rfc/rfc4086.html)