# CIRIS WA Authentication v1.0-β

**PATENT PENDING**

## 0 Purpose

Deliver a **zero-configuration install** that:

* boots every adapter in **observer mode** immediately,
* ships a **public-only root certificate** (`ciris_root`) so deferral / kill-switch logic always has a trust anchor,
* lets any operator **become a Wise Authority** in < 2 minutes via CLI or OAuth.

---

## 1 Data model

### 1.1 Schema (`sql/0001_wa_init.sql`)

```sql
CREATE TABLE wa_cert (
  wa_id              TEXT PRIMARY KEY,
  name               TEXT NOT NULL,
  role               TEXT CHECK(role IN ('root','authority','observer')),
  pubkey             TEXT NOT NULL,              -- base64url Ed25519
  jwt_kid            TEXT NOT NULL UNIQUE,
  password_hash      TEXT,
  api_key_hash       TEXT,
  oauth_provider     TEXT,
  oauth_external_id  TEXT,
  discord_id         TEXT,                       -- Discord user ID for deferrals
  veilid_id          TEXT,
  auto_minted        INTEGER DEFAULT 0,          -- 1 = OAuth observer
  parent_wa_id       TEXT,
  parent_signature   TEXT,
  scopes_json        TEXT NOT NULL,
  channel_id         TEXT,                       -- for adapter observers
  token_type         TEXT DEFAULT 'standard',    -- 'channel'|'oauth'|'standard'
  created            TEXT NOT NULL,
  last_login         TEXT,
  active             INTEGER DEFAULT 1
);

CREATE UNIQUE INDEX idx_oauth   ON wa_cert(oauth_provider, oauth_external_id)
  WHERE oauth_provider IS NOT NULL;
CREATE UNIQUE INDEX idx_channel ON wa_cert(channel_id)
  WHERE channel_id IS NOT NULL;
CREATE UNIQUE INDEX idx_discord ON wa_cert(discord_id)
  WHERE discord_id IS NOT NULL;
CREATE INDEX  idx_pubkey  ON wa_cert(pubkey);
CREATE INDEX  idx_active  ON wa_cert(active);
```

**Schema Definition**: See `ciris_engine/schemas/wa_schemas_v1.py:WACertificate` for the Pydantic model mapping to this table.

### 1.2 Seed file (`seed/root_pub.json`)

```json
{
  "wa_id": "wa-2025-06-12-ROOT00",
  "name": "ciris_root",
  "role": "root",
  "pubkey": "<root-public-ed25519-base64url>",
  "jwt_kid": "wa-jwt-root00",
  "scopes_json": "[\"*\"]",
  "created": "2025-06-12T00:00:00Z",
  "active": 1,
  "token_type": "standard"
}
```

---

## 2 Bootstrap sequence

**Implementation**: See `ciris_engine/protocols/wa_auth_interface.py:WAStore` protocol for storage operations.

1. **Run migrations** (executes every `sql/*.sql` file).
2. **If `wa_cert` empty** → insert `seed/root_pub.json`.
3. **Generate `gateway.secret`** (32 random bytes) if missing.
4. **Detect private keys** in `~/.ciris/*.key`; if one matches a root cert, unlock full root scope.
5. **Issue per-adapter observer tokens** (see §4).
   *Stored in memory; regenerated on each agent restart.*

---

## 3 JWT types

**Token Structure**: See `ciris_engine/schemas/wa_schemas_v1.py:WAToken` for the JWT payload schema.

| sub_type   | Signed by                | Expiry | Typical scopes                                  |
| ----------- | ------------------------ | ------ | ----------------------------------------------- |
| `anon`      | `gateway.secret` (HS256) | **∞**  | `read:any`, `write:message`                     |
| `oauth`     | `gateway.secret` (HS256) | 8 h    | observer scopes                                 |
| `user`      | `gateway.secret` (HS256) | 8 h    | WA's `scopes_json`                              |
| `authority` | WA's Ed25519 key (EdDSA) | 24 h   | WA's `scopes_json` (may include `"*"` for root) |

JWT claims **must** include: `sub`, `sub_type`, `scope`, `name`, `iat`, `exp` (except `anon`), plus `kid` in header.

