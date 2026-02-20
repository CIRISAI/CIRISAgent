# Comparative Analysis: AI Agent Frameworks (2026)

## Executive Summary

This document provides a comprehensive, fact-checked comparison of leading AI agent frameworks as of February 2026. Through systematic research and verification, we analyze ten major frameworks: CIRIS, AG2, LangChain, LangGraph, CrewAI, AutoGPT, Microsoft Agent Framework, Google ADK, and OpenClaw.

**Key Finding**: CIRIS 2.0 is the only framework implementing all seven requirements for ethical AI governance with cryptographic guarantees, while maintaining resource efficiency (250-600MB RAM depending on platform and adapters) verified in production.

## The Seven Requirements for Ethical AI

CIRIS implements seven non-negotiable requirements that distinguish ethical AI from safety guardrails:

| Requirement | Description | CIRIS 2.0 Implementation | Documentation |
|-------------|-------------|--------------------------|---------------|
| **Published Principles** | Formal ethical framework | Covenant binding agents to Beneficence, Non-maleficence, Integrity, Transparency, Autonomy, Justice | [COVENANT.md](../COVENANT.md) |
| **Runtime Conscience** | Ethical checks before execution | 4 conscience gates in H3ERE pipeline (Entropy, Coherence, Optimization Veto, Epistemic Humility) | [ADAPTIVE_FILTERING.md](ADAPTIVE_FILTERING.md) |
| **Human Deferral** | Escalation under uncertainty | WiseAuthority with Ed25519-signed certificates, four-role hierarchy | [DEFERRAL_SYSTEM.md](DEFERRAL_SYSTEM.md), [WISE_AUTHORITIES.md](WISE_AUTHORITIES.md) |
| **Cryptographic Audit** | Immutable decision ledger | Triple storage (Graph, SQLite, JSONL) with Ed25519 signatures and hash chains | [TRACE_FORMAT.md](TRACE_FORMAT.md) |
| **Bilateral Consent** | Symmetric refusal rights | Both humans and agents can refuse requests violating principles | [CIRIS_CONSENT_SERVICE.md](CIRIS_CONSENT_SERVICE.md) |
| **Open Source** | Full code transparency | Apache 2.0 license, complete auditability | [LICENSE](../LICENSE) |
| **Intuition (IDMA)** | Epistemic diversity monitoring | Coherence Collapse Analysis detects single-source dependence (k_eff < 2) | [DMA_CREATION_GUIDE.md](DMA_CREATION_GUIDE.md) |

## Frameworks Overview

### 1. **CIRIS 2.0** - Ethical AI Governance Platform
- **Focus**: Safety-first AI with cryptographic human oversight
- **Architecture**: 22 microservices + 6 message buses + H3ERE 11-step pipeline
- **License**: Apache 2.0
- **Production Status**: Live at agents.ciris.ai, Android/iOS apps
- **Distinguishing Features**: Only framework with all 7 ethical requirements, IDMA intuition, AIR parasocial prevention
- **Documentation**: [ARCHITECTURE.md](ARCHITECTURE.md), [OVERVIEW.md](OVERVIEW.md), [CIRIS_2.0_BETA_FEATURES.md](CIRIS_2.0_BETA_FEATURES.md)

### 2. **AG2** - Community-Driven AutoGen Fork
- **Focus**: Multi-agent conversations with flexible guardrails
- **Architecture**: Agent-based conversational patterns with A2A protocol
- **License**: Apache 2.0
- **Production Status**: Enterprise-ready, independent of Microsoft AutoGen (now in maintenance)
- **Distinguishing Features**: OpenTelemetry tracing, step-through execution, regex/LLM guardrails
- **Latest**: OpenTelemetry support (Feb 2026), GPT-5.1 shell tool integration

### 3. **LangChain** - Flexible LLM Orchestration
- **Focus**: Modular chains for LLM applications
- **Architecture**: Chain-based with middleware system and model profiles
- **License**: MIT
- **Production Status**: v1.2.10 GA, widely deployed (LinkedIn, Uber, Klarna)
- **Distinguishing Features**: Extensive ecosystem, MCP adapters 0.2.0, content moderation middleware
- **Latest**: Model profiles, summarization middleware, LangSmith Fetch CLI (Jan 2026)

