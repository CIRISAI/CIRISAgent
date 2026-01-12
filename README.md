[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Stable](https://img.shields.io/badge/Status-STABLE-green.svg)](CHANGELOG.md)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=CIRISAI_CIRISAgent&metric=ncloc)](https://sonarcloud.io/summary/new_code?id=CIRISAI_CIRISAgent)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=CIRISAI_CIRISAgent&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=CIRISAI_CIRISAgent)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=CIRISAI_CIRISAgent&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=CIRISAI_CIRISAgent)

[![DeepWiki](https://img.shields.io/badge/DeepWiki-CIRIS_Codebase-blue?logo=readthedocs)](https://deepwiki.com/CIRISAI/CIRISAgent)
[![CIRIS Architecture](https://img.shields.io/badge/Paper-CIRIS_Architecture-orange?logo=arxiv)](https://doi.org/10.5281/zenodo.18137161)
[![Coherence Ratchet](https://img.shields.io/badge/Paper-Coherence_Ratchet_(CCA)-orange?logo=arxiv)](https://doi.org/10.5281/zenodo.18142668)
[![Covenant](https://img.shields.io/badge/Covenant-v1.2--Beta-purple)](https://ciris.ai/ciris_covenant.pdf)

# CIRIS Engine

**Copyright © 2025 Eric Moore and CIRIS L3C** | **Apache 2.0 License**

**Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude**

**A type-safe, auditable AI agent framework with built-in ethical reasoning**

**BETA RELEASE 1.8.0-stable** | [Release Notes](CHANGELOG.md) | [Documentation Hub](docs/README.md)

CIRIS lets you run AI agents that explain their decisions, defer to humans when uncertain, and maintain complete audit trails. Currently powering Discord community moderation, designed to scale to healthcare and education.

## What It Actually Does

CIRIS wraps LLM calls with:
- **Multiple evaluation passes** - Every decision gets ethical, common-sense, domain, and epistemic diversity checks
- **Intuition DMA (IDMA)** - Coherence Collapse Analysis for detecting fragile reasoning (k_eff < 2 = single-source dependence)
- **Human escalation** - Uncertain decisions defer to designated "Wise Authorities"
- **Complete audit trails** - Every decision is logged with reasoning
- **Type safety** - Minimal `Dict[str, Any]` usage, none in critical paths
- **Identity system** - Agents have persistent identity across restarts
- **Privacy compliance** - Built-in DSAR/GDPR tools for data discovery, export, and deletion
- **Commons Credits** - Track non-monetary contributions that strengthen community (not currency, not scorekeeping)

**Philosophy**: "No Untyped Dicts, No Bypass Patterns, No Exceptions" - See [CLAUDE.md](CLAUDE.md#core-philosophy-type-safety-first)

**Engine Documentation**: [ciris_engine/README.md](ciris_engine/README.md) - Technical architecture and implementation details

## Quick Start

### One-Line Install (Agent + Web UI)

Get CIRIS running in minutes without Docker:

```bash
curl -sSL https://ciris.ai/install.sh | bash
```

This installs both CIRISAgent and CIRISGUI with all dependencies, then opens the web interface at `http://localhost:3000`.

**→ [Standalone Installation Guide](docs/STANDALONE_INSTALL.md)** - Full options, troubleshooting, and manual setup

### Agent-Only Install (Python)

**Via pip (Recommended):**
```bash
# Install from PyPI
pip install ciris-agent

# Start with API adapter and built-in web UI
ciris-agent --adapter api --port 8000

# Or use Discord adapter
ciris-agent --adapter discord --guild-id YOUR_GUILD_ID

# Load multiple adapters together
ciris-agent --adapter api --adapter reddit
```

**From Source (Development):**
```bash
# 1. Clone and install
git clone https://github.com/CIRISAI/CIRISAgent.git
cd CIRISAgent
pip install -r requirements.txt
# For development: pip install -r requirements-dev.txt

# 2. Start with Discord adapter
python main.py --adapter discord --guild-id YOUR_GUILD_ID

# 3. Or start API mode
python main.py --adapter api --port 8000

# 4. Load multiple adapters together
python main.py --adapter api --adapter reddit
```

**→ [Complete Installation Guide](docs/INSTALLATION.md)** - Detailed setup, configuration, and deployment

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
| SQL External Data | Tools | DSAR/GDPR compliance tools for SQL databases. Supports data discovery, export, anonymization, and deletion across multiple database types (SQLite, PostgreSQL, MySQL, MSSQL). | Database connection config (see docs) | Loaded automatically via tool system |
| Mock LLM | LLM Provider | Testing mock LLM service that simulates AI responses without external API calls. Not for production use. | None (optional delay/failure rate) | `--adapter mockllm` or `--mock-llm` |
| Geo Wisdom | Wise Authority | Geographic navigation guidance using OpenStreetMap for routing and geocoding. | None (uses public OSM API) | Loaded automatically for navigation domains |
| Weather Wisdom | Wise Authority | Weather forecasting and alerts using NOAA National Weather Service API. | None (uses public NOAA API) | Loaded automatically for weather domains |
| Sensor Wisdom | Wise Authority | Home automation and IoT sensor integration via Home Assistant. Actively filters out medical sensors. | `CIRIS_HOMEASSISTANT_URL`<br>`CIRIS_HOMEASSISTANT_TOKEN` | Loaded automatically for sensor domains |

### LLM Providers

CIRIS uses an OpenAI-compatible API interface for LLM inference:

| Provider | Endpoint | Authentication | Platform |
|----------|----------|----------------|----------|
| ciris.ai | `https://ciris.ai/v1` | Google Sign-In | Android only |
| OpenAI | `https://api.openai.com/v1` | API Key | All |
| Groq | `https://api.groq.com/openai/v1` | API Key | All |
| Together.ai | `https://api.together.ai/v1` | API Key | All |
| Local LLMs | `http://localhost:8080/v1` | Optional | All |

**ciris.ai Proxy** (Android only): Available exclusively on Android due to Google Play Services dependencies. Uses Google Sign-In for authentication with automatic token refresh. No logging - prompts and responses pass through without being stored. Backend providers are Groq and Together.ai.

### Agent Templates

CIRIS includes pre-configured agent templates in `ciris_engine/ciris_templates/`:

| Template | Description |
|----------|-------------|
| **Ally** | Personal assistant focused on ethical partnership. Supports task management, scheduling, decision support, and wellbeing. Includes California SB 243 compliance, crisis response protocols, and GDPR DSAR automation. |
| **Datum** | Community moderation agent for Discord. Production-deployed at agents.ciris.ai. |

Templates define identity, permitted actions, guardrails, and standard operating procedures (SOPs) for DSAR compliance.

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
