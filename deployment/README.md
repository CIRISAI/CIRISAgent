# CIRIS Deployment

This directory contains the deployment configuration for the CIRIS system.

## Current Status (July 20, 2025)
- **CIRISManager**: Fully integrated for dynamic agent discovery
- **OAuth**: Google OAuth with permission request system
- **GUI**: Dynamic agent selection via CIRISManager
- **CI/CD**: Fully automated deployment pipeline

## Key Services

### CIRISManager
- Provides agent discovery API at `/manager/v1/*`
- Monitors container health and lifecycle
- Runs as systemd service: `ciris-manager-api.service`
- API-only mode in production (no container management)

### Deployment Environments

### Development (Mock LLM)
- Single Datum agent with mock LLM for testing
- No external API dependencies
- CIRISManager for local agent discovery
- GUI with hot reload on port 3000

### Production (agents.ciris.ai)
- Currently single Datum agent (multi-agent ready)
- Mock LLM for development (real LLM ready)
- Full OAuth integration with Google
- Nginx containerized with dynamic routing

## Production Architecture

The production system consists of 5 CIRIS agents, each with a specific role:

1. **Datum** (port 8080) - Primary decision-making agent
2. **Sage** (port 8081) - Wisdom and deep analysis
3. **Scout** (port 8082) - Information gathering and reconnaissance  
4. **Echo-Core** (port 8083) - Core reasoning and consistency
5. **Echo-Speculative** (port 8084) - Speculative reasoning and possibilities

## Production Environment Files

On the production server, each agent has its own `.env` file:
- `/path/to/datum.env`
- `/path/to/sage.env`
- `/path/to/scout.env`
- `/path/to/echo-core.env`
- `/path/to/echo-speculative.env`

Each `.env` file should contain:
```bash
# LLM Configuration
OPENAI_API_KEY=...
OPENAI_API_BASE=...
OPENAI_MODEL_NAME=...

# Discord Configuration (if different per agent)
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_ID=...
DISCORD_DEFERRAL_CHANNEL_ID=...
WA_USER_ID=...

# Agent-specific settings
CIRIS_AGENT_NAME=Datum  # Or Sage, Scout, etc.
```

## Deployment Commands

### Development Environment
```bash
# Deploy single agent with mock LLM
docker-compose -f docker-compose.dev.yml up -d
```

### Production Environment
```bash
# Deploy all 5 agents with real LLM
docker-compose -f docker-compose.production.yml up -d
```

## Automated CI/CD

Production deployment is fully automated via GitHub Actions:
1. Push to main branch triggers the pipeline
2. Tests run in Docker containers
3. Docker images built and pushed to ghcr.io
4. Automatic deployment to production server
5. Health checks verify successful deployment

## Adapter Priority Configuration

The adapters are configured with the following priorities:
- **API Adapter**: Priority.CRITICAL (highest)
- **Discord Adapter**: Priority.NORMAL (medium)
- **CLI Adapter**: Priority.LOW (lowest)

This ensures that API requests take precedence, followed by Discord, then CLI.

## NGINX Configuration

The production NGINX configuration (`nginx/agents.ciris.ai.conf`) routes:
- `/` → GUI on port 3000
- `/api/datum/*` → Datum agent on port 8080
- `/api/sage/*` → Sage agent on port 8081
- `/api/scout/*` → Scout agent on port 8082
- `/api/echo-core/*` → Echo-Core agent on port 8083
- `/api/echo-speculative/*` → Echo-Speculative agent on port 8084

## Local Development

For local development and testing:

```bash
# Run with mock LLM
python main.py --adapter api --adapter discord --mock-llm --timeout 60

# Or use Docker
docker-compose -f docker-compose.dev.yml up -d
```

## CIRISManager - Agent Lifecycle Management

CIRISManager runs as a systemd service to provide:
- Automatic container updates (leverages Docker's restart policy)
- Crash loop detection and prevention
- Agent discovery API for GUI
- Future: Agent creation with WA signatures

### Installation

```bash
# Install CIRISManager
cd /home/ciris/CIRISAgent
pip install -e .

# Create config directory
sudo mkdir -p /etc/ciris-manager
sudo chown $USER:$USER /etc/ciris-manager

# Generate default config
ciris-manager --generate-config --config /etc/ciris-manager/config.yml

# Install systemd service
sudo cp deployment/ciris-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ciris-manager
sudo systemctl start ciris-manager
```

### Configuration

Edit `/etc/ciris-manager/config.yml`:
```yaml
docker:
  compose_file: /home/ciris/CIRISAgent/deployment/docker-compose.yml

watchdog:
  check_interval: 30  # Check every 30 seconds
  crash_threshold: 3  # Stop after 3 crashes
  crash_window: 300   # Within 5 minutes

container_management:
  interval: 60  # Run docker-compose up -d every 60 seconds
```

### How It Works

1. **Automatic Updates**: Runs `docker-compose up -d` every 60 seconds
   - Stopped containers start with latest image
   - Running containers are unaffected
   - Works with `restart: unless-stopped` policy

2. **Crash Prevention**: Monitors for crash loops
   - Detects 3+ crashes in 5 minutes
   - Stops the container to prevent infinite restarts
   - Alerts for manual intervention

### Monitoring CIRISManager

```bash
# Check service status
sudo systemctl status ciris-manager

# View logs
sudo journalctl -u ciris-manager -f

# Check manager health
curl http://localhost:9999/status  # When API is implemented
```

## Agent Monitoring

Check agent health:
```bash
# Individual agents
curl http://localhost:8080/v1/system/health  # Datum
curl http://localhost:8081/v1/system/health  # Sage
# etc...

# Through NGINX
curl https://agents.ciris.ai/api/datum/system/health
```

View logs:
```bash
docker logs ciris-agent-datum
docker logs ciris-agent-sage
# etc...
```