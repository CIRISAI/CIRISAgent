## Summary

Major RC1 update introducing multi-agent infrastructure, enhanced security, and comprehensive test coverage.

## Key Changes

### 🏗️ Multi-Agent Support
- Stateless routing with Intent-Driven Architecture
- Docker-based agent lifecycle management  
- Dynamic nginx configuration
- Port allocation system (8080-8199)

### 🎨 GUI Overhaul
- Complete redesign for multi-agent management
- OAuth-protected manager interface
- Real-time agent monitoring
- Template-based agent creation

### 🔐 Security & Stability
- Cryptographically secure agent IDs
- Fixed insecure temp file usage
- Google OAuth with @ciris.ai restriction
- Fixed infinite thought loops
- Resolved CI permission errors

### 📊 Test Coverage
- Achieved >80% coverage (SonarQube compliant)
- 218 passing tests
- Key modules at 95-100% coverage

## Breaking Changes

- OAuth required for manager API
- Agent IDs use secure 6-char suffixes
- Environment variable `CIRIS_ADAPTER=api` required

## Quick Start

```bash
# Start manager
CIRIS_MANAGER_CONFIG=~/.config/ciris-manager/config.yml python deployment/run-ciris-manager-api.py

# Create agent
curl -X POST http://localhost:8888/manager/v1/agents \
  -H "Content-Type: application/json" \
  -d '{"template": "scout", "name": "My Agent"}'
```

## Testing

```bash
python -m pytest tests/ciris_manager/  # All pass
```

Fixes #183, #180
Implements #185