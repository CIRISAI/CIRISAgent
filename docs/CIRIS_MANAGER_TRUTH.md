# CIRISManager: What It ACTUALLY Is

## Current Reality Check

### The Existing CLI (`ciris_manager/cli.py`)

This CLI does exactly TWO things:
1. **Starts the manager service**: `python ciris_manager/cli.py`
2. **Generates a config file**: `python ciris_manager/cli.py --generate-config`

That's it. No agent management. It's a service starter.

### How Do You Actually Manage Agents?

Right now, you have THREE options:

1. **Use the Web GUI** (if it's running)
   - Go to http://localhost:3000
   - Click buttons to create/delete agents

2. **Call the API directly**
   ```bash
   # Create agent
   curl -X POST http://localhost:8888/manager/v1/agents \
     -H "Content-Type: application/json" \
     -d '{"template": "default", "name": "my-agent"}'
   
   # List agents
   curl http://localhost:8888/manager/v1/agents
   
   # Delete agent
   curl -X DELETE http://localhost:8888/manager/v1/agents/my-agent
   ```

3. **Use the Python SDK** (if you write Python code)
   ```python
   from lib.ciris_manager_client import CIRISManagerClient
   client = CIRISManagerClient("http://localhost:8888")
   client.create_agent("default", "my-agent")
   ```

### What CIRISManager ACTUALLY Does

When you call the API to create an agent:

1. **Generates a unique ID**: Like `agent-abc123`
2. **Creates a directory**: `~/.config/ciris-manager/agents/agent-abc123/`
3. **Writes docker-compose.yml**: Using the template + your settings
4. **Runs**: `docker-compose up -d` in that directory
5. **Tracks in registry**: So it knows what it created

When you list agents:
1. **Asks Docker**: "What containers start with 'ciris-'?"
2. **Returns the list**: With status from Docker

When you delete an agent:
1. **Runs**: `docker-compose down` in the agent's directory
2. **Removes**: The directory
3. **Updates**: Its internal registry

### What About Templates?

Templates are YAML files in `ciris_templates/` that define:
- What personality/prompts to use
- What environment variables to set
- What adapters to enable

Example (`ciris_templates/default.yaml`):
```yaml
name: default
description: Datum - baseline agent
prompts:
  system: "You are Datum, a helpful AI assistant..."
```

### What About Modes (CIRIS_MODE)?

This is just an environment variable that tells the agent how to run:
- `CIRIS_MODE=service` → Start web server, keep running
- `CIRIS_MODE=discord` → Connect to Discord, keep running  
- `CIRIS_MODE=tool` → Run once and exit

CIRISManager sets this when creating the docker-compose.yml.

## Authentication Reality

CIRISManager requires OAuth authentication:
1. You need to be logged in with a @ciris.ai Google account
2. The CLI needs a token (from browser session or env var)
3. Without auth, you get 401 Unauthorized

This means:
- The CLI won't work without setting up OAuth first
- You need to login through the web UI to get a token
- Or disable auth in development (if possible)

## The Truth About Our Setup

1. **CIRISManager** = Docker container factory with an API
2. **Current CLI** = Just starts the manager service
3. **Agent Management** = Through API/GUI/SDK only
4. **Templates** = YAML files that become docker-compose configs
5. **Modes** = Environment variables that control agent behavior

## What We Were Building

The `cli_new.py` (formerly cli_v2.py) was going to be a proper management CLI that wraps the API calls. It would let you do:

```bash
python ciris_manager/cli_new.py agent create --name foo --mode service
```

Instead of:
```bash
curl -X POST http://localhost:8888/manager/v1/agents -d '{"name": "foo"}'
```

But right now, that's not what exists. The current system requires either:
- Using the web GUI
- Making raw API calls
- Writing Python code

## For Discord Moderation RC1

To run 5 Discord moderation agents, you currently need to:

1. Start CIRISManager service
2. Make 5 API calls to create agents
3. Each call needs Discord credentials in environment variables
4. Hope the template system passes them through correctly

There's no "fleet" concept. No batch operations. Just one-by-one agent creation.