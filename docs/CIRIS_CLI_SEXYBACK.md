# CIRIS CLI: The Sexyback Spec 🔥

> Deploy agents like you're conducting a symphony. Auth like butter. Output like poetry.

## Quick Hit: What This Is

```bash
# Old and busted
curl -X POST localhost:8888/manager/v1/agents -H "Authorization: Bearer ..." -d '{"template":"discord","name":"my-bot","environment":{...}}'

# New hotness
ciris create discord-bot --mode discord --env DISCORD_TOKEN=$TOKEN
```

## Core Philosophy

1. **Humans First, Machines Close Second**
2. **Auth That Doesn't Suck**
3. **Progressive Power**
4. **Claude Code Native**

## The Setup (30 seconds)

```bash
# Install
pip install ciris-cli  # or brew install ciris

# Init
ciris init
# → Creates ~/.ciris/config.yaml
# → Sets up token storage
# → Detects local manager

# Auth (pick your fighter)
ciris auth login          # Browser flow for humans
ciris auth token $TOKEN   # Direct token for CI/CD
ciris auth dev            # Bypass for local dev

# Verify
ciris status
✓ Manager: http://localhost:8888
✓ Auth: valid (expires in 23h)
✓ Agents: 2 running
```

## Daily Driver Commands

### Create Agents (The Money Shot)

```bash
# Simplest possible
ciris create my-bot

# With personality
ciris create discord-bot --template echo-core --mode discord

# Full send
ciris create prod-bot \
  --template sage \
  --mode service,discord \
  --env-file prod.env \
  --env EXTRA_VAR=value \
  --port 8090 \
  --wait \
  --follow-logs
```

### List & Manage

```bash
# See what's up
ciris ls
NAME         STATUS   MODE      PORT   UPTIME
discord-bot  running  discord   8081   2h ago
api-bot      running  service   8082   5m ago

# Get details
ciris inspect discord-bot

# Logs (with style)
ciris logs discord-bot --follow --highlight ERROR,WARN

# Lifecycle
ciris stop discord-bot
ciris start discord-bot  
ciris restart discord-bot
ciris rm discord-bot
```

### Fleet Ops (Power Mode)

```bash
# Deploy multiple agents from spec
ciris fleet deploy discord-moderation.yaml

# Scale existing
ciris fleet scale api-workers --replicas 10

# Rolling update
ciris fleet update --template sage-v2
```

## The Secret Sauce

### 1. Output Modes (Both Sexy)

```bash
# Human mode (default)
ciris create my-bot
Creating agent 'my-bot'... ✓
│ Template validated
│ Port allocated: 8082
│ Container started
└ Health check passed

# Machine mode
CIRIS_OUTPUT=json ciris create my-bot
{"agent_id":"my-bot-abc123","port":8082,"status":"running"}

# Or per command
ciris create my-bot --json
ciris create my-bot -o yaml
```

### 2. Auth That Respects You

```bash
# Interactive (opens browser)
ciris auth login
→ Opening browser...
→ Waiting for auth...
✓ Authenticated as tyler@ciris.ai

# CI/CD friendly
export CIRIS_TOKEN=xxx
ciris create bot  # Just works

# Local dev mode (no auth)
ciris --local create bot

# Service accounts (future)
ciris auth service-account --key-file sa.json
```

### 3. Smart Defaults, No Magic

```yaml
# ~/.ciris/config.yaml (auto-created)
manager_url: http://localhost:8888
auth:
  token_file: ~/.ciris/tokens.json
  provider: google
defaults:
  template: default
  mode: service
  output: pretty
aliases:
  ls: agent list
  rm: agent delete
  logs: agent logs
```

### 4. Composability

```bash
# UNIX philosophy
ciris ls --json | jq '.[] | select(.status=="error")' | xargs ciris rm

# But also high-level
ciris fleet health-check --restart-failed

# Pipe friendly
ciris logs my-bot | grep ERROR | ciris notify slack
```

## Implementation Checklist

- [ ] **Core Framework**: Click or Typer
- [ ] **Auth Module**: OAuth device flow + token management
- [ ] **Output Formatters**: Human (rich tables) + JSON/YAML
- [ ] **Config System**: YAML with env var overrides
- [ ] **Error Handling**: Clear messages + proper exit codes
- [ ] **Streaming**: Logs, events, progress bars
- [ ] **Completion**: Bash/ZSH/Fish autocomplete
- [ ] **Testing**: Every command has --dry-run
- [ ] **Help System**: Examples in every --help

## Command Structure

```
ciris
├── auth
│   ├── login      # Browser-based OAuth
│   ├── logout     # Clear stored tokens
│   ├── token      # Manage tokens directly
│   └── status     # Check auth status
├── agent / <default>
│   ├── create     # Deploy new agent
│   ├── list (ls)  # List all agents
│   ├── delete (rm)# Remove agent
│   ├── logs       # Stream logs
│   ├── exec       # Run command in agent
│   ├── inspect    # Detailed info
│   └── update     # Update agent config
├── fleet
│   ├── deploy     # Deploy from YAML spec
│   ├── scale      # Adjust replicas
│   └── update     # Rolling updates
├── config
│   ├── get        # Show config values
│   ├── set        # Update config
│   └── init       # Initial setup
└── debug
    ├── api        # Raw API calls
    └── doctor     # Diagnose issues
```

## Environment Variables

```bash
CIRIS_MANAGER_URL    # Override manager location
CIRIS_TOKEN          # Auth token
CIRIS_OUTPUT         # json|yaml|pretty
CIRIS_NO_COLOR       # Disable colors
CIRIS_QUIET          # Suppress non-essential output
CIRIS_LOCAL          # Local dev mode (no auth)
```

## The Claude Code Experience

```python
# In scripts/notebooks
from ciris import CLI

cli = CLI(output='json')
agents = cli.list_agents()
cli.create_agent('worker', template='sage', env={'KEY': 'value'})
```

## Error Handling (Always Helpful)

```bash
# Clear errors for humans
$ ciris create test --template nonexistent
Error: Template 'nonexistent' not found

Available templates:
  • default - Base agent template
  • sage - Thoughtful responder
  • scout - Action-oriented
  
Try: ciris create test --template sage

# Structured for machines
$ ciris create test --template nonexistent --json 2>&1
{
  "error": "TemplateNotFound",
  "template": "nonexistent", 
  "available": ["default", "sage", "scout"],
  "suggestion": "ciris create test --template sage"
}
```

## Production Patterns

```bash
# Deploy with checks
ciris create prod-api \
  --template api-server \
  --health-check-retries 10 \
  --wait-for-ready \
  --notify-slack "#deploys"

# Graceful updates
ciris fleet update api-workers \
  --strategy rolling \
  --max-unavailable 1 \
  --health-check-interval 5s

# Monitoring integration
ciris agent list --watch --format prometheus | curl -X POST http://pushgateway/metrics
```

## Why This Slaps

1. **It's Fast**: No ceremony, just results
2. **It's Smart**: Knows when you're human vs machine
3. **It's Respectful**: Your tokens are safe, your output is clean
4. **It's Powerful**: From simple creates to complex orchestration
5. **It's Testable**: --dry-run everything, mock modes for CI

This is the CLI that makes you want to use the CLI. Ship it.