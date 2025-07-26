# CIRISManager CLI - What Actually Works

## Two Different CLIs Exist

### 1. Service CLI (`cli.py`) - Just starts the manager
```bash
# Start the manager service
python -m ciris_manager.cli --config ~/.config/ciris-manager/config.yml

# Generate a config file
python -m ciris_manager.cli --generate-config
```

### 2. Management CLI (`cli_new.py`) - Actually manages agents
```bash
# This is what we'll focus on
python -m ciris_manager.cli_new <command>
```

## Management CLI Commands That Work

### List Agents ✅ WORKS
```bash
python -m ciris_manager.cli_new agent list
```
Shows running agents with their ID, name, status, mode, port, and container name.

### List Templates ✅ WORKS
```bash
python -m ciris_manager.cli_new template list
```
Shows available templates and which ones need WA signatures.

### Create Agent ✅ WORKS (with caveats)
```bash
python -m ciris_manager.cli_new agent create \
  --name test-agent \
  --template default \
  --mode service
```

**What happens:**
1. Calls CIRISManager API
2. Manager creates docker-compose.yml
3. Starts container with name like `ciris-test-agent-abc123`
4. Agent gets a port (8080+)

**Important:** The `--mode` sets BOTH:
- `CIRIS_MODE=service` (new variable)
- `CIRIS_ADAPTER=api` (old variable for compatibility)

### Delete Agent ✅ WORKS
```bash
python -m ciris_manager.cli_new agent delete <agent-id>
```
Stops and removes the container.

### Agent Status ✅ WORKS
```bash
python -m ciris_manager.cli_new agent status <agent-id>
```
Shows detailed info about a specific agent.

### Test Mode ✅ WORKS
```bash
python -m ciris_manager.cli_new test-mode --mode service
```
Creates a temporary test agent to verify modes work.

## Environment Variables

### Setting them during creation ✅ WORKS
```bash
python -m ciris_manager.cli_new agent create \
  --name my-bot \
  --template default \
  --mode discord \
  --env DISCORD_BOT_TOKEN=xxx \
  --env DISCORD_HOME_CHANNEL_ID=123456
```

### Loading from file ✅ WORKS
```bash
python -m ciris_manager.cli_new agent create \
  --name my-bot \
  --template default \
  --mode discord \
  --env-file discord.env
```

## What Each Mode Actually Does

Based on testing:

- `--mode service` → Sets `CIRIS_ADAPTER=api` → Agent starts web server
- `--mode discord` → Sets `CIRIS_ADAPTER=discord` → Agent connects to Discord
- `--mode tool` → Sets `CIRIS_ADAPTER=cli` → Agent exits immediately
- `--mode service,discord` → Sets `CIRIS_ADAPTER=api,discord` → Multi-mode

## Current Limitations

1. **No batch operations** - Can't create multiple agents at once
2. **No fleet management** - Each agent is independent
3. **Templates are basic** - Just YAML files with prompts
4. **No agent communication** - Agents don't know about each other
5. **Manual nginx config** - May need to update nginx manually

## For RC1 Discord Moderation

To deploy 5 Discord bots, you need to run create command 5 times:

```bash
# Bot 1 - General channel
python -m ciris_manager.cli_new agent create \
  --name discord-general \
  --template echo-core \
  --mode discord \
  --env DISCORD_BOT_TOKEN=$TOKEN \
  --env DISCORD_HOME_CHANNEL_ID=$GENERAL_CHANNEL_ID

# Bot 2 - Support channel  
python -m ciris_manager.cli_new agent create \
  --name discord-support \
  --template echo-core \
  --mode discord \
  --env DISCORD_BOT_TOKEN=$TOKEN \
  --env DISCORD_HOME_CHANNEL_ID=$SUPPORT_CHANNEL_ID

# ... repeat for each channel
```

Each bot:
- Gets its own container
- Gets its own port (even though Discord bots don't need ports)
- Runs independently
- Can't share context with other bots

## Quick Test Commands

```bash
# See what's running
python -m ciris_manager.cli_new agent list

# Create a test web agent
python -m ciris_manager.cli_new agent create --name web-test --mode service

# Create a test Discord bot (will fail without valid token)
python -m ciris_manager.cli_new agent create --name discord-test --mode discord

# Delete test agents
python -m ciris_manager.cli_new agent delete web-test
python -m ciris_manager.cli_new agent delete discord-test
```