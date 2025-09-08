# CIRIS Agent Deployment Guide

Comprehensive deployment guide for CIRIS Agent with enterprise security features.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation Methods](#installation-methods)
- [Configuration](#configuration)
- [Security Setup](#security-setup)
- [Environment-Specific Deployments](#environment-specific-deployments)
- [Service Dependencies](#service-dependencies)
- [Health Monitoring](#health-monitoring)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **Python**: 3.9 or higher
- **Memory**: Minimum 512MB RAM, recommended 2GB+ for production
- **Storage**: 1GB free space for databases and logs
- **Network**: Internet connectivity for LLM API calls
- **OS**: Linux, macOS, or Windows with WSL2

### Dependencies

```bash
# Production dependencies only
pip install -r requirements.txt

# For development environments also install:
pip install -r requirements-dev.txt

# Optional: For development
pip install pytest mypy
```

### Required Environment Variables

Create a `.env` file or set environment variables:

```bash
# Core Configuration
OPENAI_API_KEY="your_openai_api_key"
LOG_LEVEL="INFO"

# Discord (if using Discord mode)
DISCORD_BOT_TOKEN="your_discord_bot_token"
DISCORD_CHANNEL_ID="your_channel_id"

# Security Keys
SECRETS_MASTER_KEY="your_base64_encoded_32_byte_key"
TELEMETRY_ENCRYPTION_KEY="your_base64_encoded_32_byte_key"

# Paths (optional - defaults provided)
CIRIS_DB_PATH="./data/ciris_engine.db"
CIRIS_DATA_DIR="./data"
SECRETS_DB_PATH="./secrets.db"
AUDIT_LOG_PATH="./audit_logs.jsonl"
```

## Installation Methods

### Method 1: Direct Python Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-org/CIRISAgent.git
   cd CIRISAgent
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Initialize configuration**:
   ```bash
   # Copy and customize configuration
   cp config/base.yaml config/local.yaml
   # Edit config/local.yaml as needed
   ```

4. **Run the agent**:
   ```bash
   # CLI mode
   python main.py --mode cli

   # Discord mode
   python main.py --mode discord

   # API mode
   python main.py --mode api

   # Note: Profiles are only used during initial agent creation
   # Use --profile only with --wa-bootstrap for new agents
   ```

### Method 2: Docker Deployment

1. **Build the image**:
   ```bash
   docker build -t ciris-agent -f docker/Dockerfile .
   ```

2. **Create environment file**:
   ```bash
   # Create env.sh with required variables
   cat > env.sh << EOF
   export OPENAI_API_KEY="your_key"
   export DISCORD_BOT_TOKEN="your_token"
   export SECRETS_MASTER_KEY="$(openssl rand -base64 32)"
   EOF
   ```

3. **Run the container**:
   ```bash
   docker run -it --env-file env.sh \
     -v $(pwd)/data:/app/data \
     -v $(pwd)/config:/app/config \
     ciris-agent
   ```

### Method 3: Docker Compose (Recommended for Production)

1. **Use the provided docker-compose.yml**:
   ```bash
   # Customize docker-compose.yml
   cp docker-compose.yml docker-compose.local.yml

   # Start services
   docker-compose -f docker-compose.local.yml up -d
   ```

### Method 4: Automated CD Pipeline (Production Deployment)

The CIRIS project uses GitHub Actions for continuous deployment to production servers.

#### CD Pipeline Overview

1. **Trigger**: Merge to main branch or manual workflow dispatch
2. **Build**: Docker images built and pushed to GitHub Container Registry
3. **Deploy**: Staged deployment with zero-downtime updates

#### Deployment Process

```bash
# 1. Create PR to upstream repository
gh pr create --repo CIRISAI/CIRISAgent --title "Your changes" --body "Description"

# 2. Merge PR (requires admin permissions)
gh pr merge <PR#> --repo CIRISAI/CIRISAgent --merge --admin

# 3. Automatic deployment begins:
#    - Tests run in Docker container
#    - Images built and pushed to ghcr.io
#    - Server deployment initiated
#    - Health checks verify deployment
```

#### Staged Deployment Model

The deployment uses a sophisticated staged deployment system to ensure zero downtime:

1. **GUI and Nginx**: Updated immediately on deployment
2. **Agent Containers**: Staged deployment process:
   - New container created but not started
   - Waits for current agent to gracefully exit
   - New container starts automatically when old exits with code 0
   - Rollback if agent exits with non-zero code

#### Graceful Shutdown

For manual graceful shutdown or maintenance:

```bash
# Use the graceful shutdown script
./deployment/graceful-shutdown.py

# With custom message
./deployment/graceful-shutdown.py --message "Maintenance in progress"

# For remote agent
./deployment/graceful-shutdown.py --agent-url https://agents.ciris.ai
```

**Important**: Containers are configured with `restart: on-failure` policy:
- Exit code 0: Container will NOT restart (enables staged deployment)
- Non-zero exit: Container will restart automatically

#### CD Pipeline Configuration

The pipeline is configured in `.github/workflows/build.yml`:
- Automatically updates Docker Compose if v1.x detected
- Handles fresh server initialization
- Manages OAuth volume permissions
- Creates necessary directories and volumes

## Configuration

### Configuration Hierarchy

CIRIS Agent uses a layered configuration system:

1. **Base configuration**: `config/base.yaml`
2. **Environment-specific**: `config/production.yaml` or `config/development.yaml`
3. **Agent templates**: `ciris_profiles/default.yaml`, `ciris_profiles/teacher.yaml`, etc. (used only during creation)
4. **Environment variables**: Override any configuration value

### Key Configuration Sections

#### Database Configuration
```yaml
database:
  db_filename: "/var/lib/ciris/ciris_engine.db"
  data_directory: "/var/lib/ciris/data"
  graph_memory_filename: "/var/lib/ciris/graph_memory.pkl"
```

#### LLM Services
```yaml
llm_services:
  openai:
    model_name: "gpt-4o"
    timeout_seconds: 30.0
    max_retries: 3
    api_key_env_var: "OPENAI_API_KEY"
```

#### Security Configuration
```yaml
secrets:
  enabled: true
  storage:
    database_path: "/var/lib/ciris/secrets.db"
    encryption_key_env: "SECRETS_MASTER_KEY"
    key_rotation_days: 30
  detection:
    sensitivity_threshold: "HIGH"
  access_control:
    max_accesses_per_minute: 5
    require_confirmation_for: ["HIGH", "CRITICAL"]

audit:
  enable_signed_audit: true
  audit_log_path: "/var/log/ciris/audit_logs.jsonl"
  audit_db_path: "/var/lib/ciris/ciris_audit.db"
  audit_key_path: "/etc/ciris/audit_keys"
  retention_days: 2555  # 7 years
```

#### Resource Management
```yaml
resources:
  enabled: true
  budgets:
    memory:
      limit: 128  # MB
      action: "defer"
    tokens_day:
      limit: 50000
      action: "reject"
```

## Security Setup

### 1. Generate Encryption Keys

```bash
# Generate master encryption key for secrets
openssl rand -base64 32 > /etc/ciris/secrets_master.key
export SECRETS_MASTER_KEY=$(cat /etc/ciris/secrets_master.key)

# Generate telemetry encryption key
openssl rand -base64 32 > /etc/ciris/telemetry.key
export TELEMETRY_ENCRYPTION_KEY=$(cat /etc/ciris/telemetry.key)
```

### 2. Set Up Audit Keys

```bash
# Create audit key directory
mkdir -p /etc/ciris/audit_keys

# Generate RSA key pair for audit signatures
openssl genrsa -out /etc/ciris/audit_keys/audit_private.pem 4096
openssl rsa -in /etc/ciris/audit_keys/audit_private.pem \
  -pubout -out /etc/ciris/audit_keys/audit_public.pem

# Secure permissions
chmod 600 /etc/ciris/audit_keys/audit_private.pem
chmod 644 /etc/ciris/audit_keys/audit_public.pem
```

### 3. Database Security

```bash
# Create secure data directories
sudo mkdir -p /var/lib/ciris /var/log/ciris
sudo chown ciris:ciris /var/lib/ciris /var/log/ciris
sudo chmod 750 /var/lib/ciris /var/log/ciris

# Set database permissions
sudo chmod 600 /var/lib/ciris/*.db
```

### 4. Network Security

For production deployments:

- Use TLS/SSL for all external connections
- Configure firewall to restrict access
- Use VPN or private networks when possible
- Enable audit logging for all network access

## Environment-Specific Deployments

### Development Environment

```bash
# Use development configuration
python main.py --config config/development.yaml --mode cli

# Enable debug logging
export LOG_LEVEL="DEBUG"

# Use local-only features
export TELEMETRY_ENABLED="true"
export AUDIT_ENABLE_SIGNED="false"  # Disable for development speed
```

### Production Environment

```bash
# Use production configuration
python main.py --config config/production.yaml --mode discord

# Production settings
export LOG_LEVEL="WARNING"
export TELEMETRY_ENABLED="true"
export AUDIT_ENABLE_SIGNED="true"
export SECRETS_SENSITIVITY_THRESHOLD="HIGH"
```

### High-Availability Setup

For enterprise deployments:

1. **Load Balancer**: Use nginx or HAProxy for API mode
2. **Database Replication**: Set up SQLite replication or migrate to PostgreSQL
3. **Monitoring**: Integrate with Prometheus/Grafana
4. **Backup Strategy**: Automated backups of databases and keys

## Service Dependencies

### Required Services

1. **OpenAI API**: For LLM functionality
2. **Discord API**: For Discord mode operation
3. **File System**: For database and log storage

### Optional Services

1. **CIRISNode**: For multi-agent networking
2. **External Monitoring**: Prometheus/Grafana
3. **Log Aggregation**: ELK stack or similar

### Startup Order

1. Database initialization and migrations
2. Security services (secrets, audit)
3. Core services (LLM, memory, telemetry)
4. Processing services (DMAs, guardrails)
5. Interface adapters (Discord, CLI, API)

## Health Monitoring

### Built-in Health Checks

The agent provides several monitoring endpoints and logs:

#### System Health
```bash
# Check system resources
tail -f logs/latest.log | grep "resource_usage"

# Monitor telemetry
tail -f logs/latest.log | grep "telemetry"

# Check audit integrity
tail -f logs/latest.log | grep "audit_verification"
```

#### Database Health
```bash
# Check database status
python -c "
from ciris_engine.persistence.db.core import get_db_connection
conn = get_db_connection()
print('Database OK' if conn else 'Database Error')
"
```

#### Service Health
```bash
# Monitor service registry
tail -f logs/latest.log | grep "service_registry"

# Check circuit breakers
tail -f logs/latest.log | grep "circuit_breaker"
```

### External Monitoring Integration

#### Prometheus Metrics
```yaml
# Add to configuration
telemetry:
  export:
    otlp: true
    api: true
```

#### Log Monitoring
```bash
# Monitor error rates
grep "ERROR\|CRITICAL" logs/latest.log | wc -l

# Track secrets detection
grep "SECRET_DETECTED" audit_logs.jsonl | wc -l

# Monitor resource usage
grep "resource_threshold_exceeded" logs/latest.log
```

## Troubleshooting

### Common Issues

#### 1. Database Connection Errors
```bash
# Check database permissions
ls -la data/ciris_engine.db

# Verify database integrity
python -c "
from ciris_engine.persistence.db.core import verify_database_integrity
print(verify_database_integrity())
"

# Run database migrations
python -c "
from ciris_engine.persistence.db.migration_runner import run_migrations
run_migrations()
"
```

#### 2. Authentication Failures
```bash
# Verify API keys
echo $OPENAI_API_KEY | wc -c  # Should be > 20
echo $DISCORD_BOT_TOKEN | wc -c  # Should be > 50

# Test API connectivity
python -c "
import openai
openai.api_key = '$OPENAI_API_KEY'
print(openai.Model.list())
"
```

#### 3. Memory/Resource Issues
```bash
# Check memory usage
python -c "
import psutil
print(f'Memory: {psutil.virtual_memory().percent}%')
print(f'CPU: {psutil.cpu_percent()}%')
"

# Reduce resource limits
export RESOURCE_MEMORY_LIMIT="64"
export RESOURCE_CPU_LIMIT="50"
```

#### 4. Secrets Management Issues
```bash
# Verify encryption key
python -c "
import base64
key = '$SECRETS_MASTER_KEY'
print(f'Key length: {len(base64.b64decode(key))} bytes (should be 32)')
"

# Check secrets database
sqlite3 secrets.db ".schema secrets"
```

#### 5. Audit Trail Issues
```bash
# Verify audit keys
openssl rsa -in audit_keys/audit_private.pem -check
openssl rsa -in audit_keys/audit_private.pem -pubout | \
  diff - audit_keys/audit_public.pem

# Check audit database integrity
python -c "
from ciris_engine.audit.verifier import AuditVerifier
verifier = AuditVerifier()
print(verifier.verify_chain_integrity())
"
```

### Performance Optimization

#### 1. Database Optimization
```bash
# Enable SQLite optimizations
sqlite3 data/ciris_engine.db "PRAGMA optimize;"
sqlite3 data/ciris_engine.db "VACUUM;"
```

#### 2. Memory Optimization
```yaml
# Reduce buffer sizes in config
telemetry:
  buffer_size: 500
workflow:
  max_active_thoughts: 25
```

#### 3. Network Optimization
```yaml
# Optimize timeouts
llm_services:
  openai:
    timeout_seconds: 15.0
    max_retries: 2
```

### Emergency Procedures

#### 1. Emergency Shutdown
```bash
# Preferred: Use graceful shutdown script for clean exit
./deployment/graceful-shutdown.py --message "Emergency shutdown"

# Manual graceful shutdown
kill -TERM $(pgrep -f "python main.py")

# Force shutdown if needed (avoid - breaks staged deployment)
kill -KILL $(pgrep -f "python main.py")
```

#### 1.5. Staged Deployment Recovery
```bash
# If staged deployment is stuck, check for staged container
docker ps -a | grep staged

# Complete staged deployment manually
docker stop ciris-agent-datum
docker rm ciris-agent-datum
docker rename ciris-agent-datum-staged ciris-agent-datum
docker start ciris-agent-datum

# If no staged container but deployment needed
cd /home/ciris/CIRISAgent
./deployment/deploy-staged.sh
```

#### 2. Database Recovery
```bash
# Backup current database
cp data/ciris_engine.db data/ciris_engine.db.backup

# Restore from backup
cp data/ciris_engine.db.backup data/ciris_engine.db

# Reset database (last resort)
rm data/ciris_engine.db
python -c "from ciris_engine.persistence.db.setup import initialize_database; initialize_database()"
```

#### 3. Key Recovery
```bash
# Regenerate secrets key (will invalidate stored secrets)
openssl rand -base64 32 > new_secrets_master.key

# Regenerate audit keys (will break chain verification)
openssl genrsa -out new_audit_private.pem 4096
openssl rsa -in new_audit_private.pem -pubout -out new_audit_public.pem
```

### Getting Help

- **Logs**: Always check `logs/latest.log` first
- **Audit Trail**: Review `audit_logs.jsonl` for security events
- **Configuration**: Verify configuration with `python -c "from ciris_engine.config import load_config; print(load_config())"`
- **Tests**: Run test suite with `pytest tests/`
- **Documentation**: See module READMEs in `ciris_engine/*/README.md`

For additional support, ensure you have:
1. Current log files
2. Configuration files (redacted)
3. Error messages with full stack traces
4. System resource information
5. Version information: `python --version`, `pip list`

---

*Copyright © 2025 Eric Moore and CIRIS L3C - Apache 2.0 License*
