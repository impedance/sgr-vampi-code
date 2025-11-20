# Developer Guide (Architecture & Ops)

## Runtime & Config
- Python 3.12; install deps via `uv sync`. Config loads from YAML (default `config.yaml` in CWD or `APP_CONFIG` path). Env HOST/PORT override FastAPI server flags.
- Keys: OpenAI (`openai.api_key`), Tavily (`tavily.api_key`), optional proxy (`openai.proxy`), MCP transport (`mcp.transport_config`). Logging config at `logging_config.yaml`.
- Logs/reports: `execution.logs_dir` for agent JSON logs, `execution.reports_dir` for Markdown reports from `CreateReportTool` (includes sources). Directories auto-created.

## Server & Entry Points
- FastAPI app: `python -m sgr_deep_research [--host ... --port ...]`. Lifespan builds MCP tools if `mcp.transport_config` present. Endpoints: health, agents list/state, OpenAI-compatible `/v1/chat/completions`, `/agents/{id}/provide_clarification`.
- CLI:
  - `cli_stream.py` runs coding agent locally with Rich JSON streaming.
  - `cli.py` is an OpenAI client to the local server (`base_url http://localhost:8010/v1`), renders reasoning/final in panels.

## Agents & Flow
- `BaseAgent.execute`: loop reasoning → select tool → act; streams chunks via `OpenAIStreamingGenerator`; saves log per run.
- `SGRResearchAgent`: builds discriminated union of tools (`NextStepToolsBuilder`), includes web search + MCP tools; caps iterations/searches.
- `SGRVampiCodeAgent`: coding toolkit, code-specific prompt, history truncation, forces ReasoningTool first; if tool_calls missing, falls back to FinalAnswerTool.
- State store: in-memory `agents_storage` in API; no persistence/HA or TTL; agent continuity by passing agent id as `model` in `/v1/chat/completions` while process lives.

## Streaming Contract
- SSE-like: `data: <json>\n\n` chunks; terminator `[DONE]`. Tool calls streamed with `tool_calls.function.name/arguments`; reasoning/final tools emit JSON payloads.
- `OpenAIStreamingGenerator` adds chunks per LLM delta and per tool call; clients must handle partial JSON until completion.

## Tools
- Base: `ReasoningTool`, `FinalAnswerTool`, `NextStepToolsBuilder`; `MCPBaseTool` wraps `fastmcp.Client`.
- Coding: read/write/edit (path resolved vs `context.working_directory`), grep/find/list (filters hidden/ignored dirs), run commands with timeout. Web search/extract included for parity.
- Research: Tavily search/extract (`services/tavily_search.py`), `CreateReportTool` writes MD with citations and sources.
- MCP: `MCP2ToolConverter` dynamically builds Pydantic tools from MCP schemas; `mcp.context_limit` truncates returned content.

## Prompts
- Files in `sgr_deep_research/prompts`: `system_prompt.txt`, `code_system_prompt.txt`, `coding_agent_prompt.txt`, `initial_user_request.txt`, `clarification_response.txt`.
- Coding agent temporarily swaps `config.prompts.system_prompt_file` to `code_system_prompt.txt`; be mindful of global side effects if multiple agents run.

## Caveats & Gotchas
- `AgentStatesEnum.FINISH_STATES` is a set member; code uses `.value`, which is unusual—keep in mind if extending states.
- In-memory agent storage: restart drops sessions, multiple workers won’t share state.
- Streaming format is hand-rolled; any client must match SSE framing (`data:` lines, blank line separation).
- MCP optional: with empty `mcp.transport_config` converter logs warning and yields no MCP tools.
