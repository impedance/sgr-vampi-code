# Repository Guidelines

- Всегда отвечать пользователю на русском языке.

## Project Purpose & Stack
Platform for Schema-Guided Reasoning coding assistants: local-first CLI with streaming JSON. Stack: Python 3.12, Typer/Rich, FastAPI/uvicorn, Pydantic, httpx/OpenAI client. Tooling: Ruff + pre-commit, docformatter, mdformat. Config in `config.yaml` and logging in `logging_config.yaml`.

## Project Structure & Modules
Core logic: `sgr_deep_research/` (agents `core/agents`, prompts `prompts/`, API schemas `api/`, utilities/tools `core/tools/`, `services/`). CLIs: `cli_stream.py` (streamed chat/task) and `cli.py`. Benchmarks: `benchmark/`; docs/examples: `docs/`; configs: `config.yaml.example`, `logging_config.yaml`; Docker assets: `services/`.

## Architecture Overview
- Agents: `BaseAgent` orchestrates reasoning → tool selection → action with streaming/logging. `SGRResearchAgent` adds dynamic NextStepToolsBuilder unions, web search toolkit, and iteration/search caps. `SGRVampiCodeAgent` removes web search, uses code-specific prompt, truncates conversation history, and forces ReasoningTool first.
- Data model: `ResearchContext` tracks state, iterations, counters, working directory, searches (`SearchResult`), and sources (`SourceData`); `AgentStatesEnum` governs lifecycle. Settings loaded via `AppConfig` (`settings.py`, EnvYAML) covering OpenAI, Tavily, search/scraping, prompts, execution, logging, MCP.
- Tooling: Coding tools (read/write/edit, grep/find/list, run commands) plus optional web search/extract; research tools (Tavily search/extract, `CreateReportTool`). `MCP2ToolConverter` builds Pydantic tools from MCP schemas (lifespan startup).
- Streaming & interfaces: `OpenAIStreamingGenerator` emits SSE-like chunks consumed by FastAPI and CLI. FastAPI app (`__main__.py`) exposes health, agents list/state, OpenAI-compatible `/v1/chat/completions`; CLI `cli.py` talks to HTTP, `cli_stream.py` runs locally.
- Limitations: API agent storage is in-memory (no persistence/HA); `SGRVampiCodeAgent` temporarily toggles global prompt file; `AgentStatesEnum.FINISH_STATES` is a set member—watch for enum/value handling.
- Logs/reports: agent JSON logs go to `logs_dir` (see `config.execution.logs_dir`), file names include timestamp/agent id; reports from `CreateReportTool` go to `reports_dir` with markdown content plus sources.
- Env/servers: settings load via `APP_CONFIG` (path to YAML, default `config.yaml` in CWD). FastAPI server entrypoint `python -m sgr_deep_research` (or `python -m sgr_deep_research --host ... --port ...`), env HOST/PORT override defaults. Requires OpenAI/Tavily keys in config/env; MCP starts if `mcp.transport_config` is set.
- Streaming contract: SSE-like lines `data: <json>\n\n` with `[DONE]` terminator; tool calls streamed as chunks with function name/arguments; clients parse tool_calls to render reasoning/final panels.
- Sessions: `/v1/chat/completions` accepts `model` as agent id to continue existing agent (only while process lives; in-memory `agents_storage`).
- Prompts: prompt files in `sgr_deep_research/prompts` (`system_prompt.txt`, `code_system_prompt.txt`, `coding_agent_prompt.txt`, `initial_user_request.txt`, `clarification_response.txt`). Coding agent temporarily swaps system prompt file at runtime.

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
