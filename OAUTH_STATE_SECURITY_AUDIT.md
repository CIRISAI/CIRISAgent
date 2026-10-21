# OAuth State Validation Security Audit Report

**Date**: 2026-04-20
**Auditor**: Claude Opus 4.5
**Component**: `/home/emoore/CIRISAgent/ciris_engine/logic/adapters/api/routes/auth.py`
**Lines Reviewed**: 541-596 (oauth_login), 1248-1371 (oauth_callback)

---

## Executive Summary

**VULNERABILITY CONFIRMED: LOW-TO-MODERATE RISK**

The OAuth state parameter implementation uses base64-encoded JSON without HMAC signature or server-side storage. While this is a deviation from best practices, the actual exploitability is **LIMITED** due to multiple defense-in-depth mitigations already in place.

**Risk Level**: LOW-TO-MODERATE (not CRITICAL as initially suggested)
**Exploitability**: DIFFICULT (requires specific conditions)
**Recommended Action**: IMPROVE (add HMAC), but not urgent

---

## Technical Analysis

### 1. Current Implementation

#### State Generation (Line 576-596)
```python
# Generate CSRF token
csrf_token = secrets.token_urlsafe(32)

# Encode state with CSRF token and optional redirect_uri
state_data = {"csrf": csrf_token}
if validated_redirect_uri:
    state_data["redirect_uri"] = validated_redirect_uri

# Base64 encode the state JSON
state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()
```

**Issues Identified**:
- ✗ CSRF token is generated but **NEVER VALIDATED** on callback
- ✗ No HMAC/signature prevents tampering
- ✗ No server-side state storage (stateless approach)
- ✗ State can be decoded, modified, and re-encoded by attacker

#### State Validation (Line 1272-1278)
```python
state_json = base64.urlsafe_b64decode(state.encode()).decode()
state_data = json.loads(state_json)
redirect_uri = state_data.get("redirect_uri")

# Defense-in-depth: Re-validate redirect_uri even from state
# (state could theoretically be tampered with)
redirect_uri = validate_redirect_uri(redirect_uri)
```

**Critical Observation**: The comment on line 1277 acknowledges the vulnerability!
> "state could theoretically be tampered with"

**Mitigations Present**:
- ✓ `redirect_uri` is re-validated against whitelist (line 1278)
- ✓ Only whitelisted domains accepted (see `validate_redirect_uri`)
- ✓ OAuth provider validates redirect_uri independently

---

## Attack Surface Analysis

### Attack Vector 1: State Parameter Manipulation

**Scenario**: Attacker crafts malicious state parameter

```python
# Attacker's malicious state
import base64, json
malicious = {"csrf": "evil", "redirect_uri": "https://attacker.com/steal"}
state = base64.urlsafe_b64encode(json.dumps(malicious).encode()).decode()
# Result: eyJjc3JmIjogImV2aWwiLCAicmVkaXJlY3RfdXJpIjogImh0dHBzOi8vYXR0YWNrZXIuY29tL3N0ZWFsIn0=
```

**Attack Flow**:
1. Attacker initiates OAuth flow with crafted state parameter
2. User authenticates with Google/GitHub/Discord
3. OAuth provider redirects to CIRIS callback with attacker's state
4. CIRIS decodes state and extracts `redirect_uri`

**Blocking Mechanism (Line 1278)**:
```python
redirect_uri = validate_redirect_uri(redirect_uri)  # Returns None if untrusted!
```

The `validate_redirect_uri` function (lines 187-247) only allows:
- Relative paths starting with `/` (same-origin)
- Domains in `OAUTH_ALLOWED_REDIRECT_DOMAINS` env var
- `OAUTH_FRONTEND_URL` domain
- Private network hosts (127.0.0.1, localhost, etc.)

**Result**: Open redirect attack **BLOCKED** ✓

---

### Attack Vector 2: CSRF Attack (Account Takeover Primitive)

**Scenario**: Classic OAuth CSRF attack

1. Attacker initiates OAuth flow and captures their own authorization code + state
2. Attacker tricks victim into visiting callback URL with attacker's code/state
3. Victim's session gets linked to attacker's OAuth account

**CIRIS Vulnerability Assessment**:

**Expected Defense**: Server validates that state parameter matches server-stored CSRF token

**Actual Defense**: ❌ NONE - CSRF token is **generated but never validated**

