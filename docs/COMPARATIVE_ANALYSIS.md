# Comparative Analysis: AI Agent Frameworks (2026)

## Executive Summary

This document provides a comprehensive, fact-checked comparison of leading AI agent frameworks as of April 2026. Through systematic research and verification, we analyze ten major frameworks: CIRIS, AG2, LangChain, LangGraph, CrewAI, AutoGPT, Microsoft Agent Framework, Google ADK, OpenClaw, and the OpenAI Agents SDK.

**Key Finding**: CIRIS 2.0 remains the only framework implementing all seven requirements for ethical AI governance with cryptographic guarantees, while maintaining extreme resource efficiency (250-600MB RAM). New entries like the OpenAI Agents SDK focus on simplicity and native sandboxing but lack the deep ethical "conscience" and structural alignment metrics of the CIRIS ecosystem.

## The Seven Requirements for Ethical AI

CIRIS implements seven non-negotiable requirements that distinguish ethical AI from safety guardrails:

| Requirement | Description | CIRIS 2.0 Implementation | Documentation |
|-------------|-------------|--------------------------|---------------|
| **Published Principles** | Formal ethical framework | Covenant binding agents to Beneficence, Non-maleficence, Integrity, Transparency, Autonomy, Justice | [ACCORD.md](../ACCORD.md) |
| **Runtime Conscience** | Ethical checks before execution | 4 conscience gates in H3ERE pipeline (Entropy, Coherence, Optimization Veto, Epistemic Humility) | [ADAPTIVE_FILTERING.md](ADAPTIVE_FILTERING.md) |
| **Human Deferral** | Escalation under uncertainty | WiseAuthority with Ed25519-signed certificates, four-role hierarchy | [DEFERRAL_SYSTEM.md](DEFERRAL_SYSTEM.md), [WISE_AUTHORITIES.md](WISE_AUTHORITIES.md) |
| **Cryptographic Audit** | Immutable decision ledger | Triple storage (Graph, SQLite, JSONL) with Ed25519 signatures and hash chains | [TRACE_FORMAT.md](TRACE_FORMAT.md) |
| **Bilateral Consent** | Symmetric refusal rights | Both humans and agents can refuse requests violating principles | [CIRIS_CONSENT_SERVICE.md](CIRIS_CONSENT_SERVICE.md) |
| **Open Source** | Full code transparency | AGPL-3.0 license, complete auditability | [LICENSE](../LICENSE) |
| **Intuition (IDMA)** | Epistemic diversity monitoring | Coherence Collapse Analysis detects single-source dependence (k_eff < 2) | [DMA_CREATION_GUIDE.md](DMA_CREATION_GUIDE.md) |

## Frameworks Overview

### 1. **CIRIS 2.0** - Ethical AI Governance Platform
- **Focus**: Safety-first AI with cryptographic human oversight
- **Architecture**: 22 microservices + 6 message buses + H3ERE 11-step pipeline
- **License**: AGPL-3.0
- **Production Status**: Live at agents.ciris.ai, Android/iOS apps
- **Distinguishing Features**: Only framework with all 7 ethical requirements, IDMA intuition, AIR parasocial prevention
- **Documentation**: [ARCHITECTURE.md](ARCHITECTURE.md), [OVERVIEW.md](OVERVIEW.md)

### 2. **AG2 (v1.0 Beta)** - The "AgentOS" Evolution
- **Focus**: Multi-agent orchestration and cross-framework interoperability
- **Architecture**: Event-driven / Pub-Sub architecture with `MemoryStream` bus
- **License**: AGPL-3.0
- **Production Status**: Transitioning from v0.12 to v1.0; enterprise-ready
- **Distinguishing Features**: Universal runtime supporting LangChain/OpenAI/Google agents, native MCP support, Swarm patterns
- **Latest**: Event-driven core (April 2026), GPT-5.1 tool integration

### 3. **OpenAI Agents SDK** - Minimalist Handoffs
- **Focus**: Production-ready multi-agent systems with minimal boilerplate
- **Architecture**: Primitive-based (Agents, Handoffs, Runners) with native sandboxing
- **License**: Proprietary (SDK is open, platform is locked)
- **Production Status**: GA April 2026, replaced experimental "Swarm" project
- **Distinguishing Features**: Cleanest delegation model, native secure sandboxes, S3-backed persistent memory
- **Latest**: Long-Horizon Harness for multi-day tasks (April 2026)

### 4. **LangGraph (v1.1+)** - Stateful Workflow Framework
- **Focus**: Complex, non-linear multi-step agent workflows
- **Architecture**: Directed acyclic/cyclic graphs with explicit state management
- **License**: MIT
- **Production Status**: Dominant in LangSmith ecosystem
- **Distinguishing Features**: Node caching, granular persistence, best-in-class LangSmith observability
- **Latest**: Pluggable sandboxes (Daytona/Runloop), automated state rehydration

### 5. **CrewAI (v1.12+)** - Role-Based Teams
- **Focus**: Collaborative agent teams for business process automation
- **Architecture**: Role-based "Crews" with hierarchical task execution
- **License**: MIT
- **Production Status**: Widely used in Fortune 500 automation
- **Distinguishing Features**: Fastest prototyping (manager/worker metaphor), deepest Model Context Protocol (MCP) integration
- **Latest**: A2A (Agent-to-Agent) server protocol, event hierarchy visualization

