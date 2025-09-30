[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Stable](https://img.shields.io/badge/Status-STABLE-green.svg)](CHANGELOG.md)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=CIRISAI_CIRISAgent&metric=ncloc)](https://sonarcloud.io/summary/new_code?id=CIRISAI_CIRISAgent)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=CIRISAI_CIRISAgent&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=CIRISAI_CIRISAgent)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=CIRISAI_CIRISAgent&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=CIRISAI_CIRISAgent)

# CIRIS Engine

**Copyright © 2025 Eric Moore and CIRIS L3C** | **Apache 2.0 License**

**Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude**

**A type-safe, auditable AI agent framework with built-in ethical reasoning**

**STABLE RELEASE 1.2.0** | [Release Notes](CHANGELOG.md) | [Documentation Hub](docs/README.md)

Academic paper https://zenodo.org/records/17195221
Philosophical foundation https://ciris.ai/ciris_covenant.pdf

CIRIS lets you run AI agents that explain their decisions, defer to humans when uncertain, and maintain complete audit trails. Currently powering Discord community moderation, designed to scale to healthcare and education.

## What It Actually Does

CIRIS wraps LLM calls with:
- **Multiple evaluation passes** - Every decision gets ethical, common-sense, and domain checks
- **Human escalation** - Uncertain decisions defer to designated "Wise Authorities"
- **Complete audit trails** - Every decision is logged with reasoning
- **Type safety** - Minimal `Dict[str, Any]` usage, none in critical paths
- **Identity system** - Agents have persistent identity across restarts

**Philosophy**: "No Untyped Dicts, No Bypass Patterns, No Exceptions" - See [CLAUDE.md](CLAUDE.md#core-philosophy-type-safety-first)

**Engine Documentation**: [ciris_engine/README.md](ciris_engine/README.md) - Technical architecture and implementation details

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/CIRISAI/CIRISAgent.git
cd CIRISAgent
pip install -r requirements.txt
# For development: pip install -r requirements-dev.txt

# 2. Start with Discord adapter (easiest)
python main.py --adapter discord --guild-id YOUR_GUILD_ID

# 3. Or start API mode for development
python main.py --adapter api --port 8000
```

**First run?** → **[Complete Installation Guide](docs/INSTALLATION.md)**

## Deployment Ready

✅ **22 core services** with message bus architecture
✅ **4GB RAM target** for edge deployment
✅ **Thousands of tests** with comprehensive coverage
✅ **SonarCloud quality gates** passing
✅ **Currently powering** Discord moderation at agents.ciris.ai

## Documentation

**📚 [Complete Documentation Hub](docs/README.md)**

**Quick Links:**
- **[Quick Start Guide](docs/QUICKSTART.md)** - Get running in 5 minutes
- **[Architecture Overview](docs/ARCHITECTURE.md)** - System design (22 services)
- **[API Reference](docs/single_step_api_audit.md)** - REST API documentation
- **[Developer Guide](docs/FOR_NERDS.md)** - Contributing and extending

## Contributing

1. Read the [Architecture Guide](docs/ARCHITECTURE.md) - Understand the three-legged stool
2. Follow [Type Safety Rules](CLAUDE.md#type-safety) - Minimal `Dict[str, Any]` usage
3. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup

## Support

- **Issues**: [GitHub Issues](https://github.com/CIRISAI/CIRISAgent/issues)
- **Security**: [SECURITY.md](SECURITY.md)
- **Quality**: [![SonarCloud](https://sonarcloud.io/images/project_badges/sonarcloud-light.svg)](https://sonarcloud.io/summary/new_code?id=CIRISAI_CIRISAgent)

---

**CIRIS: Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude**
*Ethical AI with human oversight, complete transparency, and deployment reliability.*

**Ready to build trustworthy AI?** → **[Get started →](docs/README.md)**
