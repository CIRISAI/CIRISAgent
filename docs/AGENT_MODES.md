# CIRIS Agent Modes

## Overview

CIRIS agents can run in different modes depending on your use case. The mode determines:
- How the agent receives input and sends output
- Whether the agent runs continuously or exits after processing
- What interfaces are available for interaction

## Available Modes

### 🌐 Service Mode (`CIRIS_MODE=service`)
**Use case**: Web services, REST APIs, GUI access

- Starts an HTTP server on port 8080
- Provides REST API endpoints for interaction
- Compatible with CIRIS GUI for visual management
- **Runs continuously** (daemon mode)

```bash
# Docker example
docker run -e CIRIS_MODE=service -p 8080:8080 ciris-agent

# Direct execution
CIRIS_MODE=service python main.py
```

### 💬 Discord Mode (`CIRIS_MODE=discord`)
**Use case**: Discord bots, community moderation

- Connects to Discord as a bot
- Monitors specified channels for commands
- Requires Discord bot token and channel configuration
- **Runs continuously** (daemon mode)

```bash
# Requires Discord configuration
CIRIS_MODE=discord \
DISCORD_BOT_TOKEN=your_token \
DISCORD_HOME_CHANNEL_ID=channel_id \
python main.py
```

### 🛠️ Tool Mode (`CIRIS_MODE=tool`)
**Use case**: CLI tools, one-shot operations, scripts

- Interactive command-line interface
- Processes input and exits
- Perfect for automation and scripting
- **Exits after processing** (not a daemon)

```bash
# Direct CLI interaction
CIRIS_MODE=tool python main.py process "Analyze this text"

# Pipe data through CIRIS
echo "Hello world" | CIRIS_MODE=tool python main.py
```

### 🔀 Multi-Mode (`CIRIS_MODE=service,discord`)
**Use case**: Agents accessible through multiple interfaces

- Run multiple modes simultaneously
- Common: `service,discord` for web + Discord access
- Each mode operates independently

```bash
# Agent accessible via both web API and Discord
CIRIS_MODE=service,discord \
DISCORD_BOT_TOKEN=your_token \
python main.py
```

## Mode Selection Logic

1. **Explicit CLI argument** (highest priority)
   ```bash
   python main.py --adapter api
   ```

2. **Environment variable** (recommended for containers)
   ```bash
   CIRIS_MODE=service python main.py
   ```

3. **Default behavior** (lowest priority)
   - Defaults to `tool` mode (CLI)
   - This ensures safe, predictable behavior

## Common Patterns for LLM Agents

### Agent as a Service
```yaml
# docker-compose.yml
services:
  my-agent:
    image: ciris-agent
    environment:
      - CIRIS_MODE=service
      - CIRIS_AGENT_ID=my-agent
    ports:
      - "8080:8080"
```

### Agent as a Discord Bot
```yaml
services:
  discord-bot:
    image: ciris-agent
    environment:
      - CIRIS_MODE=discord
      - DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}
      - DISCORD_HOME_CHANNEL_ID=${CHANNEL_ID}
```

### Agent as a CLI Tool
```bash
# Use in scripts
alias ciris='docker run --rm -i ciris-agent'
echo "Analyze this" | ciris
```

## Migration from CIRIS_ADAPTER

For backward compatibility, `CIRIS_ADAPTER` still works:
- `CIRIS_ADAPTER=api` → `CIRIS_MODE=service`
- `CIRIS_ADAPTER=cli` → `CIRIS_MODE=tool`
- `CIRIS_ADAPTER=discord` → `CIRIS_MODE=discord`

New deployments should use `CIRIS_MODE` for clarity.

## Troubleshooting

**Agent exits immediately?**
- You're in tool mode (default). Set `CIRIS_MODE=service` for continuous operation.

**Can't access web interface?**
- Ensure `CIRIS_MODE=service` is set
- Check port 8080 is exposed and not blocked

**Discord bot not responding?**
- Verify `CIRIS_MODE=discord` or `CIRIS_MODE=service,discord`
- Check Discord token and channel IDs are correct

## Design Philosophy

The mode system reflects CIRIS's nature as a flexible LLM agent framework:

1. **Tool Mode**: For when you need an intelligent command-line assistant
2. **Service Mode**: For when you need an always-available AI service
3. **Discord Mode**: For when you need an AI presence in your community
4. **Multi-Mode**: For when you need all of the above

Each mode is optimized for its use case, ensuring CIRIS agents behave predictably and efficiently in any deployment scenario.