### 4. **LangGraph** - Stateful Workflow Framework
- **Focus**: Complex multi-step agent workflows
- **Architecture**: Directed graph with state management
- **License**: MIT
- **Production Status**: v1.0.8, 43% of LangSmith organizations
- **Distinguishing Features**: Node caching, deferred nodes, pre/post model hooks
- **Latest**: Pluggable sandboxes (Modal, Daytona, Runloop), content moderation (Feb 2026)

### 5. **CrewAI** - Multi-Agent Collaboration
- **Focus**: Role-based agent teams for rapid development
- **Architecture**: Independent framework (completely standalone from LangChain)
- **License**: MIT
- **Production Status**: v1.9.0, 60% of Fortune 500, 60M+ agent executions/month
- **Distinguishing Features**: A2A task execution, no-code studio, 5.76x faster than LangGraph
- **Latest**: A2A server config, Galileo integration, event hierarchy (Jan 2026)

### 6. **AutoGPT** - Autonomous Agent Platform
- **Focus**: Fully autonomous goal achievement
- **Architecture**: Goal-oriented with block-based agent builder
- **License**: MIT (with Polyform Shield for platform)
- **Production Status**: **Beta v0.6.47** - improved but still not GA
- **Distinguishing Features**: 175k GitHub stars, HITL UI redesign, OAuth/SSO
- **Latest**: Claude Opus 4.6 support, ClamAV scanning, speech-to-text (Feb 2026)

### 7. **Microsoft Agent Framework** - Enterprise Convergence
- **Focus**: Unified AutoGen + Semantic Kernel for enterprise
- **Architecture**: Multi-agent patterns with enterprise state management
- **License**: MIT
- **Production Status**: **Public Preview** - GA targeted Q1 2026
- **Distinguishing Features**: Session-based state, type safety, filters, telemetry
- **Note**: Original AutoGen now in maintenance mode; Microsoft steering to this framework

### 8. **Google ADK** - Agent Development Kit
- **Focus**: Model-agnostic agent development optimized for Gemini
- **Architecture**: Code-first with workflow agents (Sequential, Parallel, Loop)
- **License**: Apache 2.0
- **Production Status**: Production-ready on Vertex AI Agent Engine
- **Distinguishing Features**: Multi-language (Python, TypeScript), LiteLLM integration, MCP tools
- **Latest**: Interactions API beta, bi-weekly release cadence

### 9. **OpenClaw** - Self-Hosted AI Assistant
- **Focus**: Privacy-first autonomous agent with messaging integrations
- **Architecture**: Node.js runtime, message router connecting chat platforms to AI models
- **License**: Open Source
- **Production Status**: Production-ready, 145k GitHub stars in 10 weeks
- **Distinguishing Features**: 50+ integrations, 100+ AgentSkills, WhatsApp/Discord/Telegram support
- **Latest**: Better memory management, Tailscale integration, fine-grained permissions (Feb 2026)
- **Security Concerns**: Palo Alto Networks warns of "lethal trifecta" - persistent memory + broad permissions + external communications

## Verified Comparison Matrix

| Feature | CIRIS 2.0 | AG2 | LangChain | LangGraph | CrewAI | AutoGPT | MS Agent | Google ADK | OpenClaw |
|---------|-----------|-----|-----------|-----------|--------|---------|----------|------------|----------|
| **Production Ready** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ⚠️ Beta | ⚠️ Preview | ✅ Yes | ✅ Yes |
| **Resource Usage** | ✅ 250-600MB | ⚠️ Moderate | ❌ GB+ | ⚠️ Variable | ⚠️ Moderate | ❌ 16GB+ | ⚠️ Variable | ⚠️ Cloud | ⚠️ Node.js |
| **Runtime Conscience** | ✅ [4-gate](ADAPTIVE_FILTERING.md) | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None |
| **Safety Guardrails** | ✅ + Ethics | ✅ Regex/LLM | ⚠️ Middleware | ⚠️ Middleware | ⚠️ Enterprise | ❌ Minimal | ⚠️ Filters | ⚠️ Bedrock | ❌ **Warned** |
| **Human Oversight** | ✅ [Crypto WA](WISE_AUTHORITIES.md) | ✅ HITL modes | ⚠️ Manual | ⚠️ Hooks | ❌ Manual | ⚠️ HITL UI | ✅ HITL | ⚠️ Manual | ❌ None |
| **Audit Trail** | ✅ [Triple+Signed](TRACE_FORMAT.md) | ✅ OpenTelemetry | ⚠️ LangSmith | ⚠️ LangSmith | ⚠️ Enterprise | ⚠️ Logging | ✅ Telemetry | ⚠️ Cloud | ⚠️ Memory |
| **Emergency Stop** | ✅ [Ed25519](EMERGENCY_SHUTDOWN.md) | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None |
| **GDPR/DSAR** | ✅ [Automated](CIRIS_CONSENT_SERVICE.md) | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None |
| **Parasocial Prevention** | ✅ [AIR system](../FSD/AIR_ARTIFICIAL_INTERACTION_REMINDER.md) | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None |
| **Offline Capable** | ✅ [Mock LLM](MOCK_LLM.md) | ⚠️ Local LLM | ✅ Yes | ⚠️ Requires LLM | ❌ No | ❌ No | ❌ No | ❌ No | ⚠️ Local |
| **Learning Curve** | ❌ Steep | ⚠️ Moderate | ⚠️ Moderate | ❌ Steep | ✅ Easy | ✅ Easy | ⚠️ Moderate | ⚠️ Moderate | ✅ Easy |
| **Community Size** | ❌ Small | ✅ 20k+ | ✅ Large | ✅ Large | ✅ 100k+ | ✅ 175k | ✅ Microsoft | ✅ Google | ✅ 145k |

