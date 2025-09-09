# Test Suite Overview

This directory contains the automated tests for CIRISAgent. The suite is designed to run fully offline and exercises the majority of the engine modules. A few key points:

* **Hundreds of tests** cover action handlers, runtime components, persistence layers and CLI entry points.
* Live tests under `tests/live/` require valid Discord credentials and are skipped when the environment variables are absent.
* `conftest.py` loads environment variables from a `.env` file if present so tests can run with local configuration. Fixtures in `tests/fixtures.py` provide a basic `ServiceRegistry` and runtime for integration style tests.
* The `ciris_engine` package is largely fixture driven to allow unit tests to focus on behaviour without external services.

Run the suite with:

```bash
pytest -q
```

All tests should pass offline when `OPENAI_API_KEY` and other optional environment variables are unset or set to dummy values. The live Discord test will automatically skip if no credentials are provided.
