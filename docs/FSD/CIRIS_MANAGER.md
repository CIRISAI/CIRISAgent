# CIRISManager - Functional Specification Document

## Executive Summary

CIRISManager is a lightweight agent lifecycle management service that provides centralized discovery, creation, and lifecycle management for CIRIS agents on a server. It solves the current deployment challenges by monitoring containers for crash loops, notifying agents of updates, and ensuring containers restart with the latest images after any exit.

## Problem Statement

### Current Challenges

1. **No Dynamic Agent Discovery**: The GUI has a hardcoded list of agents, requiring code changes to add new agents
2. **Manual Update Process**: Updates require manual intervention or complex staging scripts
3. **Crash Loop Risk**: No protection against agents that crash repeatedly  
4. **No Central Creation**: Creating new agents requires manual docker-compose editing
5. **Deployment Complexity**: Current staging approach stops containers, breaking graceful shutdown

### Why Periodic `docker-compose up -d`?

The key insight is that `docker-compose up -d` with `restart: unless-stopped` creates a natural update mechanism:

1. **Container stops** (for any reason - graceful shutdown, crash, manual stop)
2. **Docker's restart policy**: 
   - Exit code 0 → Container stays stopped (unless-stopped policy)
   - Non-zero exit → Docker tries to restart
3. **CIRISManager runs `docker-compose up -d`**:
   - Stopped containers start with the **latest image**
   - Running containers are **not affected**
   - No complex staging needed

This approach leverages Docker's natural behavior instead of fighting it.

## Solution Design

### Core Components

```
┌─────────────────────────────────────────────────────┐
│                   CIRISManager                      │
├─────────────────────────────────────────────────────┤
│  API Layer                                          │
│  ┌─────────────────┬───────────────┬─────────────┐ │
│  │ Agent Discovery │ Agent Creation │  Lifecycle  │ │
│  │   GET /agents   │ POST /agents   │ Mgmt (bg)   │ │
│  └─────────────────┴───────────────┴─────────────┘ │
├─────────────────────────────────────────────────────┤
│  Core Services                                      │
│  ┌──────────────┬────────────┬──────────────────┐  │
│  │   Watchdog   │  Notifier  │ Container Mgr    │  │
│  │ (crash loop) │ (updates)  │ (docker-compose) │  │
│  └──────────────┴────────────┴──────────────────┘  │
├─────────────────────────────────────────────────────┤
│  Security Layer                                     │
│  ┌──────────────────────┬──────────────────────┐   │
│  │ WA Signature Verify  │  Local Auth Socket   │   │
│  └──────────────────────┴──────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### API Endpoints

#### 1. Agent Discovery
```yaml
GET /agents
Response:
  agents:
    - id: "agent-datum"
      name: "Datum"
      status: "running"  # running, stopped, crashed
      container: "ciris-agent-datum"
      port: 8080
      health_url: "http://localhost:8080/v1/system/health"
      uptime_seconds: 3600
      version: "sha256:abc123..."  # image hash
      crash_count: 0
    - id: "agent-sage"
      name: "Sage"
      status: "stopped"
      container: "ciris-agent-sage"
      port: 8081
      health_url: "http://localhost:8081/v1/system/health"
      stopped_at: "2025-01-20T12:00:00Z"
      exit_code: 0
```

#### 2. Agent Creation
```yaml
POST /agents
Headers:
  Authorization: "Bearer <token>"  # Admin token for pre-approved templates
  # OR
  Authorization: "WA-Signature ..."  # Required for custom templates
Body:
  template: "scout"  # Template name from ciris_templates/
  name: "Scout"  # Instance name
  environment:
    # Optional environment variables
    CUSTOM_SETTING: "value"
Response:
  agent_id: "agent-scout"
  container: "ciris-agent-scout"
  port: 8081  # Dynamically allocated
  api_endpoint: "http://localhost:8081"
  compose_file: "/etc/ciris-manager/agents/scout/docker-compose.yml"
  status: "starting"
