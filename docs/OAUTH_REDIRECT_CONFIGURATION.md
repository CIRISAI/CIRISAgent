# OAuth Redirect Configuration

## Overview

The OAuth redirect system is now fully configurable via environment variables, making it easy to adapt to different frontend/backend architectures and add/remove redirect parameters without code changes.

## Environment Variables

### `OAUTH_FRONTEND_URL`

**Purpose**: Base URL of the frontend application where users are redirected after OAuth completion

**Example**:
```bash
OAUTH_FRONTEND_URL=https://scout.ciris.ai
```

**Default**: None (falls back to relative path if not set)

**When to use**: When your frontend and backend are on different domains (e.g., `scout.ciris.ai` vs `scoutapi.ciris.ai`)

---

### `OAUTH_FRONTEND_PATH`

**Purpose**: Path on the frontend where the OAuth completion page lives

**Example**:
```bash
OAUTH_FRONTEND_PATH=/oauth-complete.html
```

**Default**: `/oauth-complete.html`

**When to use**: If your frontend uses a different path for OAuth completion (e.g., `/auth/complete`, `/login/callback`)

---

### `OAUTH_REDIRECT_PARAMS`

**Purpose**: Comma-separated list of parameters to include in the OAuth redirect URL

**Example**:
```bash
OAUTH_REDIRECT_PARAMS=access_token,token_type,role,user_id,expires_in,email,marketing_opt_in,agent,provider
```

**Default**: `access_token,token_type,role,user_id,expires_in,email,marketing_opt_in,agent,provider`

**Available Parameters**:
- `access_token` - API key for authenticated requests
- `token_type` - Always "Bearer"
- `role` - User role (observer, admin, etc.)
- `user_id` - Unique user identifier
- `expires_in` - Token expiration in seconds (default: 2592000 = 30 days)
- `email` - User email from OAuth provider
- `marketing_opt_in` - Marketing preference (true/false) from redirect_uri
- `agent` - Agent ID (e.g., "scout", "datum")
- `provider` - OAuth provider (e.g., "google", "discord")

**When to use**: To customize which parameters are included in the redirect. Remove sensitive parameters or add new ones as needed.

---

### `OAUTH_CALLBACK_BASE_URL`

**Purpose**: Base URL for OAuth provider callbacks (where Google/Discord sends authorization codes)

**Example**:
```bash
OAUTH_CALLBACK_BASE_URL=https://scoutapi.ciris.ai
```

**Default**: `https://agents.ciris.ai`

**When to use**: When your backend API is on a different domain than agents.ciris.ai

---

## Configuration Examples

### Example 1: Scout with Separate Frontend/Backend

```bash
# Backend API domain (for OAuth provider callbacks)
OAUTH_CALLBACK_BASE_URL=https://scoutapi.ciris.ai

# Frontend domain (for user redirects)
OAUTH_FRONTEND_URL=https://scout.ciris.ai
OAUTH_FRONTEND_PATH=/oauth-complete.html

# Full parameter set
OAUTH_REDIRECT_PARAMS=access_token,token_type,role,user_id,expires_in,email,marketing_opt_in,agent,provider

# Agent ID
CIRIS_AGENT_ID=scout
```

**Result**: After OAuth, users are redirected to:
```
https://scout.ciris.ai/oauth-complete.html?access_token=...&email=...&marketing_opt_in=true&agent=scout&provider=google
```

---

### Example 2: Minimal Configuration (Backward Compatible)

```bash
# No frontend URL set - uses relative path
OAUTH_REDIRECT_PARAMS=access_token,token_type,role,user_id

# Agent ID
CIRIS_AGENT_ID=datum
```

**Result**: After OAuth, users are redirected to:
```
/oauth/datum/google/callback?access_token=...&token_type=Bearer&role=observer&user_id=...
```

---

### Example 3: Privacy-Focused Configuration

```bash
# Exclude email from redirect (store server-side only)
OAUTH_REDIRECT_PARAMS=access_token,token_type,role,user_id,expires_in

OAUTH_FRONTEND_URL=https://app.example.com
OAUTH_FRONTEND_PATH=/auth/complete
```

**Result**: Email is not included in the redirect URL for privacy, but is still stored in the backend database.

---

## Marketing Opt-In Flow

