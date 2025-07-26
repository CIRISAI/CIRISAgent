# CIRIS RC1 Quick Start Guide

## Prerequisites
- Docker and docker-compose installed
- Port 80 available (for nginx)
- 4GB+ RAM recommended

## Quick Start (5 minutes)

### 1. Start Core Infrastructure
```bash
# Clone the repository
git clone https://github.com/CIRISAI/CIRISAgent.git
cd CIRISAgent

# Start the default agent (Datum)
docker-compose -f docker-compose-api-discord-mock.yml up -d

# Start nginx
docker-compose -f docker-compose-nginx.yml up -d

# Configure CIRISManager
mkdir -p ~/.config/ciris-manager
cat > ~/.config/ciris-manager/config.yml << EOF
manager:
  agents_directory: ~/.config/ciris-manager/agents
  manifest_path: ~/.config/ciris-manager/pre-approved-templates.json
  templates_directory: ./ciris_templates
nginx:
  config_dir: /home/$USER/nginx
  container_name: ciris-nginx
EOF

# Start CIRISManager API
CIRIS_MANAGER_CONFIG=~/.config/ciris-manager/config.yml \
  nohup python deployment/run-ciris-manager-api.py > /tmp/ciris-manager.log 2>&1 &

# Start the GUI
cd CIRISGUI/apps/agui
npm install
npm run dev
```

### 2. Access the System
- **GUI**: http://localhost
- **Default Agent API**: http://localhost/v1/system/health
- **Manager API**: http://localhost:8888/manager/v1/agents

### 3. Create Your First Agent

#### Via GUI:
1. Open http://localhost
2. Click "Create Agent"
3. Enter name: "My Scout"
4. Select template: "scout"
5. Click "Create"

#### Via API:
```bash
curl -X POST http://localhost:8888/manager/v1/agents \
  -H "Content-Type: application/json" \
  -d '{
    "template": "scout",
    "name": "My Scout",
    "environment": {
      "CIRIS_ADAPTER": "api"
    }
  }'
```

### 4. Interact with Agents

```bash
# Default agent (Datum)
curl -X POST http://localhost/v1/agent/interact \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer admin:ciris_admin_password" \
  -d '{"message": "Hello!", "channel_id": "api_test"}'

# Specific agent
curl -X POST http://localhost/api/my-scout-abc123/v1/agent/interact \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer admin:ciris_admin_password" \
  -d '{"message": "Hello Scout!", "channel_id": "api_test"}'
```

## Important Environment Variables

### Required for API Agents
- `CIRIS_ADAPTER=api` - Without this, agents exit immediately
- `CIRIS_API_HOST=0.0.0.0` - Required for API adapter

### For Discord Agents
- `CIRIS_ADAPTER=discord`
- `DISCORD_TOKEN=<your-bot-token>`
- `DISCORD_HOME_CHANNEL_ID=<channel-id>`

## Troubleshooting

### Agent keeps restarting
- Check logs: `docker logs ciris-<agent-id>`
- Ensure `CIRIS_ADAPTER=api` is set
- Check incidents: `docker exec <container> tail /app/logs/incidents_latest.log`

### Can't create agents
- Check nginx: `docker logs ciris-nginx`
- Check manager: `tail -f /tmp/ciris-manager.log`
- Ensure all ports are available

### GUI not loading
- Check if port 3000 is in use
- Ensure npm install completed
- Check browser console for errors

## Architecture Overview

```
[Browser] → [nginx:80] → ├─ [GUI:3000] → [Manager:8888] → [Docker]
                         ├─ [Manager:8888]              ↘
                         └─ [Agents:808X] ← ← ← ← ← ← ← ← [Agents]
```

## Next Steps
- Configure Discord integration for agents
- Set up OAuth authentication
- Deploy to production with proper certificates
- Read the full documentation at `docs/`