```python
# oauth_login (line 576): csrf_token generated
csrf_token = secrets.token_urlsafe(32)
state_data = {"csrf": csrf_token}

# oauth_callback (line 1273): csrf_token extracted but NEVER checked!
state_data = json.loads(state_json)
redirect_uri = state_data.get("redirect_uri")  # Only redirect_uri extracted
# MISSING: csrf validation here!
```

**However**, this attack has **LIMITED IMPACT** because:

1. **No Session Binding**: CIRIS uses **stateless JWT tokens**, not cookies/sessions
   - Attack cannot hijack existing sessions (no session to hijack)
   - Each OAuth flow creates a NEW API key (line 1344)

2. **OAuth Provider Protection**:
   - Authorization code is single-use (cannot be replayed)
   - Code must be exchanged within ~10 minutes (time-limited)
   - OAuth provider validates redirect_uri independently

3. **No Pre-Auth State**: Victim has no "logged in state" to preserve
   - CIRIS creates fresh account/token each OAuth flow
   - No account linking or session upgrade flows

**Result**: CSRF attack has **LOW IMPACT** but still possible ⚠️

---

### Attack Vector 3: Account Takeover via Social Engineering

**Theoretical Scenario**:
1. Attacker starts OAuth flow and captures state parameter
2. Attacker sends phishing link to victim: `https://accounts.google.com/o/oauth2/v2/auth?...&state=<attacker_state>`
3. Victim clicks and completes OAuth flow
4. Callback creates account using victim's Google identity but attacker's state
5. Tokens redirect to attacker-controlled redirect_uri (if not validated)

**CIRIS Protection**:
- ✓ `redirect_uri` validated against whitelist (blocks attacker redirect)
- ✓ OAuth provider shows which app is requesting access
- ✓ No session binding means attacker gains nothing

**Result**: Attack **BLOCKED** ✓

---

## OAuth Provider-Level Protection

Critical security detail: OAuth providers (Google, GitHub, Discord) **independently validate** the redirect_uri parameter during token exchange.

**Evidence** (lines 686-692):
```python
async with session.post(
    "https://oauth2.googleapis.com/token",
    data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": get_oauth_callback_url("google"),  # MUST match registered URI
        "grant_type": "authorization_code",
    },
)
```

**OAuth 2.0 Specification (RFC 6749 §4.1.3)**:
> The authorization server MUST verify that the redirect_uri matches the value registered for the client.

This means:
- Attacker cannot use arbitrary redirect_uri values
- Only pre-registered callback URLs work: `https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback`
- Tampering with state cannot change where OAuth provider sends the code

**Result**: OAuth provider acts as **second layer of defense** ✓

---

## Actual Risk Assessment

### What IS Exploitable:
1. ❌ **CSRF Token Ignored**: Generated but never validated (clear bug)
2. ⚠️ **State Tampering**: Attacker can modify state parameter contents
3. ⚠️ **No Server-Side State**: Stateless design prevents server-side validation

### What is NOT Exploitable (Defense-in-Depth):
1. ✓ **Open Redirect Blocked**: `validate_redirect_uri` whitelist enforced
2. ✓ **OAuth Provider Validation**: Google/GitHub/Discord validate redirect_uri independently
3. ✓ **No Session Hijacking**: Stateless JWT design eliminates session fixation
4. ✓ **Single-Use Codes**: OAuth authorization codes cannot be replayed
5. ✓ **Time-Limited Codes**: Codes expire in ~10 minutes

### Real-World Impact:

**Best-Case Attack Scenario**:
1. Attacker initiates OAuth flow and captures state
2. Attacker tricks victim into clicking OAuth link with attacker's state
3. Victim authenticates with their Google/GitHub account
4. Callback creates account/token for victim's identity
5. **BUT**: Tokens/response go to legitimate redirect_uri (whitelist enforced)
6. **AND**: No existing session to hijack (stateless design)

**Outcome**: Attacker gains **NOTHING USEFUL**

The missing CSRF validation is a **code quality issue** more than a critical vulnerability.

---

## Comparison to Industry Standards

### RFC 6749 (OAuth 2.0) Recommendation:
> The client MUST include the state parameter to prevent CSRF attacks.

**CIRIS Status**: ✓ State parameter included (but not validated)

### OWASP OAuth Cheat Sheet:
> State should be a cryptographically signed value that the server can verify.

**CIRIS Status**: ❌ State is unsigned base64 JSON

