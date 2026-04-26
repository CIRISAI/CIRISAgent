# FSD: CIRIS Development Experience (DevX) System

## 1. Overview

The CIRIS DevX System provides a unified, production-mirroring development environment that eliminates configuration drift and reduces setup complexity from hours to minutes.

## 2. Core Philosophy

**"Production Parity with Developer Ergonomics"** - The development environment should mirror production architecture while providing sensible developer defaults and instant feedback loops.

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CIRIS CLI (ciris)                       │
│  ┌─────────────┬──────────────┬─────────────┬────────────┐ │
│  │ Environment │ Health Check │   Agent     │   Config   │ │
│  │  Manager    │   Monitor    │  Lifecycle  │ Validator  │ │
│  └─────────────┴──────────────┴─────────────┴────────────┘ │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
            ┌─────────────────────────────────────┐
            │     Configuration Resolver          │
            │  ┌──────────┬──────────┬─────────┐ │
            │  │   Dev    │  Staging │  Prod   │ │
            │  │ Defaults │ Defaults │ Config  │ │
            │  └──────────┴──────────┴─────────┘ │
            └─────────────────┬───────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            ┌───────────────┐   ┌───────────────┐
            │ Docker Stack  │   │ Health Check  │
            │   Orchestor   │   │    Engine     │
            └───────────────┘   └───────────────┘
```

## 4. Key Components

### 4.1 CIRIS CLI
**Purpose**: Single entry point for all development operations

**Commands**:
```bash
ciris init                    # Initialize new CIRIS project
ciris dev start              # Start full dev environment
ciris dev stop               # Stop all services
ciris status                 # Show health of all components
ciris logs <component>       # Stream component logs
ciris agent create           # Interactive agent creation
ciris config validate        # Validate configuration
ciris doctor                 # Diagnose common issues
```

### 4.2 Environment Configuration System

**File**: `ciris-config.yml`
```yaml
version: "1.0"
environments:
  dev:
    defaults:
      llm_provider: mock
      api_host: 0.0.0.0
      auth_required: false
      oauth_mode: mock
      nginx_auto_update: true
    services:
      nginx:
        port: 80
      manager:
        port: 8888
      gui:
        port: 3000
        hot_reload: true

  prod:
    defaults:
      llm_provider: "${LLM_PROVIDER}"
      api_host: 0.0.0.0
      auth_required: true
      oauth_mode: google
      oauth_domain: ciris.ai
```

### 4.3 Health Check System

**Real-time monitoring** of all components with actionable error messages:

```json
{
  "timestamp": "2025-07-26T15:55:00Z",
  "status": "degraded",
  "components": {
    "nginx": {
      "status": "healthy",
      "endpoint": "http://localhost:80",
      "version": "1.29.0"
    },
    "manager": {
      "status": "healthy",
      "endpoint": "http://localhost:8888",
      "agents_managed": 3
    },
    "gui": {
      "status": "healthy",
      "endpoint": "http://localhost:3000"
    },
    "agents": {
      "asdf-7gmaex": {
        "status": "unhealthy",
        "error": "API host misconfigured",
        "fix": "Set CIRIS_API_HOST=0.0.0.0 in agent config",
        "endpoint": "http://localhost/api/asdf-7gmaex"
      }
    }
  }
}
```

### 4.4 Automatic Configuration Management

**Smart Defaults Engine**:
- Detects environment (dev/staging/prod)
- Applies appropriate defaults
- Validates configuration consistency
- Prevents common misconfigurations

**Key Rules**:
1. Dev always uses mock LLM unless explicitly overridden
2. Docker containers always use `0.0.0.0` for API host
3. nginx config auto-updates when agents change
4. OAuth uses mock provider in dev

### 4.5 Error Recovery System

**Intelligent error messages with fixes**:
```
ERROR: Agent 'scout-abc123' not accessible

CAUSE: Agent listening on 127.0.0.1 inside Docker container
FIX: Update CIRIS_API_HOST=0.0.0.0 in agent environment

Run: ciris doctor --fix-agent scout-abc123
```

## 5. Implementation Plan

### Phase 1: CLI Foundation (Week 1)
- [ ] Create `ciris` CLI with basic commands
- [ ] Implement config file parser
- [ ] Add environment detection

### Phase 2: Health Check System (Week 2)
- [ ] Build health check engine
- [ ] Create status dashboard
- [ ] Add error diagnosis

### Phase 3: Automated Configuration (Week 3)
- [ ] Smart defaults system
- [ ] Config validation
- [ ] Auto-fix capabilities

### Phase 4: Integration (Week 4)
- [ ] nginx auto-update on agent changes
- [ ] Unified logging system
- [ ] Production parity verification

## 6. Success Metrics

1. **Time to First Agent**: < 5 minutes from clone to running agent
2. **Configuration Errors**: 90% reduction in config-related issues
3. **Dev/Prod Parity**: Same commands work in both environments
4. **Error Resolution Time**: < 30 seconds with auto-fix

## 7. Common Issues Addressed

Based on real developer experience, this system solves:

1. **LLM Ponder Loops**: Automatic mock LLM in dev
2. **Docker Networking**: Correct API host configuration
3. **OAuth Complexity**: Mock provider for local dev
4. **nginx Routing**: Auto-update on agent changes
5. **Configuration Drift**: Single source of truth

## 8. Future Enhancements

1. **Cloud Development Environments**: Spin up full env in cloud
2. **Team Synchronization**: Share dev environments
3. **Performance Profiling**: Built-in bottleneck detection
4. **Security Scanning**: Automatic vulnerability checks

This FSD addresses the core pain point: the gap between development and production environments that causes configuration drift and makes deployment scary. By providing production-mirroring defaults with developer ergonomics, we make the entire system more reliable and enjoyable to work with.
