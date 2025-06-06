[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

# CIRIS Engine (CIRISAgent)

> Edge-side reasoning runtime for AI agents.
> Status: **PRE-ALPHA — API & internal architecture subject to change**

---

## Overview

**CIRIS Engine** (also referred to as CIRISAgent in some contexts) is a Python-based runtime environment designed to enable AI agents to perform complex reasoning tasks. It can run on various devices, from laptops to single-board computers.

The core of CIRIS Engine is its ability to process "thoughts" (inputs or internal states) through a series of Decision Making Algorithms (DMAs):

*   **Ethical PDMA (Principled Decision-Making Algorithm):** Evaluates the ethical implications of a thought.
*   **CSDMA (Common Sense DMA):** Assesses the common-sense plausibility and clarity of a thought.
*   **DSDMA (Domain-Specific DMA):** Applies domain-specific knowledge and heuristics. Different DSDMAs can be created for various specialized tasks or agent roles (e.g., `StudentDSDMA`, `BasicTeacherDSDMA`).
*   **ASPDMA (Action‑Selection PDMA):** Determines the final action an agent should take based on the outputs of the preceding DMAs and the agent's current state.

Actions chosen by the PDMA are routed through an `ActionDispatcher`. Memory operations use `DiscordGraphMemory` for persistence.

CIRIS Engine supports different **agent profiles** (e.g., "Student", "Teacher" defined in `ciris_profiles/`) which can customize the behavior, prompting, and available DSDMAs for an agent. This allows for tailored reasoning processes depending on the agent's role or task.

The system is designed for modularity, allowing developers to create and integrate new DMAs and agent profiles.

---

## Key Features

### 🧠 **Advanced Decision Making Architecture**
*   **[Decision Making Algorithms (DMAs)](ciris_engine/dma/README.md):** Parallel evaluation through Ethical PDMA, Common Sense DMA, and Domain-Specific DMA with sophisticated error handling and circuit breaker protection
*   **Profile-Driven Customization:** YAML-based agent profiles with specialized behavior for different roles (teacher, student, etc.)
*   **Action Selection:** Intelligent 3×3×3 action space selection with context-aware parameter injection

### 🔐 **Enterprise Security Features**
*   **[Secrets Management](docs/SECRETS_MANAGEMENT.md):** Automatic detection, encryption, and decapsulation of sensitive information with AES-256-GCM
*   **[Cryptographic Audit Trail](ciris_engine/audit/README.md):** Tamper-evident logging with hash chains, RSA digital signatures, and comprehensive integrity verification
*   **[Adaptive Filtering](docs/ADAPTIVE_FILTERING.md):** Intelligent message prioritization with trust-based user management and spam detection

### 🏗️ **Multi-Platform Architecture**
*   **[Platform Adapters](ciris_engine/adapters/README.md):** Discord, CLI, and API adapters with consistent service interfaces and automatic secrets processing
*   **Service Registry:** Dynamic service discovery with capability-based selection and circuit breaker protection
*   **Runtime Flexibility:** Supports CLI, Discord bot, and API server modes with seamless switching

### 📊 **Observability & Monitoring**
*   **[Telemetry System](docs/TELEMETRY_SYSTEM.md):** Multi-tier metric collection with security filtering and resource monitoring
*   **Circuit Breakers:** Automatic service protection with graceful degradation
*   **Performance Monitoring:** Real-time resource usage tracking and adaptive throttling

### 🧩 **Advanced Memory & Processing**
*   **Graph Memory:** SQLite-backed graph storage with automatic secrets encryption and WA-authorized updates
*   **[Action Handlers](ciris_engine/action_handlers/README.md):** Comprehensive handler system with automatic secrets decapsulation and service integration
*   **[Configuration Management](ciris_engine/config/README.md):** Multi-source configuration with agent self-configuration through memory operations
*   **[Context Management](ciris_engine/context/README.md):** Multi-source context aggregation with system snapshots and user profile enrichment
*   **[Processing Engine](ciris_engine/processor/README.md):** Multi-state processing architecture with specialized processors for WORK, PLAY, DREAM, and SOLITUDE modes
*   **Thought Processing:** Multi-round pondering with escalation to Wise Authority

### 🎯 **Core Infrastructure**
*   **[Epistemic Faculties](ciris_engine/faculties/README.md):** Advanced content evaluation through specialized entropy, coherence, and decision analysis faculties
*   **[Service Registry](ciris_engine/registries/README.md):** Priority-based service discovery with circuit breaker patterns and automatic failover
*   **[Prompt Formatters](ciris_engine/formatters/README.md):** Composable text formatting utilities for consistent LLM prompt engineering

## Repository Structure

The repository root contains the following notable directories and scripts:

* `ciris_engine/` – core engine code including DMAs, runtime logic, and prompt utilities.
* `ciris_profiles/` – YAML files defining agent behavior and available actions.
* `tests/` – unit and integration tests for the engine.
* `docker/` – container build scripts and Dockerfiles.
* `main.py` – unified entry point for running the agent or engine in CLI,
  Discord, or API modes.

## Guardrails Summary

The system enforces the following guardrails via `app_config.guardrails_config`:

| Guardrail            | Description                                                                       |
|----------------------|-----------------------------------------------------------------------------------|
| entropy              | Prevents nonsensical replies                                                       |
| coherence            | Ensures output flows logically from prior context                                 |
| optimization_veto    | Aborts actions that sacrifice autonomy or diversity for entropy reduction |
| epistemic_humility   | Reflects on uncertainties and may defer or abort if certainty is low |
| rate_limit_observe   | Caps new tasks from Discord per OBSERVE cycle (10 messages max)                    |
| idempotency_tasks    | Prevents duplicate tasks for the same message                                      |
| pii_non_repetition   | Flags and prevents verbatim repetition of personal information                     |
| input_sanitisation   | Cleans inputs using `bleach` (no regex)                                            |
| metadata_schema      | Enforces a structured schema and max size for stored metadata                      |
| graphql_minimal      | Limits enrichment to nick/channel with 3&nbsp;s timeout and fallback               |
| graceful_shutdown    | Services stop cleanly or are forced after a 10&nbsp;s timeout                      |

---

## 3×3×3 Handler Actions

The `HandlerActionType` enum defines core operations grouped as:

* **External Actions:** `OBSERVE`, `SPEAK`, `TOOL`
* **Control Responses:** `REJECT`, `PONDER`, `DEFER`
* **Memory Operations:** `MEMORIZE`, `RECALL`, `FORGET` (now fully supported and enabled by default)
* **Terminal:** `TASK_COMPLETE`

These actions are processed by matching handlers within the engine. 

### Audit Logging
All handler actions are logged via the integrated `AuditService`, which supports log rotation, retention, and query. Audit logs are written to `audit_logs.jsonl` by default and can be queried for compliance and debugging.

Example memory action JSON:

```json
{
  "action": "MEMORIZE",
  "scope": "local",
  "payload": {
    "node": {"id": "User:alice", "type": "user", "scope": "local", "attrs": {"nick": "alice"}}
  }
}
```

---

## Core Components (in `ciris_engine/`)

*   `core/`: Contains data schemas (`config_schemas.py`, `agent_core_schemas.py`, `foundational_schemas.py`), configuration management (`config_manager.py`), the `AgentProcessor`, `WorkflowCoordinator`, `ActionDispatcher`, and persistence layer (`persistence.py`).
*   `dma/`: Implementations of the various DMAs (EthicalPDMA, CSDMA, DSDMA, ASPDMA).
*   `utils/`: Utility helpers like `logging_config.py` and an asynchronous `load_profile` function in `profile_loader.py` (recall to `await` it).
*   `guardrails/`: Ethical guardrail implementation.
*   `adapters/`: adapters for audit logging, LLM access, and other integrations.
*   `ciris_profiles/`: Directory for agent profile YAML files (e.g., `student.yaml`, `teacher.yaml`).

---

## Getting Started

### Prerequisites

*   Python 3.10+ (as per project structure, though 3.9+ might work)
*   An OpenAI API key (or an API key for a compatible service like Together.ai).
*   For Discord examples: A Discord Bot Token.

### Installation

1.  Clone the repository:
    ```bash
    git clone <your-repository-url> 
    # Replace <your-repository-url> with the actual URL
    cd CIRISEngine 
    # Or your project's root directory name
    ```
2.  Install dependencies (it's recommended to use a virtual environment):
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```

### Environment Variables

Set the following environment variables (see `.env.example` for a template):

*   `OPENAI_API_KEY`: **Required.** Your API key for the LLM service. If running a local model, set `OPENAI_API_BASE` and `OPENAI_MODEL_NAME` and provide any value for this key.
*   `DISCORD_BOT_TOKEN`: **Required for Discord agents.** Your Discord bot token.
*   `OPENAI_BASE_URL` (Optional): If using a non-OpenAI endpoint (e.g., Together.ai, local LLM server), set this to the base URL (e.g., `https://api.together.xyz/v1/`).
*   `OPENAI_MODEL_NAME` (Optional): Specify the LLM model to be used (e.g., `meta-llama/Llama-3-70b-chat-hf`). Defaults to `gpt-4o-mini` if not set (see `ciris_engine/core/config_schemas.py`).
*   `WA_USER_ID` (Optional): Discord User ID for the Wise Authority mentioned in deferral messages.
*   `DISCORD_CHANNEL_ID` (Optional): ID of the Discord channel the agent listens to for new messages.
*   `DISCORD_DEFERRAL_CHANNEL_ID` (Optional): Channel ID used for deferral reports.
*   `SNORE_CHANNEL_ID` (Optional): Channel ID used for runtime heartbeat notifications.
*   `WA_DISCORD_USER` (Optional): Fallback Discord username for the Wise Authority. Defaults to `somecomputerguy`.
*   `LOG_LEVEL` (Optional): Set to `DEBUG` for verbose logging. Defaults to `INFO`.

Example:
```bash
export OPENAI_API_KEY="your_api_key_here"
export DISCORD_BOT_TOKEN="your_discord_bot_token_here"
# export DISCORD_CHANNEL_ID="123"                   # Channel the bot listens to
# export DISCORD_DEFERRAL_CHANNEL_ID="456"          # Channel used for deferral reports
# export WA_USER_ID="123456789012345678"            # Mention this user on deferrals
# export SNORE_CHANNEL_ID="789"                     # Optional status channel
# export OPENAI_API_BASE="https://api.together.xyz/v1/" # Uncomment if using a custom endpoint
# export OPENAI_MODEL_NAME="meta-llama/Llama-3-70b-chat-hf" # Uncomment to specify a model
```

---

## Running Agents

Run the agent using the unified entry point. Specify the mode and profile as needed:

```bash
python main.py --mode auto --profile default
```

The script automatically loads the CLI runtime and adds Discord if a bot token is available:

```bash
python main.py --profile teacher   # Auto-detect Discord support
```

When a Discord token is present the `DiscordRuntime` registers its communication
and observer services with `Priority.HIGH`. The bundled CLI services are also
registered at `Priority.NORMAL` so the agent can fall back to the console if the
Discord connection drops. Running without a token automatically selects the
`CLIRuntime`.

During startup each runtime waits for the service registry to report that core
services are available. If communication, memory, audit logging, or the LLM
service are missing for more than 30 seconds an error is logged but the runtime
continues, allowing partial functionality in constrained environments.

CLI communication acts as the lowest priority service on the bus. If the CLI
adapter is unable to process incoming or outgoing messages for more than 30
seconds the runtime will trigger a graceful shutdown to avoid a wedged state.

Use `--mode cli` for a local command-line interface or `--mode api` for the API runtime. When running the API, you can set `--host` and `--port` to control the listen address. Disable interactive CLI input with `--no-interactive`. Enable debug logging with `--debug`.
For offline testing you can pass `--mock-llm` to use the bundled mock LLM service.

Play Mode and Solitude Mode provide short introspective sessions for the agent. Each lasts five minutes and is offered at random roughly once per hour. In safety-critical deployments, these sessions should be restricted to non‑shift hours via agent configuration.

---
## Testing

Run the full test suite with:

```bash
pytest -q
```

All functional and guardrail validation tests should pass.

---

## Contributing

PRs welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute to this project.

Please ensure your contributions align with the core goals of the CIRIS Engine. If adding new features, consider how they integrate with the existing DMA workflow and agent profile system.

Run `pytest` to ensure all tests pass before submitting a pull request.

---

## License

Apache-2.0 © 2025 CIRIS AI Project