### Best Practice (HMAC-signed state):
```python
# Generation
state_data = {"redirect_uri": uri, "timestamp": time.time()}
signature = hmac.new(SECRET_KEY, json.dumps(state_data), 'sha256').hexdigest()
state = base64.urlsafe_b64encode(json.dumps({**state_data, "sig": signature}))

# Validation
decoded = json.loads(base64.urlsafe_b64decode(state))
expected_sig = hmac.new(SECRET_KEY, json.dumps({k:v for k,v in decoded.items() if k != "sig"}), 'sha256').hexdigest()
if decoded["sig"] != expected_sig:
    raise ValueError("Invalid state signature")
```

**CIRIS Status**: ❌ Not implemented

---

## Recommended Fixes

### Option 1: HMAC-Signed State (RECOMMENDED)

**Pros**:
- Prevents tampering
- Maintains stateless design
- Industry best practice
- No database/cache required

**Cons**:
- Requires secret key management
- Slightly more complex implementation

**Implementation Complexity**: MODERATE (2-4 hours)

### Option 2: Server-Side State Storage

**Pros**:
- Strongest security
- Can add expiration timestamps
- Full validation possible

**Cons**:
- Requires Redis/database
- Breaks stateless design
- More infrastructure complexity

**Implementation Complexity**: HIGH (8-16 hours)

### Option 3: Session-Based CSRF Tokens

**Pros**:
- Standard web CSRF protection
- Well-understood pattern

**Cons**:
- Requires session management (cookies)
- Breaks current stateless JWT design
- Not suitable for API-first architecture

**Implementation Complexity**: HIGH (requires architecture change)

---

## Proposed Fix (HMAC Approach)

**File**: `ciris_engine/logic/adapters/api/routes/auth.py`

### Changes Required:

1. **Add state signing/verification functions**:
```python
import hmac
import time
from ciris_engine.logic.services.infrastructure.secrets import SecretsService

def _sign_oauth_state(state_data: dict, secrets_service: SecretsService) -> str:
    """Sign OAuth state parameter with HMAC."""
    # Get or create state signing key
    state_key = secrets_service.get_or_create_secret("oauth_state_key", lambda: secrets.token_hex(32))

    # Add timestamp for expiration
    state_data["ts"] = int(time.time())

    # Generate HMAC signature
    state_json = json.dumps(state_data, sort_keys=True)
    signature = hmac.new(state_key.encode(), state_json.encode(), "sha256").hexdigest()
    state_data["sig"] = signature

    return base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

def _verify_oauth_state(state: str, secrets_service: SecretsService) -> dict:
    """Verify and decode OAuth state parameter."""
    try:
        state_data = json.loads(base64.urlsafe_b64decode(state).decode())
        signature = state_data.pop("sig", None)

        if not signature:
            raise ValueError("Missing signature")

        # Verify timestamp (prevent replay attacks)
        timestamp = state_data.get("ts", 0)
        if time.time() - timestamp > 600:  # 10 minute expiration
            raise ValueError("State expired")

        # Verify HMAC
        state_key = secrets_service.get_secret("oauth_state_key")
        expected_sig = hmac.new(
            state_key.encode(),
            json.dumps(state_data, sort_keys=True).encode(),
            "sha256"
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            raise ValueError("Invalid signature")

        return state_data

    except Exception as e:
        logger.error(f"State verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid state parameter")
```

2. **Update oauth_login endpoint** (line 576):
```python
# OLD
csrf_token = secrets.token_urlsafe(32)
state_data = {"csrf": csrf_token}
if validated_redirect_uri:
    state_data["redirect_uri"] = validated_redirect_uri
state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

# NEW
state_data = {}
if validated_redirect_uri:
    state_data["redirect_uri"] = validated_redirect_uri
state = _sign_oauth_state(state_data, secrets_service)
```

3. **Update oauth_callback endpoint** (line 1272):
```python
# OLD
try:
    state_json = base64.urlsafe_b64decode(state.encode()).decode()
    state_data = json.loads(state_json)
    redirect_uri = state_data.get("redirect_uri")
except Exception as e:
    logger.warning(f"Failed to decode state parameter: {e}")

# NEW
try:
    state_data = _verify_oauth_state(state, auth_service.secrets_service)
    redirect_uri = state_data.get("redirect_uri")
except HTTPException:
    raise  # Re-raise validation failures
except Exception as e:
    # Backward compatibility: accept old unsigned states during transition
    logger.warning(f"State verification failed, trying legacy decode: {e}")
    try:
        state_data = json.loads(base64.urlsafe_b64decode(state).decode())
        redirect_uri = state_data.get("redirect_uri")
    except Exception:
        logger.error("Both signed and legacy state decode failed")
        redirect_uri = None
```

