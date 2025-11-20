# Repository Guidelines

## Project Purpose & Stack
Platform for Schema-Guided Reasoning coding assistants: local-first CLI with streaming JSON and optional API. Stack: Python 3.12, Typer/Rich for CLI, FastAPI/uvicorn for services, Pydantic for config/IO models, httpx/OpenAI client for LLM calls. Tooling: Ruff + pre-commit, docformatter, mdformat; dependencies pinned via `uv.lock`. Config lives in `config.yaml` (see example) and `logging_config.yaml`.

## Project Structure & Module Organization
Core logic in `sgr_deep_research/`: agents (`core/agents`), prompts (`prompts/`), HTTP/API schemas (`api/`), utilities (`core/tools/`, `services/`). CLIs: `cli_stream.py` (streamed chat/task) and `cli.py`. Benchmarks in `benchmark/`; examples/docs in `docs/`; runtime configs in `config.yaml.example` and `logging_config.yaml`. Docker assets in `services/`, visuals in `assets/`.

## Build, Test, and Development Commands
- Install deps: `uv sync`.
- Run chat UI: `uv run cli_stream.py chat --debug --workspace <dir>`.
- Single task modes: `uv run cli_stream.py task "<instruction>"` or `uv run cli_stream.py fast "<instruction>"`.
- Formatting/lint sweep: `make format` (pre-commit hooks: Ruff, docformatter, mdformat).
- Build artifact: `make wheel` or `make install` (wheel + local pip install).
- Benchmarks: `uv run benchmark/run_benchmark.py` (configure `benchmark/env.example`).

## Coding Style & Conventions (Python/FastAPI)
- Python 3.12; 4-space indents, LF endings, 120-char lines (`ruff.toml`). Use type hints; prefer `|` over `Optional`. Avoid `requests` in async code; use httpx/async clients.
- Pure logic stays `def`; I/O-bound work uses `async def`. Prefer Pydantic models for validation/IO schemas.
- No stray `print` in services—use `logging.Logger` per `logging_config.yaml`.
- FastAPI: avoid globals; centralize app state. Use declarative routes with return types, `HTTPException` for expected errors, middleware for cross-cutting concerns, and lifespan contexts over raw startup/shutdown events. Favor async end-to-end; avoid blocking calls.
- Error handling: guard clauses for edge cases, early returns over deep nesting, happy path last. Log with context; use custom errors/factories for consistency. Optimize via async I/O, caching when needed, and lazy loading for heavy data.

## Testing Guidelines
Pytest is the harness (optional deps under `[project.optional-dependencies.tests]`). Tests live in `tests/` as `test_*.py`. Run `uv run pytest -q` or `uv run pytest --cov sgr_deep_research`. Prefer deterministic fixtures; mark/skip anything external. Use `benchmark/` scripts for performance comparisons instead of inline timing.

## Commit & Pull Request Guidelines
Commit messages follow light Conventional Commit style (`feat:`, `fix:`, `docs:`). Keep commits small and reversible. PRs should include intent summary, commands/tests run, linked issues, and media for UX/CLI changes when helpful. Never commit secrets—keep keys in `config.yaml` or env vars; mirror config changes in `config.yaml.example` and note migrations when behavior shifts.