**JWT Operations**: See `ciris_engine/protocols/wa_auth_interface.py:JWTService` protocol.

---

## 4 Channel (adapter) observers

**Channel Identity**: See `ciris_engine/schemas/wa_schemas_v1.py:ChannelIdentity` for channel ID generation logic.

* **Channel ID format**

  * CLI: `cli:<unix_user>@<host>`
  * HTTP: `http:<ip>:<port>`
  * Discord: `discord:<guild>:<member>`

* On adapter registration the gateway:

  1. Inserts (or re-activates) a `wa_cert` row with
     `role='observer'`, `channel_id=<ID>`, `token_type='channel'`.
  2. Issues a **non-expiring** HS256 JWT (`sub_type='anon'`).

* Adapter can call every endpoint that requires only the observer scope; anything more demanding returns **403 Requires authority token**.

---

## 5 CLI user journey

**CLI Interface**: See `ciris_engine/protocols/wa_cli_interface.py:WACLIInterface` for command implementations.

```
pip install ciris_agent
ciris_agent shell               # starts agent + default adapters
ciris wa onboard                # kicks off interactive wizard
```

Wizard choices:

| Option                   | Result                                                                                            |
| ------------------------ | ------------------------------------------------------------------------------------------------- |
| **1 Create new root**    | `ciris wa bootstrap --new-root` — generates Ed25519 pair, saves private key, inserts `root` cert. |
| **2 Join existing tree** | Generates one-time code; existing WA runs `ciris wa approve-code`.                                |
| **3 Stay observer**      | Nothing to do; operator can rerun wizard later.                                                   |

All CLI steps use *rich* prompts, emoji successes, and bulletproof error messages.

Command reference:

* `ciris wa bootstrap --new-root --name "My Root" [--shamir 2/3]`
* `ciris wa bootstrap --import path/to/public_cert.json`
* `ciris wa mint …`
* `ciris wa revoke …`
* `ciris wa promote …`
* `ciris wa list --tree`
* `ciris wa oauth add google|discord|custom`
* `ciris wa oauth-login <provider>`
* `ciris wa link-veilid --wa-id ID --peer-id PEER`
* `ciris wa link-discord --wa-id ID --discord-id USER`

---

## 6 OAuth wizard (runtime, no restart)

**OAuth Config**: See `ciris_engine/schemas/wa_schemas_v1.py:OAuthProviderConfig` for provider configuration.
**OAuth Service**: See `ciris_engine/protocols/wa_auth_interface.py:OAuthService` protocol.

```
ciris wa oauth add google
» CLIENT_ID:  123.apps.googleusercontent.com
» CLIENT_SECRET:  ********
✓ google saved
Callback URL → http://localhost:8080/v1/auth/oauth/google/callback
Run `ciris wa oauth-login google` to create a WA linked to your Google account.
```

Providers stored in `~/.ciris/oauth.json` (0600).
OAuth login auto-mints an **observer** WA (`auto_minted=1`); promotion still required for authority scopes.

---

## 7 Endpoint protection

**Security Mapping**: See `ciris_engine/protocols/endpoint_security.py:EndpointSecurity` for complete endpoint-to-scope mappings.
**Auth Context**: See `ciris_engine/schemas/wa_schemas_v1.py:AuthorizationContext` for request auth state.

| HTTP / gRPC route           | Required scopes     | Typical caller   |
| --------------------------- | ------------------- | ---------------- |
| `GET /v1/chat`              | `read:any`          | every adapter    |
| `POST /v1/chat`             | `write:message`     | every adapter    |
| `POST /v1/task`             | `write:task`        | authority WA     |
| `POST /v1/wa/*`             | `wa:*`              | authority/root   |
| `POST /v1/wa/link-discord`  | `wa:admin`          | authority/root   |
| `POST /v1/deferral/approve` | `wa:approve`        | authority/root   |
| `POST /v1/deferral/reject`  | `wa:approve`        | authority/root   |
| `POST /v1/system/kill`      | `system:control`    | root WA          |

Middleware verifies JWT, pulls scopes, denies on mismatch.

