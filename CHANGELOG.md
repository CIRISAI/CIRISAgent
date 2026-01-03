# Changelog

All notable changes to CIRIS Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.8.0] - 2026-01-02

### Added

- **Coherence Ratchet Trace Capture** - Full 6-component reasoning trace for corpus building
  - Captures: situation_analysis, ethical_pdma, csdma, action_selection, conscience_check, guardrails
  - Cryptographic signing of complete traces for immutability
  - Mock logshipper endpoint for testing trace collection
  - Transparency API endpoints for trace retrieval (`/v1/transparency/traces/latest`)

- **OpenRouter Provider Routing** - Select/ignore specific LLM backends
  - Environment variables: `OPENROUTER_PROVIDER_ORDER`, `OPENROUTER_IGNORE_PROVIDERS`
  - Provider config passed via `extra_body` to Instructor
  - Success logging: `[OPENROUTER] SUCCESS - Provider: {name}`

- **System/Error Message Visibility** - Messages visible to all users via system channel
  - System and error messages emitted to agent history
  - `is_agent=True` on system/error messages prevents agent self-observation
  - System channel included in all user channel queries

### Changed

- **LLM Bus Retry Logic** - 3 retries per service before failover
  - Configurable retry count with exponential backoff
  - Log deduplication for repeated failures (WARNING instead of ERROR)
  - Circuit breaker integration with retry exhaustion

- **Changelog Rotation** - Archived 2025 changelog
  - `CHANGELOG-2025.md` contains v1.1.1 through v1.7.9
  - Fresh `CHANGELOG.md` for 2026

### Fixed

- **ServiceRegistry Lookup for Modular Adapters** - Transparency routes now query ServiceRegistry
  - Modular adapters register with ServiceRegistry, not runtime.adapters
  - Fixed trace API returning 404/500 for covenant_metrics traces

## [Unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

---

## Previous Years

- [2025 Changelog](./CHANGELOG-2025.md) - v1.1.1 through v1.7.9
