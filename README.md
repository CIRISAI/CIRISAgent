[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Stable](https://img.shields.io/badge/Status-STABLE-green.svg)](CHANGELOG.md)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=CIRISAI_CIRISAgent&metric=ncloc)](https://sonarcloud.io/summary/new_code?id=CIRISAI_CIRISAgent)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=CIRISAI_CIRISAgent&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=CIRISAI_CIRISAgent)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=CIRISAI_CIRISAgent&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=CIRISAI_CIRISAgent)

# CIRIS Engine

**Copyright © 2025 Eric Moore and CIRIS L3C** | **Apache 2.0 License**

**Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude**

**A type-safe, auditable AI agent framework with built-in ethical reasoning**

**STABLE RELEASE 1.5.7** | [Release Notes](CHANGELOG.md) | [Documentation Hub](docs/README.md)

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

# 4. Load multiple adapters together
python main.py --adapter api --adapter reddit
```

**First run?** → **[Complete Installation Guide](docs/INSTALLATION.md)**

## Available Adapters

CIRIS supports both built-in and modular adapters that can be loaded via `--adapter` flag or `CIRIS_ADAPTER` environment variable.

### Built-in Adapters

| Adapter | Type | Description | Usage |
|---------|------|-------------|-------|
| CLI | Communication | Interactive command-line interface | `--adapter cli` |
| API | Communication | RESTful HTTP API server (FastAPI) | `--adapter api --port 8000` |
| Discord | Communication | Discord bot integration | `--adapter discord --guild-id ID` |

### Modular Service Adapters

| Adapter | Type | Description | Required Configuration | Usage |
|---------|------|-------------|------------------------|-------|
| Reddit | Communication + Tools | Reddit integration for r/ciris monitoring and interaction. Supports posting, commenting, content removal, user lookups, and passive observation. | `CIRIS_REDDIT_CLIENT_ID`<br>`CIRIS_REDDIT_CLIENT_SECRET`<br>`CIRIS_REDDIT_USERNAME`<br>`CIRIS_REDDIT_PASSWORD` | `--adapter reddit` |
| Mock LLM | LLM Provider | Testing mock LLM service that simulates AI responses without external API calls. Not for production use. | None (optional delay/failure rate) | `--adapter mockllm` or `--mock-llm` |
| Geo Wisdom | Wise Authority | Geographic navigation guidance using OpenStreetMap for routing and geocoding. | None (uses public OSM API) | Loaded automatically for navigation domains |
| Weather Wisdom | Wise Authority | Weather forecasting and alerts using NOAA National Weather Service API. | None (uses public NOAA API) | Loaded automatically for weather domains |
| Sensor Wisdom | Wise Authority | Home automation and IoT sensor integration via Home Assistant. Actively filters out medical sensors. | `CIRIS_HOMEASSISTANT_URL`<br>`CIRIS_HOMEASSISTANT_TOKEN` | Loaded automatically for sensor domains |

### Loading Adapters

**Via Command Line:**
```bash
# Single adapter
python main.py --adapter api

# Multiple adapters
python main.py --adapter api --adapter reddit

# With configuration
export CIRIS_REDDIT_CLIENT_ID="your_client_id"
export CIRIS_REDDIT_CLIENT_SECRET="your_secret"
python main.py --adapter reddit
```

**Via Environment Variable:**
```bash
export CIRIS_ADAPTER="api,reddit"
python main.py
```

**Priority and Behavior:**
- Communication adapters can run simultaneously (e.g., API + Reddit + Discord)
- Reddit adapter defaults to lower priority than API for message handling
- Wise Authority adapters load automatically when their domain is needed
- Mock LLM disables real LLM services when loaded (testing only)

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
- **[API Reference](docs/API_SPEC.md)** - REST API documentation
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
