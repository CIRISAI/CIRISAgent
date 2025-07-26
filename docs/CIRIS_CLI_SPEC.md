# CIRIS Manager CLI Specification

## Purpose

A command-line interface for managing CIRIS agents locally and in production. Focuses on core functionality needed for deployment and management.

## Core Requirements

1. **Authentication**: Support both local development (no auth) and production (OAuth)
2. **Agent Management**: Create, list, delete, and monitor agents
3. **Environment Support**: Work seamlessly in local and production environments
4. **Output Formats**: Human-readable by default, JSON for automation

## Installation & Setup

```bash
# Install
pip install ciris-cli

# Initialize configuration
ciris init

# This creates ~/.ciris/config.yaml:
manager_url: http://localhost:8888  # Auto-detected or prompted
auth:
  method: local  # or 'oauth'
output:
  format: table  # or 'json'
```

## Authentication

### Local Development
```bash
# No authentication required
ciris --local <command>

# Or set in config
ciris config set auth.method local
```

### Production
```bash
# OAuth login (opens browser)
ciris auth login

# Direct token (for CI/CD)
export CIRIS_TOKEN=<token>
ciris <command>

# Or
ciris --token <token> <command>
```

## Core Commands

### Agent Management

#### Create Agent
```bash
ciris agent create <name> [options]

Options:
  --template TEXT      Agent template (default: "default")
  --mode TEXT          Agent mode: service, discord, tool
  --env KEY=VALUE      Environment variables (repeatable)
  --env-file PATH      Load environment from file
  --wait               Wait for agent to be ready
  --output FORMAT      Output format: table, json

Examples:
  # Basic agent
  ciris agent create my-agent
  
  # Discord bot
  ciris agent create discord-bot \
    --template echo-core \
    --mode discord \
    --env DISCORD_BOT_TOKEN=$TOKEN \
    --env DISCORD_HOME_CHANNEL_ID=$CHANNEL_ID
  
  # From environment file
  ciris agent create prod-api --env-file production.env
```

#### List Agents
```bash
ciris agent list [options]

Options:
  --output FORMAT      Output format: table, json
  --filter STATUS      Filter by status: running, stopped, error

Example output (table):
NAME         ID              STATUS    MODE      PORT    CREATED
my-agent     my-agent-abc    running   service   8081    2h ago
discord-bot  discord-bot-xyz running   discord   8082    1h ago

Example output (json):
[
  {
    "name": "my-agent",
    "id": "my-agent-abc",
    "status": "running",
    "mode": "service",
    "port": 8081,
    "created": "2025-07-26T10:00:00Z"
  }
]
```

#### Delete Agent
```bash
ciris agent delete <name> [options]

Options:
  --force              Skip confirmation

Example:
  ciris agent delete my-agent
  Are you sure? [y/N]: y
  Agent 'my-agent' deleted.
```

#### View Agent Logs
```bash
ciris agent logs <name> [options]

Options:
  --follow             Follow log output
  --lines INT          Number of lines to show
  --since DURATION     Show logs since duration (e.g., 5m, 1h)

Example:
  ciris agent logs discord-bot --follow --since 10m
```

### Configuration Management

```bash
# View configuration
ciris config show

# Set configuration values
ciris config set manager_url https://manager.prod.ciris.ai
ciris config set output.format json

# Get specific value
ciris config get auth.method
```

## Environment Variables

```bash
CIRIS_MANAGER_URL    # Override manager URL
CIRIS_TOKEN          # Authentication token
CIRIS_OUTPUT         # Output format: table, json
CIRIS_CONFIG         # Config file location (default: ~/.ciris/config.yaml)
```

## Deployment Workflows

### Local Development
```bash
# Start with local manager
ciris config set auth.method local
ciris config set manager_url http://localhost:8888

# Create test agent
ciris agent create test-agent --mode service

# Monitor
ciris agent logs test-agent --follow
```

### Production Deployment
```bash
# Configure for production
ciris config set manager_url https://manager.ciris.ai
ciris auth login

# Deploy agents
ciris agent create api-1 --template api --env-file prod.env
ciris agent create api-2 --template api --env-file prod.env
ciris agent create discord-mod --template echo-core --mode discord --env-file discord.env

# Monitor
ciris agent list
ciris agent logs api-1 --follow
```

### CI/CD Integration
```bash
#!/bin/bash
# deploy.sh

export CIRIS_TOKEN=$CI_CIRIS_TOKEN
export CIRIS_MANAGER_URL=$PROD_MANAGER_URL

# Deploy with error handling
if ciris agent create prod-api --env-file prod.env --wait; then
  echo "Deployment successful"
else
  echo "Deployment failed"
  exit 1
fi
```

## Output Format Examples

### Human-Readable (default)
```
$ ciris agent create my-bot --template discord
Creating agent 'my-bot'...
✓ Template: discord
✓ Port allocated: 8082
✓ Container started
✓ Health check passed

Agent created successfully.
```

### JSON (for automation)
```
$ ciris agent create my-bot --template discord --output json
{
  "name": "my-bot",
  "id": "my-bot-abc123",
  "template": "discord",
  "port": 8082,
  "status": "running",
  "container": "ciris-my-bot-abc123"
}
```

## Error Handling

```bash
# Clear error messages
$ ciris agent create test --template nonexistent
Error: Template 'nonexistent' not found.
Available templates: default, sage, scout, echo, echo-core

# Proper exit codes
$ ciris agent delete nonexistent
Error: Agent 'nonexistent' not found.
$ echo $?
1
```

## Implementation Notes

1. **Framework**: Use Click for command parsing
2. **Configuration**: YAML with environment variable overrides
3. **HTTP Client**: Requests with retry logic
4. **Authentication**: OAuth device flow for interactive, token for automation
5. **Output**: Tabulate for tables, built-in JSON encoder
6. **Error Handling**: Clear messages, proper exit codes

## Minimal MVP Commands

For initial implementation, focus on:
1. `ciris init` - Setup configuration
2. `ciris auth login` - OAuth authentication
3. `ciris agent create` - Deploy agents
4. `ciris agent list` - View agents
5. `ciris agent delete` - Remove agents
6. `ciris agent logs` - View logs

This provides the essential functionality for both local development and production deployment.