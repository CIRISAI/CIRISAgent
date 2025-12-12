# Repository Guidelines

## Project Structure & Module Organization
- `ciris_engine/` houses the H3ERE core (adapters, buses, schemas, utilities).
- `ciris_adapters/` stores pluggable services; copy the `mock_llm/` manifest layout for new modules.
- `ciris_sdk/` ships the client SDK and telemetry resources.
- `shared/` and `tools/` bundle OAuth helpers plus QA, security, and Grace scripts.
- `tests/` mirrors engine domains with network suites isolated under `tests/live/`.
- `docs/`, `deployment/`, and `config/` provide architecture notes, Compose manifests, and env defaults.

## Build, Test, and Development Commands
- Install deps: `pip install -r requirements.txt` (+ `requirements-dev.txt` for tooling).
- Run adapters: `python main.py --adapter discord --guild-id <id>` or `--adapter api --port 8000`.
- Fast tests: `pytest -m "not live"`; add integrations with `-m "integration"` when needed.
- Type check: `mypy ciris_engine/ ciris_adapters/ ciris_sdk/` (strict per `mypy.ini`).
- Prune dead code: `vulture ciris_engine/ ciris_adapters/` (per `pyproject.toml`).

## Coding Style & Naming Conventions
- Stick to Python 3.12, four-space indents, `snake_case` modules, `PascalCase` classes, and `SCREAMING_SNAKE_CASE` constants; prefer Enums and Pydantic over raw dicts.
- Uphold the Three Rules (`CLAUDE.md`): no untyped dicts, no bypass patterns, no exceptions.
- Avoid `Dict[str, Any]`; extend schemas in `ciris_engine/schemas/` or add local Pydantic models when introducing fields.
- Respect async boundaries: adapters and buses stay async while helpers remain synchronous unless justified.

## Testing Guidelines
- Place tests beside their domain (e.g., adapters under `tests/adapters/<adapter>`); use `test_*.py` names.
- Pytest logs to `test_logs/pytest.log`; inspect failures before reruns.
- Mark slow, integration, or live scenarios with the corresponding pytest markers so CI filters work.
- Target ≥80% coverage on critical paths; run `pytest --cov=ciris_engine --cov=ciris_adapters`.

## Commit & Pull Request Guidelines
- Follow conventional commits (`fix:`, `perf:`, `feat:`) and keep each commit atomic.
- Branch from `main` using `feature/<topic>` or `fix/<issue>` and limit scope.
- Run `pytest`, `mypy`, and touched tools before opening a PR; document intentional skips in the description.
- Link the relevant issue, note config/deployment impacts, and attach telemetry or screenshots when user-facing.
- Confirm the checklist in `CONTRIBUTING.md` (tests, docs, type safety, H3ERE alignment) prior to requesting review.

## Security & Configuration Tips
- Keep secrets out of the repo; `config/environment_variables.md` lists required keys for adapters and services.
- When editing manifests or Docker assets, mirror changes across `docker-compose-*.yml` and `deployment/` so environments stay aligned.
- Never add medical or clinical capabilities—diagnosis, treatment, or patient data flows are prohibited and blocked at the bus level.