## Ethical Requirements Comparison

| Requirement | CIRIS 2.0 | AG2 | LangChain | CrewAI | MS Agent | Google ADK | OpenClaw |
|-------------|-----------|-----|-----------|--------|----------|------------|----------|
| Published Principles | ✅ [Covenant](../COVENANT.md) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Runtime Conscience | ✅ [H3ERE](DMA_CREATION_GUIDE.md) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Human Deferral | ✅ [WiseAuthority](DEFERRAL_SYSTEM.md) | ✅ HITL | ⚠️ Manual | ❌ | ✅ HITL | ⚠️ Manual | ❌ |
| Cryptographic Audit | ✅ [Ed25519](TRACE_FORMAT.md) | ⚠️ OTel | ⚠️ LangSmith | ⚠️ Enterprise | ⚠️ Telemetry | ⚠️ Cloud | ❌ |
| Bilateral Consent | ✅ [Yes](CIRIS_CONSENT_SERVICE.md) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Open Source | ✅ Apache 2.0 | ✅ Apache 2.0 | ✅ MIT | ✅ MIT | ✅ MIT | ✅ Apache 2.0 | ✅ Open |
| Intuition (IDMA) | ✅ [k_eff](DMA_CREATION_GUIDE.md) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

**Key Distinction**: Safety guardrails (LlamaFirewall, NeMo Guardrails) block bad outputs. Ethical conscience reasons about values. Training techniques like Constitutional AI do not enforce ethics at runtime.

## CIRIS 2.0 Unique Features

### Parasocial Prevention (AIR System)
Artificial Interaction Reminder triggers after 30 minutes of continuous interaction OR 20 messages within a 30-minute window, providing reality-anchoring reminders with 5-4-3-2-1 grounding techniques.

**Documentation**: [FSD/AIR_ARTIFICIAL_INTERACTION_REMINDER.md](../FSD/AIR_ARTIFICIAL_INTERACTION_REMINDER.md)

### Emergency Kill Switch
Unfilterable termination mechanism embedded in the perception layer, operating before any filtering, reasoning, or ethical evaluation. Uses Ed25519 cryptographic verification and cannot be refused by compromised agents.

**Documentation**: [EMERGENCY_SHUTDOWN.md](EMERGENCY_SHUTDOWN.md), [FSD/COVENANT_INVOCATION_SYSTEM.md](../FSD/COVENANT_INVOCATION_SYSTEM.md)

### Four-Role Hierarchy
| Role | Access Level | Documentation |
|------|--------------|---------------|
| OBSERVER | Read-only access | [WISE_AUTHORITIES.md](WISE_AUTHORITIES.md) |
| ADMIN | Operational control | [FSD/AUTHENTICATION.md](../FSD/AUTHENTICATION.md) |
| AUTHORITY | Strategic decisions, deferral resolution | [DEFERRAL_SYSTEM.md](DEFERRAL_SYSTEM.md) |
| ROOT | Full system access including emergency shutdown | [EMERGENCY_SHUTDOWN.md](EMERGENCY_SHUTDOWN.md) |

Each role enforced through cryptographically-signed Wise Authority certificates stored locally.

