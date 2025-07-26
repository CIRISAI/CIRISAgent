# CIRISManager CLI v2

A command-line interface for managing CIRIS agents. This CLI makes it easy to create, list, delete, and monitor agents without using the web GUI.

## Features

- 🚀 Create agents with different modes (service, discord, tool)
- 📋 List all running agents with their status
- 🗑️ Delete agents
- 📊 Check agent status
- 🧪 Test the new CIRIS_MODE feature
- 📝 List available templates

## Quick Start

```bash
# List all agents
python ciris_manager/cli_v2.py agent list

# Create a service agent (web API)
python ciris_manager/cli_v2.py agent create --name my-api --mode service

# Create a Discord bot
python ciris_manager/cli_v2.py agent create --name my-bot --mode discord \
    --env DISCORD_BOT_TOKEN=xxx --env DISCORD_HOME_CHANNEL_ID=yyy

# Test the new mode feature
python ciris_manager/cli_v2.py test-mode --mode service
```

## Commands

### Agent Management

#### List Agents
```bash
python ciris_manager/cli_v2.py agent list
```
Shows all agents with their ID, name, status, mode, port, and container.

#### Create Agent
```bash
python ciris_manager/cli_v2.py agent create --name <name> --mode <mode> [options]
```

Options:
- `--name, -n`: Agent name (required)
- `--template, -t`: Template to use (default: 'default')
- `--mode, -m`: Agent mode: service, discord, tool, or comma-separated
- `--env, -e`: Environment variables (KEY=VALUE), can be used multiple times
- `--env-file`: Load environment from .env file
- `--wa-signature`: Wise Authority signature for non-pre-approved templates

Examples:
```bash
# Service mode (web API + GUI)
python ciris_manager/cli_v2.py agent create --name api-bot --mode service

# Discord bot mode
python ciris_manager/cli_v2.py agent create --name discord-bot --mode discord \
    --env DISCORD_BOT_TOKEN=xxx --env DISCORD_HOME_CHANNEL_ID=yyy

# Multi-mode agent (accessible via both web and Discord)
python ciris_manager/cli_v2.py agent create --name multi --mode service,discord \
    --env-file discord.env

# Tool mode (CLI tool, exits after startup)
python ciris_manager/cli_v2.py agent create --name analyzer --mode tool
```

#### Delete Agent
```bash
python ciris_manager/cli_v2.py agent delete <agent_id> [--yes]
```

Options:
- `--yes, -y`: Skip confirmation prompt

#### Check Agent Status
```bash
python ciris_manager/cli_v2.py agent status <agent_id>
```
Shows detailed information about a specific agent.

### Template Management

#### List Templates
```bash
python ciris_manager/cli_v2.py template list
```
Shows all available templates and which ones are pre-approved.

### Testing Features

#### Test Mode
```bash
python ciris_manager/cli_v2.py test-mode --mode <mode>
```
Creates a temporary test agent with the specified mode to verify it works correctly.

## Environment Variables

- `CIRIS_MANAGER_URL`: Manager API URL (default: http://localhost:8888)
- `CIRIS_MANAGER_TOKEN`: Authentication token (if required)

## Understanding Modes

The new `CIRIS_MODE` environment variable replaces the old `CIRIS_ADAPTER`:

- `service`: Web API mode (was `api`) - Agent runs as a web service
- `discord`: Discord bot mode - Agent connects to Discord
- `tool`: CLI tool mode (was `cli`) - Agent runs once and exits
- `service,discord`: Multi-mode - Agent is accessible via both web and Discord

The CLI automatically sets both `CIRIS_MODE` (new) and `CIRIS_ADAPTER` (old) for backward compatibility.

## Examples

### Testing the New Mode System

```bash
# Test service mode
python ciris_manager/cli_v2.py test-mode --mode service

# Test multi-mode
python ciris_manager/cli_v2.py test-mode --mode service,discord

# The test command will:
# 1. Create a test agent with the specified mode
# 2. Verify it's running
# 3. Show the actual mode from the environment
# 4. Offer to clean up the test agent
```

### Production Examples

```bash
# Create a production API agent
python ciris_manager/cli_v2.py agent create \
    --name prod-api \
    --template scout \
    --mode service \
    --env OPENAI_API_KEY=$OPENAI_API_KEY

# Create a Discord moderation bot
python ciris_manager/cli_v2.py agent create \
    --name discord-mod \
    --template echo-core \
    --mode discord \
    --env-file /path/to/discord-config.env

# Create a multi-interface agent
python ciris_manager/cli_v2.py agent create \
    --name multi-agent \
    --template sage \
    --mode service,discord \
    --env OPENAI_API_KEY=$OPENAI_API_KEY \
    --env DISCORD_BOT_TOKEN=$DISCORD_TOKEN
```

## Why CLI First?

Building features in the CLI first has several advantages:

1. **Faster Development**: No UI components to build
2. **Better Testing**: Easy to script and automate tests
3. **Clear API Design**: Forces clean separation of concerns
4. **Automation Ready**: Can be used in scripts and CI/CD
5. **Debugging**: Easier to see exactly what's happening

Once a feature works well in the CLI, it's much easier to add it to the GUI.