The `marketing_opt_in` parameter is automatically extracted from the initial redirect_uri:

**Step 1**: Frontend initiates OAuth with marketing preference
```
GET /api/scout/v1/auth/oauth/google/login
  ?redirect_uri=https://scout.ciris.ai/oauth-complete.html?marketing_opt_in=true
```

**Step 2**: Backend extracts `marketing_opt_in` from redirect_uri and passes it through OAuth flow

**Step 3**: Backend includes it in the final redirect
```
https://scout.ciris.ai/oauth-complete.html
  ?access_token=...
  &email=user@example.com
  &marketing_opt_in=true
  &...
```

---

## Redirect Priority

The system uses this priority when determining where to redirect users:

1. **Explicit `redirect_uri` from state parameter** (highest priority)
   - Set by frontend when initiating OAuth
   - Base URL is extracted (query params replaced with OAuth params)

2. **`OAUTH_FRONTEND_URL` + `OAUTH_FRONTEND_PATH`**
   - Environment variable configuration
   - Good for production deployments

3. **Relative path fallback** (backward compatibility)
   - `/oauth/{agent_id}/{provider}/callback`
   - Works when frontend and backend are on the same domain

---

## Testing

### Test Full Configuration
```bash
# Set environment variables
export OAUTH_FRONTEND_URL=https://scout.ciris.ai
export OAUTH_FRONTEND_PATH=/oauth-complete.html
export OAUTH_REDIRECT_PARAMS=access_token,token_type,role,user_id,email,marketing_opt_in,agent,provider
export CIRIS_AGENT_ID=scout

# Initiate OAuth with redirect_uri containing marketing_opt_in
curl "https://scoutapi.ciris.ai/api/scout/v1/auth/oauth/google/login?redirect_uri=https%3A%2F%2Fscout.ciris.ai%2Foauth-complete.html%3Fmarketing_opt_in%3Dtrue"
```

Expected redirect after OAuth:
```
https://scout.ciris.ai/oauth-complete.html
  ?access_token={generated_key}
  &token_type=Bearer
  &role=observer
  &user_id={oauth_user_id}
  &expires_in=2592000
  &email=user@example.com
  &marketing_opt_in=true
  &agent=scout
  &provider=google
```

---

## Troubleshooting

### Issue: Users redirected to wrong domain
**Solution**: Check `OAUTH_FRONTEND_URL` is set correctly

### Issue: Missing parameters in redirect
**Solution**: Add parameter names to `OAUTH_REDIRECT_PARAMS`

### Issue: marketing_opt_in always false
**Solution**: Ensure redirect_uri includes `?marketing_opt_in=true` when initiating OAuth

### Issue: Email not included in redirect
**Solution**: Add `email` to `OAUTH_REDIRECT_PARAMS` environment variable

---

## Adding New Parameters

To add a new parameter to the OAuth redirect:

1. **Add parameter to `all_params` dict** in `_build_redirect_response()` (auth.py:731)
2. **Add parameter name to default `OAUTH_REDIRECT_PARAMS`** (auth.py:62)
3. **Update this documentation** with parameter description
4. **Update frontend** to handle the new parameter

Example: Adding a `locale` parameter
```python
# In auth.py
all_params = {
    # ... existing params ...
    "locale": user_locale or "en",  # NEW
}

# Environment variable
OAUTH_REDIRECT_PARAMS=access_token,token_type,role,user_id,expires_in,email,marketing_opt_in,agent,provider,locale
```

---

## Security Considerations

1. **Sensitive Data**: Avoid including sensitive data in redirect URLs (they appear in browser history)
2. **Email Privacy**: Consider if email should be in the URL or fetched via API after login
3. **Token Security**: Access tokens in URLs are visible in logs - consider using POST-based flows for maximum security
4. **HTTPS Only**: Always use HTTPS for OAuth redirects in production

---

## Related Documentation

- [OAuth Callback URLs](./OAUTH_CALLBACK_URLS.md) - OAuth provider callback configuration
- [OAuth Configuration Guide](./OAUTH_CONFIGURATION_GUIDE.md) - Setting up OAuth providers
- [ScoutGUI Backend Requirements](../../ScoutGUI/BACKEND_OAUTH_REQUIREMENTS.md) - Frontend integration requirements
