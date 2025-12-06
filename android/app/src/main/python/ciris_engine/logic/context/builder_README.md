[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/CIRISAI/CIRISAgent)

# Context Builder

The Context Builder orchestrates the construction of comprehensive `ThoughtContext` objects for the agent. It delegates subsystem snapshot logic to helper modules to keep the core builder lightweight.

## Helper Modules
- `system_snapshot.py` – assembles `SystemSnapshot` instances from memory, secrets, telemetry, and external providers.
- `secrets_snapshot.py` – safely prepares secret references for inclusion in snapshots.

Each helper is exported via the `context` package for reuse.
