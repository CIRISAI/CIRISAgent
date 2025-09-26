# CIRIS Agent Beta Release Notes

## Version: 1.0.3-beta
## Release Date: August 4, 2025

### 🐛 Bug Fixes
- **Critical**: Fixed TSDB consolidation infinite loop causing agent unresponsiveness and production outages
- **Security**: Fixed timing attack vulnerability in password verification using constant-time comparison
- **Multi-agent**: Fixed OAuth authentication to properly configure SDK for agent-specific endpoints
- **GUI**: Fixed immediate logout issue when using username/password authentication
- **GUI**: Fixed SDK base URL configuration for managed vs standalone deployment modes
- **Discord**: Improved connection stability and error handling

### 🔧 Improvements
- OAuth multi-agent support now properly configures SDK per agent instead of all agents
- Enhanced URL routing detection based on domain (agents.ciris.ai) or path (/agent/)
- Better error handling with fail-fast behavior instead of showing null/unknown data
- Complete type safety achieved - zero Dict[str, Any] remaining in codebase
- Improved test infrastructure with auto-rebuild capability

### 📊 Updated Metrics
- Test suite: 1,161 tests passing (100% pass rate)
- All SonarQube A-grades maintained with zero security issues
- Production stability proven with 1+ month Discord deployment
- Successfully running 5 agents in production environment

### 🚀 Production Status
- Discord adapter has been live for over a month with excellent stability
- Multi-agent deployment successful at agents.ciris.ai
- Ready to add 4 additional agents to the Discord pilot

---

## Version: 1.0.0-beta.1
## Release Date: July 15, 2025

## 🎉 Introduction

We are thrilled to announce the **beta release** of CIRIS Agent - a sophisticated, type-safe AI agent platform designed for progressive deployment from community moderation to mission-critical applications.

## 🌟 Key Highlights

### Complete Type Safety
- **Zero `Dict[str, Any]`** in production code
- All data structures use Pydantic models
- "No Untyped Dicts, No Bypass Patterns, No Exceptions" philosophy fully realized

### Robust Architecture
- **22 Core Services** + dynamic adapter services
- **78 API endpoints** across 12 modules
- **1,161 tests passing** with CI/CD verification
- **Sonar A-grades** across all metrics with zero security issues

### Production Ready
- Optimized for 4GB RAM environments
- Mock LLM for offline operation
- Docker deployment ready
- Complete authentication and authorization

## 📊 Technical Specifications

### Service Architecture
```
Core Services: 21
├── Graph Services (6)
├── Infrastructure Services (7)
├── Governance Services (4)
├── Runtime Services (3)
└── Tool Services (1)

Dynamic Services (per adapter):
├── CLI: +1 service
├── API: +3 services
└── Discord: +3 services
```

### Code Quality Metrics
- **Security**: A (0 issues) ✅
- **Reliability**: A (101 minor issues) ✅
- **Maintainability**: A (742 minor issues) ✅
- **Test Coverage**: 46.9%
- **Code Duplication**: 1.7%
- **Security Hotspots**: 0 ✅

## 🚀 Major Features

### 1. Multi-Adapter Support
- **Discord Bot**: Full community moderation capabilities
- **REST API**: 78 endpoints with TypeScript SDK
- **CLI**: Interactive command-line interface
- **WebSocket**: Real-time bidirectional communication

### 2. Advanced Cognitive System
- 6 cognitive states (WAKEUP, WORK, PLAY, DREAM, SOLITUDE, SHUTDOWN)
- Thought depth management with guardrails
- Conscience-based decision making
- Wise Authority deferral system

### 3. Enterprise Features
- Role-based access control (OBSERVER/ADMIN/AUTHORITY/SYSTEM_ADMIN)
- Complete audit trail with verification
- Emergency shutdown with Ed25519 signatures
- Resource monitoring and telemetry

### 4. Developer Experience
- Complete TypeScript SDK
- Comprehensive API documentation
- Mock LLM for deterministic testing
- Docker and docker-compose support
- GUI for system monitoring

## 🔧 Installation

### Docker (Recommended)
```bash
# API mode with mock LLM
docker-compose -f docker-compose-api-mock.yml up -d

# Access at http://localhost:8080
# Default credentials: admin/ciris_admin_password
```

### Local Development
```bash
# Clone the repository
git clone https://github.com/CIRISAI/CIRISAgent.git
cd CIRISAgent

# Install dependencies
pip install -r requirements.txt

# Run with mock LLM
python main.py --mock-llm --adapter api
```

## 📖 Documentation

- **API Reference**: See `/docs/API_REFERENCE.md`
- **Quick Start**: See `/docs/QUICKSTART.md`
- **Architecture**: See `/docs/ARCHITECTURE.md`
- **GUI**: Access at `http://localhost:3000` after starting the agent

## 🧪 Beta Testing Focus

We're particularly interested in feedback on:

1. **Performance** under resource constraints (4GB RAM target)
2. **API stability** and SDK usability
3. **Mock LLM** behavior vs real LLM integration
4. **Multi-adapter** coordination and switching
5. **Wise Authority** deferral system effectiveness

## ⚠️ Known Limitations

This is a beta release. While feature-complete, please note:

- Some telemetry metrics show placeholder values
- Real LLM integration requires API keys
- Discord adapter requires bot token configuration
- WebSocket connections may need firewall configuration

## 🤝 Contributing

We welcome contributions! Please see `CONTRIBUTING.md` for guidelines.

### Reporting Issues
- Use GitHub Issues for bug reports
- Include logs from `/app/logs/incidents_latest.log`
- Specify adapter type and configuration

## 🔐 Security

- All A-grade Sonar security assessment
- Zero security hotspots identified
- Ed25519 emergency shutdown capability
- Comprehensive audit trail

For security concerns, please email security@ciris.ai

## 📈 What's Next

### Planned for v1.0.0 (Stable)
- Complete telemetry metric implementation
- Performance optimization for 2GB RAM
- Additional LLM provider support
- Enhanced WebSocket features
- Expanded tool ecosystem

### Future Roadmap
- Kubernetes deployment manifests
- Prometheus/Grafana integration
- Multi-language SDK support
- Voice interface support
- Plugin architecture

## 🙏 Acknowledgments

Special thanks to:
- The Anthropic team for Claude
- All beta testers and early adopters
- Open source contributors
- The CIRIS community

## 📝 License

CIRIS Agent is released under the MIT License. See `LICENSE` file for details.

---

**Ready to Deploy Your Agent?**

Join our Discord community: [discord.gg/ciris](https://discord.gg/ciris)
Read the docs: [docs.ciris.ai](https://docs.ciris.ai)
Star us on GitHub: [github.com/CIRISAI/CIRISAgent](https://github.com/CIRISAI/CIRISAgent)

*Building the future of AI agents, one typed schema at a time.* 🤖✨