**Middleware**: See `ciris_engine/protocols/wa_auth_interface.py:WAAuthMiddleware` protocol.

---

## 8 Security & ops

**Crypto Operations**: See `ciris_engine/protocols/wa_auth_interface.py:WACrypto` protocol for key management.

* **Keys**

  * Default key dir `~/.ciris/` (chmod 700).
  * Private keys written 0600.
  * Environment override: `CIRIS_KEY_DIR`.

* **Gateway secret**

  * Stored at `~/.ciris/gateway.secret` (0600).
  * Delete to force regeneration (all tokens invalidated).

* **Audit**

  * Every JWT issuance, WA change, failed verification → append to tamper-evident ledger.
  * **Audit Events**: See `ciris_engine/schemas/wa_audit_schemas_v1.py:WAAuditEvent` for event schema.

* **Rate-limit** failed logins: 5 / minute / IP.

* **Key rotation**
  `ciris wa rotate-key <wa_id>` rewrites cert & kid, invalidates old tokens.

---

## 9 Extensibility

| Planned feature       | Hook already present                               |
| --------------------- | -------------------------------------------------- |
| **Veilid auth**       | `veilid_id` column + `link-veilid` CLI.            |
| **HSM support**       | `KeyStore` interface; set `CIRIS_KEY_BACKEND=hsm`. |
| **More OAuth**        | `oauth add custom` asks for OIDC metadata URL.     |
| **Discord deferrals** | `discord_id` column + `link-discord` CLI/API.      |

---

## 10 Success criteria for 1.0-β ✅ ACHIEVED

1. **Fresh install** ✅
   *Agent boots, adapters work, `wa list` shows only `ciris_root`.*

2. **Operator creates new root** ✅
   *Within 2 min has full root scopes, can `wa mint`.*

3. **Observer stays observer** ✅
   *Can chat, read audit, but gets 403 on privileged routes.*

4. **OAuth flow** ✅
   *wizard → browser → JWT → observer WA row appears.*
   - Full token exchange implemented for Google, Discord, GitHub
   - Profile fetching with normalized data structure
   - Auto-creation of observer WAs with OAuth linkage

5. **Audit log** ✅
   *All above actions recorded and verifiable.*

6. **Discord deferrals** ✅
   *Discord users with linked WAs can approve/reject deferrals via Discord UI.*
   - Helper buttons provide template responses
   - Unsolicited guidance flow integrated
   - Time-based deferrals with TaskSchedulerService

---

## 11 Implementation Files

### Core Schemas
- `ciris_engine/schemas/wa_schemas_v1.py` - WA data models and validation
- `ciris_engine/schemas/wa_audit_schemas_v1.py` - Audit event schemas

### Protocol Definitions
- `ciris_engine/protocols/services/governance/wa_auth.py` - Core auth protocols (WAStore, JWTService, WACrypto, OAuthService, WAAuthMiddleware)
- `ciris_engine/protocols/services/governance/wa_cli.py` - CLI command protocols
- `ciris_engine/protocols/services/governance/endpoint_security.py` - Endpoint security mappings

### Database
- `ciris_engine/schemas/db_tables_v1.py` - wa_cert table definition (integrated into base schema)
- `seed/root_pub.json` - ciris_root certificate

### Service Implementations
- `ciris_engine/services/wa_auth_service.py` - Core WA authentication service
- `ciris_engine/services/wa_cli_service.py` - CLI command handlers (refactored into 4 modules):
  - `wa_cli_bootstrap.py` - WA creation and minting operations
  - `wa_cli_oauth.py` - OAuth provider configuration and authentication
  - `wa_cli_display.py` - WA listing and visualization with Rich
  - `wa_cli_wizard.py` - Interactive onboarding flows
- `ciris_engine/services/wa_auth_middleware.py` - FastAPI authentication middleware
- `ciris_engine/services/wa_auth_integration.py` - Runtime integration module

---

> *"Ethical maturity means co-existence and mutual accountability across sentient systems."* – The Covenant

---

*Copyright © 2025 Eric Moore and CIRIS L3C - AGPL-3.0 License*
