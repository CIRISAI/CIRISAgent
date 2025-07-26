# CLAUDE.md - CIRIS RC1 Operations Guide

## Architecture: 4 Components

```
[Browser] → [nginx:80] → ├─ [GUI:3000] → [Manager:8888] → [Docker]
                         ├─ [Manager:8888]              ↘
                         └─ [Agents:808X] ← ← ← ← ← ← ← ← [Agents]
```

### 1. Agents (CIRISAgent containers)
- **Purpose**: The actual CIRIS AI instances
- **Config**: Must set `CIRIS_MODE=service` (or `discord`, `tool`)
- **Ports**: 8080-8199 (managed by CIRISManager)
- **Debug**: `docker logs ciris-<agent-id>` and `/app/logs/incidents_latest.log`

#### Agent Modes:
- `service` - Web API + GUI access (stays running)
- `discord` - Discord bot mode (stays running)
- `tool` - CLI tool mode (executes and exits)
- `service,discord` - Multiple modes simultaneously

### 2. GUI (CIRISGUI)
- **Purpose**: Web interface for agent management
- **Start**: `cd CIRISGUI/apps/agui && npm run dev`
- **Port**: 3000 (proxied through nginx on port 80)
- **Config**: Discovers agents via Manager API

### 3. nginx
- **Purpose**: Routes all HTTP traffic
- **Config**: `/home/ciris/nginx/nginx.conf` (auto-generated)
- **Routes**: `/` → GUI, `/manager/v1/*` → Manager, `/api/<agent>/*` → Agents
- **Debug**: `docker logs ciris-nginx`

### 4. Manager (CIRISManager)
- **Purpose**: Creates and manages agent containers
- **Start**: `CIRIS_MANAGER_CONFIG=~/.config/ciris-manager/config.yml nohup python deployment/run-ciris-manager-api.py > /tmp/ciris-manager.log 2>&1 &`
- **Port**: 8888
- **Config**: `~/.config/ciris-manager/config.yml`

## Critical Fixes (July 2025)

1. **nginx routing**: Use `host.docker.internal:PORT` not container names
2. **Agent IDs**: 6-char suffix, no spaces in directories
3. **Manager startup**: Must set `CIRIS_MANAGER_CONFIG` env var
4. **Agent mode**: Must set `CIRIS_MODE=service` or agents exit immediately

## Quick Commands

```bash
# Start everything
docker-compose -f docker-compose-api-discord-mock.yml up -d  # Datum agent
CIRIS_MANAGER_CONFIG=~/.config/ciris-manager/config.yml nohup python deployment/run-ciris-manager-api.py > /tmp/ciris-manager.log 2>&1 &
cd CIRISGUI/apps/agui && npm run dev

# Check health
curl http://localhost/v1/system/health      # Default agent (Datum)
curl http://localhost:8888/manager/v1/agents # Manager API
curl http://localhost                        # GUI

# Create agent
curl -X POST http://localhost:8888/manager/v1/agents \
  -H "Content-Type: application/json" \
  -d '{"template": "scout", "name": "My Agent", "environment": {"CIRIS_ADAPTER": "api"}}'

# Debug
docker logs ciris-<agent-id>
tail -f /tmp/ciris-manager.log
docker exec <container> tail /app/logs/incidents_latest.log
```

## Core Principles

1. **No Dict[str, Any]** - Everything uses Pydantic models
2. **Check incidents_latest.log FIRST** - Never restart until you understand errors
3. **No quick fixes** - This is mission-critical software for global deployment
4. **Docker is truth** - For routing, discovery, and state
5. **NEVER pipe to jq/grep without checking** - Always examine raw output first
6. **Intent-Driven Hybrid Architecture** - Stateful for intent (what should exist), stateless for operations (what does exist)

## Required Environment Variables

### For Agents
- `CIRIS_AGENT_ID` - Unique identifier (auto-set by Manager)
- `CIRIS_MODE` - service|discord|tool (or comma-separated for multi-mode)
  - `service`: Web API + GUI (stays running)
  - `discord`: Discord bot (stays running)  
  - `tool`: CLI tool (exits after processing)
- `CIRIS_API_HOST=0.0.0.0` - For service mode
- `CIRIS_API_PORT=8080` - Internal port

**Note**: `CIRIS_ADAPTER` (api|discord|cli) still works for backward compatibility

### For Discord
- `DISCORD_TOKEN` - Bot token
- `DISCORD_HOME_CHANNEL_ID` - Channel to monitor

## File Locations

- Agent configs: `~/.config/ciris-manager/agents/<agent-id>/`
- Manager config: `~/.config/ciris-manager/config.yml`
- Shared OAuth: `/home/ciris/shared/oauth/`
- Templates: `ciris_templates/`
- nginx config: `/home/ciris/nginx/nginx.conf`

## See Also

- `docs/ARCHITECTURE.md` - Full 21-service architecture
- `docs/ARCHITECTURE_PATTERN.md` - Intent-Driven Hybrid Architecture
- `docs/PHILOSOPHY.md` - No Dicts, No Strings, No Kings
- `docs/AGENT_CREATION_CEREMONY.md` - Formal agent creation
- `CHANGELOG.md` - Historical achievements and fixes