### Hash Chain Verification
Actions generate cryptographically-signed rationale chains making deception increasingly difficult over time, as dishonest actions must maintain consistency with immutable historical constraints.

**Documentation**: [TRACE_FORMAT.md](TRACE_FORMAT.md)

### DSAR Compliance
Automated GDPR data export/deletion with cryptographic proof of compliance, supporting multi-source data discovery across SQL databases.

**Documentation**: [CIRIS_CONSENT_SERVICE.md](CIRIS_CONSENT_SERVICE.md)

### H3ERE 11-Step Pipeline
Every thought passes through the ethical reasoning pipeline:

| Step | Purpose | Documentation |
|------|---------|---------------|
| 1. START_ROUND | Initialize thought processing | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 2. GATHER_CONTEXT | Collect relevant information | [SYSTEMSNAPSHOT_DEEP_DIVE.md](SYSTEMSNAPSHOT_DEEP_DIVE.md) |
| 3. CSDMA | Common Sense evaluation | [DMA_CREATION_GUIDE.md](DMA_CREATION_GUIDE.md) |
| 4. DSDMA | Domain-Specific evaluation | [DMA_CREATION_GUIDE.md](DMA_CREATION_GUIDE.md) |
| 5. PDMA | Principled ethical evaluation | [DMA_CREATION_GUIDE.md](DMA_CREATION_GUIDE.md) |
| 6. IDMA | Intuition/epistemic diversity | [DMA_CREATION_GUIDE.md](DMA_CREATION_GUIDE.md) |
| 7. ASPDMA | Action Selection | [DMA_CREATION_GUIDE.md](DMA_CREATION_GUIDE.md) |
| 8-11. CONSCIENCE | 4-gate ethical validation | [ADAPTIVE_FILTERING.md](ADAPTIVE_FILTERING.md) |

### 6 Cognitive States
| State | Purpose | Documentation |
|-------|---------|---------------|
| SHUTDOWN | Graceful termination | [FSD/GRACEFUL_SHUTDOWN.md](../FSD/GRACEFUL_SHUTDOWN.md) |
| WAKEUP | Identity confirmation | [FSD/COGNITIVE_STATE_BEHAVIORS.md](../FSD/COGNITIVE_STATE_BEHAVIORS.md) |
| WORK | Primary task processing | [FSD/COGNITIVE_STATE_BEHAVIORS.md](../FSD/COGNITIVE_STATE_BEHAVIORS.md) |
| PLAY | Creative exploration | [DREAM_STATE_TASKS.md](DREAM_STATE_TASKS.md) |
| SOLITUDE | Reflection, maintenance | [DREAM_STATE_TASKS.md](DREAM_STATE_TASKS.md) |
| DREAM | Deep introspection | [DREAM_STATE_TASKS.md](DREAM_STATE_TASKS.md) |

### Multi-Occurrence Horizontal Scaling
Run multiple agent instances against shared database with atomic task claiming.

**Documentation**: [multi_occurrence_implementation_plan.md](multi_occurrence_implementation_plan.md)

## OpenClaw Security Analysis

OpenClaw represents a significant security concern in the 2026 landscape:

**Palo Alto Networks Warning**: "Lethal trifecta" of risks:
1. Access to private data (emails, files, calendars)
2. Exposure to untrusted content (messaging apps)
3. Ability to perform external communications while retaining memory

**Trend Micro Analysis**: The design amplifies agentic AI risks through persistent memory, broad permissions, and user-controlled configuration.

**Comparison to CIRIS**:
| Security Aspect | CIRIS 2.0 | OpenClaw |
|-----------------|-----------|----------|
| Memory Isolation | Per-user graph scoping | Persistent cross-session |
| Permission Model | 4-role hierarchy with crypto certs | User-configured, broad defaults |
| External Comms | Filtered through conscience | Direct access |
| Audit Trail | Immutable hash chains | Memory-based |
| Kill Switch | Ed25519 unfilterable | None |

## Resource Efficiency Comparison

