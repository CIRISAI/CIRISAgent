# Environment Variables Reference

This document provides a comprehensive reference for all environment variables supported by the CIRIS Agent configuration system.

## Configuration Prefix Convention

All CIRIS-specific environment variables use the `CIRIS_` prefix to avoid conflicts with other applications.

## Essential Configuration Variables

### Database Configuration
- `CIRIS_DATABASE_MAIN_DB` - Main database path (default: data/ciris_engine.db)
- `CIRIS_DATABASE_SECRETS_DB` - Secrets database path (default: data/secrets.db)
- `CIRIS_DATABASE_AUDIT_DB` - Audit database path (default: data/audit.db)
- `CIRIS_DATABASE_GRAPH_MEMORY_DB` - Graph memory database path (default: data/graph_memory.db)

### Service Configuration
- `CIRIS_SERVICES_LLM_PROVIDER` - LLM provider selection (default: openai)
- `CIRIS_SERVICES_LLM_API_KEY` - LLM API key (no default - must be provided)
- `CIRIS_SERVICES_LLM_MODEL` - LLM model name (default: gpt-4)
- `CIRIS_SERVICES_LLM_BASE_URL` - Custom LLM API base URL (optional)
- `CIRIS_SERVICES_CIRISNODE_URL` - CIRISNode service URL (optional)

### Security Configuration
- `CIRIS_SECURITY_SECRETS_ENCRYPTION_KEY_ENV` - Environment variable containing master key (default: CIRIS_MASTER_KEY)
- `CIRIS_SECURITY_AUDIT_KEY_PATH` - Directory for audit signing keys (default: audit_keys)
- `CIRIS_SECURITY_ENABLE_SIGNED_AUDIT` - Enable cryptographic audit signing (default: true)
- `CIRIS_SECURITY_MAX_THOUGHT_DEPTH` - Maximum thought chain depth (default: 7)

### Operational Limits
- `CIRIS_LIMITS_MAX_ACTIVE_TASKS` - Maximum concurrent tasks (default: 10)
- `CIRIS_LIMITS_MAX_ACTIVE_THOUGHTS` - Maximum thoughts in queue (default: 50)
- `CIRIS_LIMITS_ROUND_DELAY_SECONDS` - Processing round delay (default: 5.0)
- `CIRIS_LIMITS_MOCK_LLM_ROUND_DELAY` - Mock LLM delay (default: 0.1)
- `CIRIS_LIMITS_DMA_RETRY_LIMIT` - DMA retry attempts (default: 3)
- `CIRIS_LIMITS_DMA_TIMEOUT_SECONDS` - DMA timeout (default: 30.0)
- `CIRIS_LIMITS_CONSCIENCE_RETRY_LIMIT` - Conscience retry attempts (default: 2)

### Telemetry Configuration
- `CIRIS_TELEMETRY_ENABLED` - Enable telemetry collection (default: false)
- `CIRIS_TELEMETRY_EXPORT_INTERVAL_SECONDS` - Export interval (default: 60)
- `CIRIS_TELEMETRY_RETENTION_HOURS` - Data retention period (default: 24)

## Legacy Environment Variables (Still Supported)

These variables are maintained for backward compatibility but may be deprecated:

### OpenAI/LLM Services
- `OPENAI_API_KEY` - Falls back to this if CIRIS_SERVICES_LLM_API_KEY not set
- `OPENAI_API_BASE` / `OPENAI_BASE_URL` - Falls back if CIRIS_SERVICES_LLM_BASE_URL not set
- `OPENAI_MODEL_NAME` - Falls back if CIRIS_SERVICES_LLM_MODEL not set

### Discord Integration
- `DISCORD_BOT_TOKEN` - Discord bot token (adapter-specific)
- `DISCORD_CHANNEL_ID` - Discord channel ID (adapter-specific)
- `DISCORD_DEFERRAL_CHANNEL_ID` - Deferral channel (adapter-specific)
- `WA_USER_IDS` - Wise Authority Discord user IDs (comma-separated list)

### Security
- `CIRIS_MASTER_KEY` - Master encryption key (referenced by CIRIS_SECURITY_SECRETS_ENCRYPTION_KEY_ENV)

## Environment Variable Precedence

1. **Direct CIRIS_ prefixed variables** - Highest priority
2. **Legacy variables** - Used as fallback
3. **Configuration file values** - From essential.yaml
4. **Built-in defaults** - Lowest priority

## Example .env File

```bash
# Essential Configuration
CIRIS_DATABASE_MAIN_DB=./data/production.db
CIRIS_SERVICES_LLM_API_KEY=sk-your-api-key-here
CIRIS_SERVICES_LLM_MODEL=gpt-4

# Security
CIRIS_MASTER_KEY=your-strong-encryption-key-here
CIRIS_SECURITY_ENABLE_SIGNED_AUDIT=true

# Operational Tuning
CIRIS_LIMITS_MAX_ACTIVE_TASKS=20
CIRIS_LIMITS_ROUND_DELAY_SECONDS=3.0

# Telemetry (disabled by default)
CIRIS_TELEMETRY_ENABLED=false

# Discord Adapter (if using Discord)
DISCORD_BOT_TOKEN=your-discord-bot-token
DISCORD_CHANNEL_ID=123456789012345678
```

## Best Practices

1. **Use CIRIS_ prefix** for all new environment variables
2. **Store secrets in environment** never in config files
3. **Set CIRIS_MASTER_KEY** for production deployments
4. **Use .env files** for local development only
5. **Document all custom variables** in your deployment

---

*Mission-critical configuration for autonomous moral reasoning agents.*