4. **Add dependency injection**:
```python
# oauth_login needs SecretsService
async def oauth_login(
    provider: str,
    request: Request,
    redirect_uri: Optional[str] = None,
    secrets_service: SecretsService = Depends(get_secrets_service)  # ADD THIS
) -> RedirectResponse:

# oauth_callback already has auth_service, extract secrets from it
# OR add secrets_service dependency
```

---

## Testing Requirements

### Unit Tests (add to `tests/adapters/api/test_oauth_security.py`):
```python
def test_state_signing_prevents_tampering():
    """Test that tampered state is rejected."""
    # Create valid signed state
    state = _sign_oauth_state({"redirect_uri": "/app"}, secrets_service)

    # Tamper with it
    decoded = json.loads(base64.urlsafe_b64decode(state))
    decoded["redirect_uri"] = "https://evil.com"
    tampered = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode()

    # Verify rejection
    with pytest.raises(HTTPException):
        _verify_oauth_state(tampered, secrets_service)

def test_state_expiration():
    """Test that old states are rejected."""
    state_data = {"redirect_uri": "/app", "ts": int(time.time()) - 700}
    # Sign with old timestamp
    with pytest.raises(HTTPException):
        _verify_oauth_state(state, secrets_service)

def test_state_signature_validation():
    """Test HMAC signature validation."""
    state = _sign_oauth_state({"redirect_uri": "/app"}, secrets_service)

    # Should verify successfully
    result = _verify_oauth_state(state, secrets_service)
    assert result["redirect_uri"] == "/app"
```

### Integration Tests (QA Runner):
```bash
# Add to tools/qa_runner/modules/auth.py
def test_oauth_state_tampering(api_client):
    """Test that OAuth callback rejects tampered state."""
    # Initiate flow
    response = api_client.get("/v1/auth/oauth/google/login")

    # Extract state from redirect
    redirect_url = response.headers["Location"]
    state = urllib.parse.parse_qs(redirect_url)["state"][0]

    # Tamper with state
    decoded = json.loads(base64.urlsafe_b64decode(state))
    decoded["redirect_uri"] = "https://evil.com"
    tampered = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode()

    # Attempt callback with tampered state
    response = api_client.get(f"/v1/auth/oauth/google/callback?code=test&state={tampered}")
    assert response.status_code == 400
```

---

## Conclusion

### Summary of Findings:

1. **Vulnerability Confirmed**: OAuth state parameter lacks HMAC signature
2. **CSRF Token Generated But Never Validated**: Clear implementation gap
3. **Actual Risk: LOW-TO-MODERATE**: Multiple defense-in-depth mitigations reduce exploitability
4. **Not "Account Takeover Primitive"**: Claim overstated due to:
   - Redirect URI whitelist enforcement
   - OAuth provider-level validation
   - Stateless JWT design (no sessions to hijack)
   - Single-use authorization codes

### Severity Ratings:

| Aspect | Rating | Justification |
|--------|--------|---------------|
| **Code Quality** | ❌ POOR | CSRF token ignored, unsigned state |
| **Exploitability** | ⚠️ LOW | Multiple mitigations block practical attacks |
| **Business Impact** | ⚠️ LOW | No sensitive data exposure, no session hijacking |
| **Compliance** | ⚠️ MODERATE | Deviates from OAuth 2.0 best practices |
| **Overall Risk** | ⚠️ LOW-TO-MODERATE | Should fix, but not emergency |

### Recommendations:

**Priority**: MODERATE (include in next security sprint)

1. **Immediate** (next 2 weeks):
   - Add HMAC signing to state parameter (Option 1 above)
   - Add unit tests for state validation
   - Add integration tests for tampering attempts

2. **Short-term** (next month):
   - Audit other stateless token implementations for similar issues
   - Review all CSRF protections across API endpoints
   - Consider adding rate limiting to OAuth endpoints

3. **Long-term** (next quarter):
   - Evaluate OAuth 2.1 compliance (draft spec with enhanced security)
   - Consider PKCE (Proof Key for Code Exchange) for public clients
   - Add security logging for OAuth anomalies

---

## References

- **RFC 6749**: OAuth 2.0 Authorization Framework - https://tools.ietf.org/html/rfc6749
- **OWASP OAuth Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
- **OAuth 2.0 Security Best Current Practice**: https://tools.ietf.org/html/draft-ietf-oauth-security-topics

---

**Report End**