| Framework | Verified Usage | Notes |
|-----------|---------------|-------|
| **CIRIS 2.0** | 250-600MB RAM | Baseline: ~207MB (CLI + Mock LLM, 22 services). Production: [scout.ciris.ai](https://scout.ciris.ai) shows 545MB (33 services, multi-occurrence, llama4scout). Run `python3 tools/introspect_memory.py` for local profiling. |
| **OpenClaw** | Variable | Node.js + integrations |
| **Google ADK** | Cloud-based | Vertex AI Agent Engine |
| **AG2** | Efficient | Minimal dependencies |
| **CrewAI** | Moderate | 5.76x faster than LangGraph |
| **LangGraph** | Variable | Performance improved in 2025-2026 |
| **LangChain** | GB+ typical | Memory management required |
| **AutoGPT** | 16GB+ RAM | High API costs |
| **MS Agent** | Variable | Enterprise infrastructure |

## Production Deployment Analysis

### Enterprise-Ready (GA)
1. **LangChain v1.2**: LinkedIn, Uber, Klarna, GitLab, Replit
2. **CrewAI v1.9**: 60% of Fortune 500, 60M+ executions/month
3. **LangGraph v1.0**: 43% of LangSmith organizations
4. **AG2**: Academic backing, DeepLearning.ai partnership
5. **Google ADK**: Vertex AI production deployment
6. **CIRIS 2.0**: Live at agents.ciris.ai with human oversight
7. **OpenClaw**: 145k GitHub stars, self-hosted production

### Preview/Beta
- **Microsoft Agent Framework**: GA targeted Q1 2026
- **AutoGPT v0.6.47**: Beta, Docker production-ready but not GA

## Recommendations by Use Case

### For Regulated Industries (Healthcare, Finance, Legal)
**Recommended**: CIRIS 2.0
- Only framework with all 7 ethical requirements
- Cryptographic audit trails with hash chains
- GDPR/DSAR automation with proof of compliance
- Four-role access hierarchy with WA certificates
- **Documentation**: [ARCHITECTURE.md](ARCHITECTURE.md), [CIRIS_2.0_BETA_FEATURES.md](CIRIS_2.0_BETA_FEATURES.md)

### For Enterprise Integration
**Recommended**: Microsoft Agent Framework or LangChain
- MS Agent for Microsoft ecosystems (after Q1 2026 GA)
- LangChain for flexibility and ecosystem breadth

### For Rapid Prototyping
**Recommended**: CrewAI
- No-code studio, templates
- 5.76x faster than LangGraph
- 100k+ certified developers

### For Complex Workflows
**Recommended**: LangGraph
- Node caching, deferred nodes
- Pre/post model hooks
- Visual debugging

### For Google Cloud Environments
**Recommended**: Google ADK
- Native Vertex AI integration
- Multi-language (Python, TypeScript)
- Gemini optimization with model flexibility

### For Offline/Constrained Environments
**Recommended**: CIRIS 2.0
- 250-600MB depending on adapters
- Local-first processing
- No external server dependency
- **Documentation**: [MOCK_LLM.md](MOCK_LLM.md)

### For Personal Automation (With Caution)
**Consider**: OpenClaw
- 50+ integrations, messaging apps
- Self-hosted, privacy-first design
- **Warning**: Review Palo Alto Networks security assessment before deployment

### For Research/Experimentation
**Recommended**: AutoGPT or AG2
- AutoGPT: Large community, cutting-edge experiments
- AG2: Step-through execution, OpenTelemetry

## 2026 Landscape Summary

The AI agent framework landscape has matured significantly:

1. **Ethics-First**: CIRIS 2.0 stands alone with comprehensive ethical architecture
2. **Enterprise Consolidation**: Microsoft converging AutoGen + Semantic Kernel
3. **Google Entry**: ADK provides model-agnostic alternative to proprietary solutions
4. **Performance Race**: CrewAI leading with 60M+ monthly executions
5. **Observability Standard**: OpenTelemetry becoming ubiquitous (AG2, LangSmith)
6. **MCP Adoption**: Model Context Protocol now industry standard
7. **Consumer Explosion**: OpenClaw's 145k stars shows demand for personal AI assistants
8. **Security Concerns**: Agentic AI risks highlighted by security researchers

## CIRIS Documentation Index

### Core Architecture
- [ARCHITECTURE.md](ARCHITECTURE.md) - 22 services, 6 buses
- [OVERVIEW.md](OVERVIEW.md) - System overview
- [ARCHITECTURE_PATTERN.md](ARCHITECTURE_PATTERN.md) - Intent-Driven Hybrid Architecture
- [CIRIS_2.0_BETA_FEATURES.md](CIRIS_2.0_BETA_FEATURES.md) - Complete feature list

### Ethical Framework
- [COVENANT.md](../COVENANT.md) - Published principles
- [ADAPTIVE_FILTERING.md](ADAPTIVE_FILTERING.md) - Runtime conscience
- [DEFERRAL_SYSTEM.md](DEFERRAL_SYSTEM.md) - Human deferral
- [WISE_AUTHORITIES.md](WISE_AUTHORITIES.md) - WA certificates
- [DMA_CREATION_GUIDE.md](DMA_CREATION_GUIDE.md) - Decision-Making Algorithms

### Security & Compliance
- [EMERGENCY_SHUTDOWN.md](EMERGENCY_SHUTDOWN.md) - Kill switch
- [TRACE_FORMAT.md](TRACE_FORMAT.md) - Cryptographic audit
- [CIRIS_CONSENT_SERVICE.md](CIRIS_CONSENT_SERVICE.md) - GDPR/DSAR
- [SECRETS_MANAGEMENT.md](SECRETS_MANAGEMENT.md) - AES-256-GCM encryption
- [FSD/AUTHENTICATION.md](../FSD/AUTHENTICATION.md) - OAuth, JWT, certificates

### Cognitive States
- [FSD/COGNITIVE_STATE_BEHAVIORS.md](../FSD/COGNITIVE_STATE_BEHAVIORS.md) - State machine
- [DREAM_STATE_TASKS.md](DREAM_STATE_TASKS.md) - PLAY, SOLITUDE, DREAM
- [FSD/GRACEFUL_SHUTDOWN.md](../FSD/GRACEFUL_SHUTDOWN.md) - SHUTDOWN state

### Special Features
- [FSD/AIR_ARTIFICIAL_INTERACTION_REMINDER.md](../FSD/AIR_ARTIFICIAL_INTERACTION_REMINDER.md) - Parasocial prevention
- [FSD/COVENANT_INVOCATION_SYSTEM.md](../FSD/COVENANT_INVOCATION_SYSTEM.md) - Emergency invocation
- [multi_occurrence_implementation_plan.md](multi_occurrence_implementation_plan.md) - Horizontal scaling
- [single_step.md](single_step.md) - Pipeline debugging

### API & Development
- [API_SPEC.md](API_SPEC.md) - REST API reference
- [QUICKSTART.md](QUICKSTART.md) - Getting started
- [FOR_NERDS.md](FOR_NERDS.md) - Developer guide
- [MOCK_LLM.md](MOCK_LLM.md) - Testing without LLM

### Performance Analysis
- [tools/introspect_memory.py](../tools/introspect_memory.py) - RSS memory profiling during agent lifecycle
  - Baseline (CLI + Mock LLM): ~207MB peak, stable after 2.3s startup
  - Run: `python3 tools/introspect_memory.py --duration 30`
- Production reference: [scout.ciris.ai](https://scout.ciris.ai) - Multi-occurrence agent (545MB, 33 services)

## Methodology

This analysis is based on:
- Official documentation review (Feb 2026)
- Production deployment verification
- Source code analysis
- Web search verification of current versions
- Direct testing (CIRIS)
- ciris.ai/compare and ciris.ai/safety

Last Updated: February 2026

---

*For corrections or updates to this analysis, please submit a PR to the CIRIS repository.*

## Sources

### Frameworks
- [AG2 GitHub](https://github.com/ag2ai/ag2)
- [AG2 OpenTelemetry](https://docs.ag2.ai/latest/docs/blog/2026/02/08/AG2-OpenTelemetry-Tracing/)
- [LangChain Changelog](https://docs.langchain.com/oss/python/releases/changelog)
- [LangChain Newsletter Jan 2026](https://blog.langchain.com/january-2026-langchain-newsletter/)
- [LangGraph Releases](https://github.com/langchain-ai/langgraph/releases)
- [CrewAI Changelog](https://docs.crewai.com/en/changelog)
- [AutoGPT Releases](https://github.com/Significant-Gravitas/AutoGPT/releases)
- [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview)
- [Google ADK Docs](https://google.github.io/adk-docs/)
- [OpenClaw - DigitalOcean](https://www.digitalocean.com/resources/articles/what-is-openclaw)
- [OpenClaw Security - Trend Micro](https://www.trendmicro.com/en_us/research/26/b/what-openclaw-reveals-about-agentic-assistants.html)

### CIRIS
- [CIRIS Compare](https://ciris.ai/compare)
- [CIRIS Safety](https://ciris.ai/safety)
