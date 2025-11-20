# Repository Guidelines

- Всегда отвечать пользователю на русском языке.

## Project Purpose & Stack
Platform for Schema-Guided Reasoning coding assistants: local-first CLI with streaming JSON. Stack: Python 3.12, Typer/Rich, FastAPI/uvicorn, Pydantic, httpx/OpenAI client. Tooling: Ruff + pre-commit, docformatter, mdformat. Config in `config.yaml` and logging in `logging_config.yaml`.

## Project Structure & Modules
Core logic: `sgr_deep_research/` (agents `core/agents`, prompts `prompts/`, API schemas `api/`, utilities/tools `core/tools/`, `services/`). CLIs: `cli_stream.py` (streamed chat/task) and `cli.py`. Benchmarks: `benchmark/`; docs/examples: `docs/`; configs: `config.yaml.example`, `logging_config.yaml`; Docker assets: `services/`.

## Key Capabilities
- Streaming JSON with Markdown rendering and multi-turn history.
- Workspace targeting: `--workspace/-w` scopes all file ops.
- Modes: chat (interactive), task (single instruction), fast (no typing effect; `--speed` tunes typing).
- Tools: file read/write/edit, grep/find/list, run shell commands, structured reasoning and final answers.

## Quick Start & Commands
- Install deps: `uv sync`.
- Configure: `cp config.yaml.example config.yaml` then set OpenAI/Tavily keys and paths.
- Run chat: `uv run cli_stream.py chat --debug --workspace <dir> [--speed 0/0.005]`.
- Single task: `uv run cli_stream.py task "<instruction>" [--workspace <dir>]`.
- Fast mode: `uv run cli_stream.py fast "<instruction>" [--workspace <dir>]`.
- Formatting/lint: `make format` (pre-commit hooks: Ruff, docformatter, mdformat).
- Build/install: `make wheel` or `make install`.
- Benchmarks: `uv run benchmark/run_benchmark.py` (set `benchmark/env.example`).
- Use MinGW terminal for work when on Windows.

## Coding Style & Conventions (Python/FastAPI)
- Python 3.12; 4-space indents, LF endings, 120-char lines (`ruff.toml`). Use type hints; prefer `|` over `Optional`. Avoid `requests` in async code—use async httpx. Keep simple conditionals concise (e.g., `if cond: do()`), avoid unnecessary braces/else nesting.
- Pure logic via `def`; I/O-bound via `async def`. Pydantic for validation/schemas.
- No stray `print` in services—use `logging.Logger`. Comments only for entity docs or complex logic; keep them minimal and English-only.
- FastAPI: avoid globals; if shared state is required, initialize it in a single place. Declarative routes with return types; `HTTPException` for expected errors; middleware for cross-cutting concerns, logging, error monitoring, and performance; lifespan contexts over raw startup/shutdown. Favor async end-to-end; avoid blocking calls.
- Error handling: guard clauses early, early returns over deep nesting, happy path last; log with context; custom errors/factories for consistency; optimize via async I/O, caching (Redis or in-memory) for static/frequent data, Pydantic serialization tuning, and lazy loading for large datasets/responses.

## Testing Guidelines
Pytest harness (deps under `[project.optional-dependencies.tests]`). Tests in `tests/` as `test_*.py`. Run `uv run pytest -q` or `uv run pytest --cov sgr_deep_research`. Prefer deterministic fixtures; mark/skip externals. Use `benchmark/` scripts for perf comparisons instead of inline timing.

## Commit & Pull Request Guidelines
Use light Conventional Commit style (`feat:`, `fix:`, `docs:`). Keep commits small and reversible. PRs: intent summary, commands/tests run, linked issues, media for UX/CLI changes when helpful. Never commit secrets—keep keys in `config.yaml` or env vars; mirror config changes in `config.yaml.example` and note migrations when behavior shifts.