```

### How It Works

#### 1. Startup Flow
```python
# CIRISManager starts
1. Load configuration from /etc/ciris-manager/config.yml
2. Initialize port registry (track allocated ports)
3. Scan agent directories for existing agents:
   - /etc/ciris-manager/agents/*/docker-compose.yml
   - Extract port assignments from existing configs
4. Start background tasks:
   - Watchdog (monitor containers every 30s)
   - Update checker (check for new images every 5m)
   - Container manager (run docker-compose up -d every 60s)
5. Start API server on port 8888 (or configured port)
```

#### Port Allocation
```python
class PortManager:
    """Manages dynamic port allocation for agents."""
    
    def __init__(self, start_port=8080, end_port=8200):
        self.start_port = start_port
        self.end_port = end_port
        self.allocated_ports = {}  # agent_id -> port
        self.reserved_ports = {8888}  # CIRISManager itself
        
    def allocate_port(self, agent_id: str) -> int:
        """Find and allocate next available port."""
        used_ports = set(self.allocated_ports.values()) | self.reserved_ports
        
        for port in range(self.start_port, self.end_port):
            if port not in used_ports:
                self.allocated_ports[agent_id] = port
                return port
                
        raise ValueError("No available ports in range")
        
    def release_port(self, agent_id: str):
        """Release port when agent is removed."""
        if agent_id in self.allocated_ports:
            del self.allocated_ports[agent_id]
```

#### 2. Container Management Loop
```python
# Every 60 seconds:
async def container_management_loop():
    while True:
        # Pull latest images
        await run_command("docker-compose pull")
        
        # Start any stopped containers with latest image
        # This is idempotent - running containers unaffected
        await run_command("docker-compose up -d")
        
        # Check for agents that need update notification
        for agent in get_running_agents():
            current_image = get_container_image(agent.container)
            latest_image = get_latest_image(agent.service)
            
            if current_image != latest_image:
                await notify_agent_update_available(agent)
        
        await asyncio.sleep(60)
```

#### 3. Crash Loop Detection
```python
# Watchdog monitors container restarts
async def watchdog_loop():
    crash_trackers = {}  # container -> crash events
    
    while True:
        for agent in get_all_agents():
            if not is_running(agent.container):
                exit_code = get_exit_code(agent.container)
                
                if exit_code != 0:
                    # Track crash
                    if agent.container not in crash_trackers:
                        crash_trackers[agent.container] = []
                    
                    crash_trackers[agent.container].append(time.now())
                    
                    # Remove old crashes (> 5 minutes)
                    crash_trackers[agent.container] = [
                        t for t in crash_trackers[agent.container]
                        if time.now() - t < 300
                    ]
                    
                    # Check for crash loop (3 crashes in 5 minutes)
                    if len(crash_trackers[agent.container]) >= 3:
                        logger.error(f"Crash loop detected: {agent.container}")
                        await stop_container(agent.container)
                        await send_alert(f"Agent {agent.name} in crash loop")
        
        await asyncio.sleep(30)
```

#### 4. Update Notification
```python
# Notify agents of available updates via local auth
async def notify_agent_update_available(agent):
    # Use local socket or internal endpoint
    async with LocalAuthClient(agent.health_url) as client:
        await client.post("/internal/update-available", {
            "current_image": agent.current_image,
            "new_image": agent.latest_image,
            "message": "New version available. Shutdown when ready to update."
        })
```

#### 5. Agent Creation Flow

CIRISManager supports two creation paths:

##### Pre-Approved Templates (No WA Signature Required)
The following base agent templates have been pre-approved by the root seed:
- `default.yaml` (Datum)
- `sage.yaml` (Sage)
- `scout.yaml` (Scout)
- `echo-core.yaml` (Echo-Core)
- `echo-speculative.yaml` (Echo-Speculative)
- `echo.yaml` (General Echo template)

These templates have their checksums signed by the root private key, stored in a manifest file.

##### Creation Flow
```python
async def create_agent(request, wa_signature=None):
    # 1. Load template
    template_path = f"ciris_templates/{request.template}.yaml"
    template = load_template(template_path)
    template_checksum = calculate_sha256(template_path)
    
    # 2. Check if template is pre-approved
    if is_pre_approved_template(request.template, template_checksum):
        # Pre-approved templates don't need WA signature
        logger.info(f"Using pre-approved template: {request.template}")
    else:
        # Custom or modified templates require WA signature
        if not wa_signature:
            raise Unauthorized("WA signature required for non-approved template")
        if not verify_wa_signature(request, wa_signature):
            raise Unauthorized("Invalid WA signature")
        logger.info(f"Custom template approved by WA: {request.template}")
    
    # 3. Allocate port and create agent directory
    agent_id = f"agent-{request.name.lower()}"
    allocated_port = port_manager.allocate_port(agent_id)
    agent_dir = f"/etc/ciris-manager/agents/{request.name.lower()}"
    os.makedirs(agent_dir, exist_ok=True)
    
    # 4. Generate docker-compose.yml for this agent
    compose_config = {
        "version": "3.8",
        "services": {
            agent_id: {
                "container_name": f"ciris-{agent_id}",
                "image": "ghcr.io/cirisai/ciris-agent:latest",
                "ports": [f"{allocated_port}:8080"],
                "environment": {
                    "CIRIS_AGENT_NAME": request.name,
                    "CIRIS_AGENT_ID": agent_id,
                    "CIRIS_TEMPLATE": request.template,
                    "CIRIS_API_HOST": "0.0.0.0",
                    "CIRIS_API_PORT": "8080",
                    "CIRIS_USE_MOCK_LLM": "true",  # For testing
                    **merge_env(template.env, request.environment)
                },
                "volumes": [
                    f"{agent_dir}/data:/app/data",
                    f"{agent_dir}/logs:/app/logs",
                    "/home/ciris/shared/oauth:/home/ciris/shared/oauth:ro"
                ],
                "restart": "unless-stopped",
                "healthcheck": {
                    "test": ["CMD", "curl", "-f", "http://localhost:8080/v1/system/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                }
            }
        }
    }
    
    # 5. Write docker-compose.yml
    compose_path = f"{agent_dir}/docker-compose.yml"
    with open(compose_path, 'w') as f:
        yaml.dump(compose_config, f)
    
    # 6. Update nginx routing
    # CIRISManager regenerates complete nginx.conf with all agents
    nginx_manager.update_config(get_all_agents())
    
    # 7. Start the agent
    await run_command(f"docker-compose -f {compose_path} up -d")
    
    # 8. Register agent in tracking system
    register_agent(agent_id, request.name, allocated_port, compose_path)
    
    return {
        "agent_id": agent_id,
        "container": f"ciris-{agent_id}",
        "port": allocated_port,
        "api_endpoint": f"http://localhost:{allocated_port}",
        "compose_file": compose_path,
        "status": "starting"
    }
```

##### Pre-Approved Template Verification
```python
def is_pre_approved_template(template_name: str, checksum: str) -> bool:
    """Check if template is pre-approved by root seed."""
    # Load pre-approved manifest
    manifest = load_json("/etc/ciris-manager/pre-approved-templates.json")
    
    if template_name not in manifest["templates"]:
        return False
    
    expected_checksum = manifest["templates"][template_name]["checksum"]
    if checksum != expected_checksum:
        logger.warning(f"Template {template_name} has been modified!")
        return False
    
    # Verify root signature over the manifest
    root_public_key = load_root_public_key()
    manifest_data = json.dumps(manifest["templates"], sort_keys=True)
    
    return ed25519_verify(
        public_key=root_public_key,
        message=manifest_data,
        signature=manifest["root_signature"]
    )

# Pre-approved manifest format
{
    "version": "1.0",
    "created_at": "2025-01-20T12:00:00Z",
    "templates": {
        "default": {
            "checksum": "sha256:abc123...",
            "description": "Datum - baseline agent template"
        },
        "sage": {
            "checksum": "sha256:def456...",
            "description": "Sage - wise questioning agent"
        },
        "scout": {
            "checksum": "sha256:ghi789...",
            "description": "Scout - direct action demonstrator"
        },
        "echo-core": {
            "checksum": "sha256:jkl012...",
            "description": "Echo-Core - general community moderation"
        },
        "echo-speculative": {
            "checksum": "sha256:mno345...",
            "description": "Echo-Speculative - speculative discussion moderation"
        },
        "echo": {
            "checksum": "sha256:pqr678...",
            "description": "Echo - base moderation template"
        }
    },
    "root_signature": "base64:signature_over_templates_object"
}
```

### Security

#### Root Seed and Pre-Approved Templates

The root seed private key (stored in `~/.ciris/wa_keys/root_wa.key`) represents the foundational authority of the CIRIS system. It is used to pre-approve the base agent templates, allowing them to be deployed without individual WA signatures.

```bash
# Generate pre-approved template manifest
./scripts/generate-template-manifest.sh

# This script:
# 1. Calculates SHA-256 checksums of all base templates
# 2. Creates a JSON manifest with template metadata
# 3. Signs the manifest with the root private key
# 4. Outputs pre-approved-templates.json
```

The pre-approval process ensures:
- Base agents can be deployed quickly without ceremony
- Templates are cryptographically verified as unmodified
- Only templates blessed by the root seed bypass WA approval
- Any modification to a template invalidates pre-approval

#### 1. WA Signature Verification
```python
# Agent creation requires valid WA signature
def verify_wa_signature(request, signature_header):
    # Parse signature header: "WA-Signature keyid=...,signature=..."
    keyid, signature = parse_signature_header(signature_header)
    
    # Get WA public key from database or config
    wa_public_key = get_wa_public_key(keyid)
    
    # Verify signature over request body
    return ed25519_verify(
        public_key=wa_public_key,
        message=json.dumps(request, sort_keys=True),
        signature=signature
    )
```

#### 2. Local Authentication
```python
# Manager uses local-only auth for agent communication
class LocalAuthClient:
    def __init__(self, agent_url):
        # Use Unix socket or local-only token
        self.socket_path = f"/var/run/ciris/{agent_id}.sock"
        # Or use predefined local token
        self.local_token = generate_local_token()
```

### GUI Integration

The GUI can dynamically discover agents:

```typescript
// In AgentContext
async function discoverAgents() {
  const response = await fetch('http://localhost:9999/agents');
  const data = await response.json();
  
  // Transform to GUI format
  return data.agents.map(agent => ({
    id: agent.id,
    name: agent.name,
    apiUrl: `https://agents.ciris.ai/api/${agent.id}`,
    port: agent.port,
    status: agent.status,
    health: agent.status === 'running' ? 'online' : 'offline'
  }));
}

// Periodic refresh
useEffect(() => {
  const interval = setInterval(discoverAgents, 30000);
  return () => clearInterval(interval);
}, []);
```

### Configuration

```yaml
# /etc/ciris-manager/config.yml
manager:
  port: 8888
  host: 0.0.0.0
  agents_directory: /etc/ciris-manager/agents
  templates_directory: /home/ciris/CIRISAgent/ciris_templates

ports:
  start: 8080  # Start of port range
  end: 8200    # End of port range
  reserved:    # Ports to never allocate
    - 8888     # CIRISManager itself
    - 3000     # GUI
    - 80       # HTTP
    - 443      # HTTPS

docker:
  registry: ghcr.io/cirisai
  image: ciris-agent:latest
  
watchdog:
  check_interval: 30  # seconds
  crash_threshold: 3  # crashes
  crash_window: 300   # seconds (5 minutes)

updates:
  check_interval: 300  # seconds (5 minutes)
  auto_notify: true

container_management:
  interval: 60  # seconds
  pull_images: true

nginx:
  config_dir: /home/ciris/nginx  # Directory for nginx configs
  container_name: ciris-nginx     # Nginx container name
```

### Agent Directory Structure

Each agent gets its own directory:
```
/etc/ciris-manager/agents/
├── datum/
│   ├── docker-compose.yml
│   ├── data/               # Agent's data volume
│   └── logs/               # Agent's logs
├── scout/
│   ├── docker-compose.yml
│   ├── data/
│   └── logs/
└── metadata.json           # Tracks all agents and ports
```

The `metadata.json` file tracks agent registrations:
```json
{
  "agents": {
    "agent-datum": {
      "name": "Datum",
      "port": 8080,
      "template": "default",
      "created_at": "2025-01-20T12:00:00Z",
      "compose_file": "/etc/ciris-manager/agents/datum/docker-compose.yml"
    },
    "agent-scout": {
      "name": "Scout",
      "port": 8081,
      "template": "scout",
      "created_at": "2025-01-20T13:00:00Z",
      "compose_file": "/etc/ciris-manager/agents/scout/docker-compose.yml"
    }
  }
}
```

### Nginx Management

CIRISManager now handles complete nginx configuration using a template-based approach:

1. **Template Generation**: Generates complete `nginx.conf` files from discovered agents
2. **Atomic Updates**: Configuration validated before deployment with automatic rollback
3. **Dynamic Routes**: Automatically adds routes for new agents, removes for stopped agents
4. **Default Agent**: First agent (or 'datum' if exists) becomes the default `/v1/` route
5. **OAuth Support**: Per-agent OAuth callback routes automatically configured

#### Configuration Flow
```
Discover Agents → Generate nginx.conf → Validate → Atomic Replace → Reload
                                          ↓ (fail)
                                      Rollback to backup
```

#### Setup
```bash
# Initial setup
./deployment/setup-nginx-management.sh

# Test integration
./deployment/test-nginx-integration.sh
```

#### Docker Compose Configuration
```yaml
ciris-nginx:
  image: nginx:alpine
  volumes:
    - /home/ciris/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
```

### Benefits

1. **Zero-Downtime Updates**: Agents control when to shutdown, new version starts automatically
2. **Crash Protection**: Prevents infinite restart loops
3. **Dynamic Discovery**: GUI no longer needs hardcoded agent list
4. **Secure Creation**: WA signature required for new agents
5. **Simple Implementation**: Leverages Docker's natural behavior
6. **Agent Autonomy**: Agents decide when to update, manager just notifies
7. **Dynamic Routing**: Nginx routes automatically managed by CIRISManager

### Implementation Phases

1. **Phase 1**: Core watchdog and container management
2. **Phase 2**: API endpoints for discovery
3. **Phase 3**: Agent creation with WA signatures
4. **Phase 4**: GUI integration
5. **Phase 5**: Update notifications via local auth

This design provides a simple, robust solution that respects agent autonomy while solving real deployment challenges.