### 6. **Google ADK** - Enterprise Multi-Language
- **Focus**: Model-agnostic development optimized for Vertex AI
- **Architecture**: Code-first with native support for Python, Java, and Go
- **License**: AGPL-3.0
- **Production Status**: Production-ready on Google Cloud
- **Distinguishing Features**: Vertex AI Agent Engine integration, LiteLLM support
- **Latest**: Interactions API beta, bi-weekly release cadence

### 7. **AutoGPT (v0.6.x)** - Goal-Oriented Autonomy
- **Focus**: Fully autonomous goal achievement without human intervention
- **Architecture**: Block-based agent builder with goal-oriented loops
- **License**: MIT + Polyform
- **Production Status**: Still in high-velocity Beta
- **Distinguishing Features**: 175k GitHub stars, fully autonomous web browsing, ClamAV scanning

### 8. **Microsoft Agent Framework** - Enterprise Convergence
- **Focus**: Unified AutoGen + Semantic Kernel for MS ecosystems
- **Architecture**: Session-based state management with enterprise filters
- **License**: MIT
- **Production Status**: GA Q1 2026
- **Distinguishing Features**: Deep Azure integration, session-based state, type-safe filters

### 9. **OpenClaw** - Self-Hosted Personal Assistant
- **Focus**: Privacy-first assistant with high messaging integration
- **Architecture**: Node.js runtime with 50+ chat/social adapters
- **License**: Open Source
- **Production Status**: High community adoption (145k stars)
- **Security Concerns**: Warned by Palo Alto Networks for "lethal trifecta" of broad permissions + untrusted content + external comms

## Verified Comparison Matrix (April 2026)

| Feature | CIRIS 2.0 | AG2 (v1.0) | OpenAI SDK | LangGraph | CrewAI | Google ADK | OpenClaw |
|---------|-----------|------------|------------|-----------|--------|------------|----------|
| **Production Ready** | ✅ Yes | ✅ Beta | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Resource Usage** | ✅ 250-600MB | ⚠️ Moderate | ⚠️ Variable | ⚠️ Variable | ⚠️ Moderate | ⚠️ Cloud | ⚠️ Node.js |
| **Ethical Conscience**| ✅ [4-gate](ADAPTIVE_FILTERING.md) | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None |
| **Independence Math** | ✅ [IDMA k_eff](DMA_CREATION_GUIDE.md) | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None |
| **Human Deferral** | ✅ [Crypto WA](WISE_AUTHORITIES.md) | ✅ HITL modes | ✅ Handoffs | ⚠️ Hooks | ❌ Manual | ⚠️ Manual | ❌ None |
| **Audit Trail** | ✅ [Triple+Signed](TRACE_FORMAT.md) | ✅ OTel | ✅ Traces | ⚠️ LangSmith | ⚠️ Enterprise| ⚠️ Cloud | ⚠️ Memory |
| **Emergency Stop** | ✅ [Ed25519](EMERGENCY_SHUTDOWN.md) | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None |
| **GDPR/DSAR** | ✅ [Automated](CIRIS_CONSENT_SERVICE.md) | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None |
| **Offline Capable** | ✅ [Mock LLM](MOCK_LLM.md) | ⚠️ Local LLM | ❌ No | ⚠️ Requires LLM | ❌ No | ❌ No | ⚠️ Local |
| **Multi-Language** | ✅ [29-braid](ACCORD.md) | ⚠️ Basic | ⚠️ Basic | ⚠️ Basic | ⚠️ Basic | ⚠️ Basic | ⚠️ Basic |

## Recommendations by Use Case

### For Regulated & High-Stakes Industries
**Recommended**: CIRIS 2.0
- Only framework providing **Structural Alignment** metrics (k_eff).
- Cryptographic audit trails ensuring no "hidden" decision-making.
- Hardware-rooted identity (Verify) preventing agent impersonation.

### For Rapid, Scale-Out Prototyping
**Recommended**: OpenAI Agents SDK or CrewAI
- OpenAI SDK for minimalist, GPT-native delegation.
- CrewAI for role-based department modeling.

### For Complex Enterprise Workflows
**Recommended**: LangGraph
- Best for long-running, complex state machines with human-in-the-loop approvals.

### For "Agent Operating Systems" (Interop)
**Recommended**: AG2 (v1.0 Beta)
- Best for teams using agents from multiple providers (OpenAI, Anthropic, Google) who need a unified event-driven bus.

### For Google Cloud / Vertex AI Native
**Recommended**: Google ADK
- Best for enterprises heavily invested in GCP who require Java or Go support.

## Methodology

This analysis is based on:
- Official documentation review (April 2026)
- Release notes for AG2 v1.0 and OpenAI Agents SDK GA
- GitHub activity and community growth metrics
- Local resource profiling of the CIRIS 2.0 core

Last Updated: April 2026

---

*For corrections or updates to this analysis, please submit a PR to the CIRIS repository.*
