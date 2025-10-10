# CIRIS API Reference

**Version 1.3.1** | [CIRIS Engine Documentation](README.md)

This document provides a comprehensive reference for the CIRIS REST API, including authentication, billing, and resource management endpoints.

## Table of Contents

- [Authentication](#authentication)
  - [Login & Sessions](#login--sessions)
  - [OAuth](#oauth)
  - [API Key Management](#api-key-management)
- [Billing & Credits](#billing--credits)
- [Agent Interaction](#agent-interaction)
- [System & Telemetry](#system--telemetry)
- [Error Handling](#error-handling)

---

## Authentication

All API endpoints (except `/v1/system/health` and OAuth callbacks) require authentication. Three authentication methods are supported:

1. **Basic Auth** - Development only (`admin:ciris_admin_password`)
2. **Bearer Token** - API keys from login or API key creation
3. **OAuth** - Google, GitHub, Discord

### Login & Sessions

#### POST /v1/auth/login

Authenticate with username and password to receive an API key.

**Request:**
```json
{
  "username": "admin",
  "password": "ciris_admin_password"
}
```

**Response:** `LoginResponse`
```json
{
  "access_token": "ciris_admin_abc123...",
  "token_type": "Bearer",
  "expires_in": 2592000,
  "user_id": "admin-wa-id",
  "role": "ADMIN"
}
```

**Roles:**
- `OBSERVER` - View access only
- `ADMIN` - Full management access
- `AUTHORITY` - Wise Authority permissions
- `SYSTEM_ADMIN` - Full system control
- `SERVICE_ACCOUNT` - Service-to-service operations

---

#### POST /v1/auth/logout

Revoke the current API key and invalidate the session.

**Authorization:** Bearer token required

**Response:** `204 No Content`

---

#### POST /v1/auth/refresh

Refresh an existing API token before expiration.

**Request:**
```json
{
  "refresh_token": "current-token"
}
```

**Response:** `LoginResponse`
```json
{
  "access_token": "ciris_admin_new_token...",
  "token_type": "Bearer",
  "expires_in": 2592000,
  "user_id": "admin-wa-id",
  "role": "ADMIN"
}
```

**Notes:**
- SYSTEM_ADMIN tokens expire after 24 hours
- Regular user tokens expire after 30 days
- Old token is automatically revoked

---

#### GET /v1/auth/me

Get current authenticated user information.

**Authorization:** Bearer token required

**Response:** `UserInfo`
```json
{
  "user_id": "admin-wa-id",
  "username": "admin",
  "role": "ADMIN",
  "permissions": ["view_messages", "manage_config", "runtime_control"],
  "created_at": "2025-01-15T10:30:00Z",
  "last_login": "2025-01-20T14:22:00Z"
}
```

---

### OAuth

#### GET /v1/auth/oauth/providers

List configured OAuth providers.

**Response:** `OAuthProvidersResponse`
```json
{
  "providers": [
    {
      "name": "google",
      "enabled": true,
      "login_url": "/v1/auth/oauth/google/login"
    },
    {
      "name": "github",
      "enabled": true,
      "login_url": "/v1/auth/oauth/github/login"
    }
  ]
}
```

---

#### GET /v1/auth/oauth/{provider}/login

Initiate OAuth login flow. Redirects to provider's authorization page.

**Parameters:**
- `provider` - OAuth provider name (`google`, `github`, `discord`)

**Query Parameters:**
- `redirect_uri` (optional) - Custom redirect after successful auth

**Response:** `302 Redirect` to OAuth provider

**Example:**
```
GET /v1/auth/oauth/google/login?redirect_uri=https://app.example.com/dashboard
```

---

#### GET /v1/auth/oauth/{provider}/callback

OAuth callback endpoint (called by provider after user authorizes).

**Parameters:**
- `provider` - OAuth provider name

**Query Parameters:**
- `code` - Authorization code from provider
- `state` - State parameter for CSRF protection

**Response:** `OAuth2CallbackResponse`
```json
{
  "access_token": "ciris_observer_xyz789...",
  "token_type": "Bearer",
  "expires_in": 2592000,
  "role": "OBSERVER",
  "user_id": "google:12345",
  "provider": "google",
  "email": "user@example.com",
  "name": "User Name"
}
```

**Callback URL Format:**
```
https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback
```

---

### API Key Management

**New in v1.3.1** - OAuth users can create API keys tied to their identity with configurable expiry times.

#### POST /v1/auth/api-keys

Create a new API key for the authenticated user.

**Authorization:** Bearer token required (OAuth or password login)

**Request:** `APIKeyCreateRequest`
```json
{
  "description": "CI/CD pipeline key",
  "expires_in_minutes": 1440
}
```

**Validation:**
- `expires_in_minutes` must be between 30 and 10080 (7 days)
- Common values:
  - `30` - 30 minutes
  - `60` - 1 hour
  - `1440` - 1 day (24 hours)
  - `10080` - 7 days (maximum)

**Response:** `APIKeyResponse`
```json
{
  "api_key": "ciris_observer_abc123def456...",
  "role": "OBSERVER",
  "expires_at": "2025-01-21T14:22:00Z",
  "description": "CI/CD pipeline key",
  "created_at": "2025-01-20T14:22:00Z",
  "created_by": "google:12345"
}
```

**Important:**
- The API key value is shown **only once** and cannot be retrieved later
- Keys automatically inherit the user's current role
- Store the key securely immediately after creation

---

#### GET /v1/auth/api-keys

List all API keys for the authenticated user.

**Authorization:** Bearer token required

**Response:** `APIKeyListResponse`
```json
{
  "api_keys": [
    {
      "key_id": "ciris_observer_abc...",
      "role": "OBSERVER",
      "expires_at": "2025-01-21T14:22:00Z",
      "description": "CI/CD pipeline key",
      "created_at": "2025-01-20T14:22:00Z",
      "created_by": "google:12345",
      "last_used": "2025-01-20T15:30:00Z",
      "is_active": true
    }
  ],
  "total": 1
}
```

**Notes:**
- Only returns keys owned by the authenticated user
- Keys are identified by partial key ID for security
- Full key value is never returned after creation

---

#### DELETE /v1/auth/api-keys/{key_id}

Revoke an API key. Users can only delete their own keys.

**Authorization:** Bearer token required

**Parameters:**
- `key_id` - The key identifier (from GET /v1/auth/api-keys)

**Response:** `204 No Content`

**Errors:**
- `404` - Key not found or belongs to another user
- `401` - Unauthorized

**Example:**
```bash
curl -X DELETE https://agents.ciris.ai/v1/auth/api-keys/ciris_observer_abc... \
  -H "Authorization: Bearer current-token"
```

---

## Billing & Credits

Credit management for CIRIS agents. Supports both free tier (SimpleCreditProvider) and paid credits (CIRISBillingProvider).

#### GET /api/billing/credits

Get current credit balance and status for the authenticated user.

**Authorization:** Bearer token required (OBSERVER role or higher)

**Response:** `CreditStatusResponse`
```json
{
  "has_credit": true,
  "credits_remaining": 45,
  "free_uses_remaining": 5,
  "total_uses": 12,
  "plan_name": "standard",
  "purchase_required": false,
  "purchase_options": null
}
```

**Free tier (SimpleCreditProvider):**
```json
{
  "has_credit": true,
  "credits_remaining": 0,
  "free_uses_remaining": 1,
  "total_uses": 0,
  "plan_name": "free",
  "purchase_required": false,
  "purchase_options": null
}
```

**Free tier exhausted:**
```json
{
  "has_credit": false,
  "credits_remaining": 0,
  "free_uses_remaining": 0,
  "total_uses": 1,
  "plan_name": "free",
  "purchase_required": false,
  "purchase_options": {
    "price_minor": 0,
    "uses": 0,
    "currency": "USD",
    "message": "Contact administrator to enable billing"
  }
}
```

---

#### POST /api/billing/purchase/initiate

Initiate credit purchase flow (creates Stripe payment intent).

**Authorization:** Bearer token required (OBSERVER role or higher)

**Request:** `PurchaseInitiateRequest`
```json
{
  "return_url": "https://app.example.com/billing/complete"
}
```

**Response:** `PurchaseInitiateResponse`
```json
{
  "payment_id": "pi_abc123xyz",
  "client_secret": "pi_abc123xyz_secret_def456",
  "amount_minor": 500,
  "currency": "USD",
  "uses_purchased": 20,
  "publishable_key": "pk_live_xyz..."
}
```

**Notes:**
- Only works when `CIRIS_BILLING_ENABLED=true`
- Returns `403` when SimpleCreditProvider is active (billing disabled)
- Frontend uses `client_secret` and `publishable_key` with Stripe.js
- Default purchase: $5.00 for 20 uses

**Error responses:**
- `403` - Billing not enabled
- `503` - Credit provider not configured or billing service unavailable

---

#### GET /api/billing/purchase/status/{payment_id}

Check payment status and confirm credits were added.

**Authorization:** Bearer token required (OBSERVER role or higher)

**Parameters:**
- `payment_id` - Payment intent ID from initiate response

**Response:** `PurchaseStatusResponse`
```json
{
  "status": "succeeded",
  "credits_added": 20,
  "balance_after": 65
}
```

**Status values:**
- `succeeded` - Payment completed, credits added
- `pending` - Payment processing
- `failed` - Payment failed

**Notes:**
- Frontend can poll this endpoint after payment to confirm
- Returns `404` when billing is disabled

---

## Agent Interaction

#### POST /v1/agent/interact

Send a message to the agent and receive a response.

**Authorization:** Bearer token required (SEND_MESSAGES permission)

**Request:**
```json
{
  "message": "Hello, how are you?",
  "context": {
    "channel": "web-chat",
    "user_context": "First time user"
  }
}
```

**Response:**
```json
{
  "response": "Hello! I'm doing well, thank you for asking. How can I help you today?",
  "thought_id": "thought-abc123",
  "action_taken": "SPEAK",
  "processing_time_ms": 342
}
```

---

## System & Telemetry

#### GET /v1/system/health

Health check endpoint (no authentication required).

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-20T14:22:00Z",
  "services_healthy": 22,
  "services_total": 22
}
```

---

#### GET /v1/telemetry/unified

Get unified telemetry data for all services.

**Authorization:** Bearer token required (VIEW_TELEMETRY permission)

**Response:**
```json
{
  "services_online": 22,
  "services_total": 22,
  "timestamp": "2025-01-20T14:22:00Z",
  "services": {
    "authentication": {
      "healthy": true,
      "status": "HEALTHY",
      "circuit_breaker": "CLOSED"
    },
    "memory": {
      "healthy": true,
      "status": "HEALTHY",
      "circuit_breaker": "CLOSED"
    }
  }
}
```

---

## Error Handling

All endpoints return standardized error responses:

### 400 Bad Request
```json
{
  "detail": "Invalid request parameters",
  "errors": {
    "expires_in_minutes": ["Must be between 30 and 10080"]
  }
}
```

### 401 Unauthorized
```json
{
  "detail": "Missing authorization header"
}
```

### 403 Forbidden
```json
{
  "detail": "Insufficient permissions. Required: SEND_MESSAGES"
}
```

### 404 Not Found
```json
{
  "detail": "API key not found"
}
```

### 503 Service Unavailable
```json
{
  "detail": "Billing service unavailable"
}
```

---

## Authentication Examples

### Using API Keys

```bash
# Create API key
curl -X POST https://agents.ciris.ai/v1/auth/api-keys \
  -H "Authorization: Bearer current-token" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "My automation key",
    "expires_in_minutes": 1440
  }'

# Use API key
curl -X GET https://agents.ciris.ai/v1/telemetry/unified \
  -H "Authorization: Bearer ciris_observer_abc123..."
```

### OAuth Flow

```javascript
// 1. Get OAuth providers
const providers = await fetch('/v1/auth/oauth/providers').then(r => r.json());

// 2. Redirect to OAuth login
window.location.href = '/v1/auth/oauth/google/login?redirect_uri=' +
  encodeURIComponent('https://app.example.com/auth/callback');

// 3. Handle callback (CIRIS redirects to your redirect_uri with token)
const urlParams = new URLSearchParams(window.location.search);
const token = urlParams.get('access_token');
localStorage.setItem('ciris_token', token);

// 4. Use token for API calls
const credits = await fetch('/api/billing/credits', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
}).then(r => r.json());
```

---

## Rate Limits

- **Authentication endpoints**: 10 requests/minute per IP
- **API key creation**: 5 keys/hour per user
- **Billing endpoints**: 30 requests/minute per user
- **Agent interaction**: Based on credit availability

---

## Changelog

### v1.3.1
- Added API key management endpoints (POST/GET/DELETE /v1/auth/api-keys)
- Added configurable expiry for API keys (30 minutes to 7 days)
- Enhanced billing endpoints with marketing opt-in support
- Improved resource usage tracking in action results

### v1.3.0
- Added billing endpoints (/api/billing/*)
- Added OAuth providers endpoint
- Enhanced authentication with multiple providers

---

**For more information:**
- [CIRIS Documentation Hub](README.md)
- [Architecture Overview](ARCHITECTURE.md)
- [OAuth Setup Guide](OAUTH_CONFIGURATION_GUIDE.md)
- [Security Guide](SECURITY_SETUP.md)
