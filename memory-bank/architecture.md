# Архитектура проекта SGR Vampi Code

## Назначение и интерфейсы
- Локальный агент с двумя интерфейсами: FastAPI сервер (OpenAI‑совместимые `/v1/chat/completions`) и CLI-клиенты (`cli.py` через HTTP, `cli_stream.py` локально).
- Стриминг построен на собственном генераторе SSE-совместимых чанков (`OpenAIStreamingGenerator`), которые читают CLI и HTTP-ответы.

## Конфигурация и окружение
- Pydantic-модели настроек (`settings.py`, `AppConfig`): OpenAI, Tavily, search/scraping, prompts, execution (logs/reports), logging, MCP.
- Конфигурация загружается из YAML (EnvYAML), логирование из `logging_config.yaml`; каталоги логов/репортов создаются при старте.

## Модель данных
- `ResearchContext`: состояние агента (`AgentStatesEnum`), итерация, счётчики поисков/уточнений, рабочая директория, результаты выполнения, поисковые запросы (`SearchResult`), источники (`SourceData`), событие для синхронизации уточнений.
- API-модели (`api/models.py`): OpenAI-совместимые запросы/ответы, перечисление моделей агентов, состояния агентов для мониторинга.

## Архитектура агентов
- `BaseAgent`: цикл reasoning → выбор инструмента → выполнение; управляет контекстом, стримингом, логами; сохраняет JSON-лог для каждой сессии.
- `SGRResearchAgent`: динамический тулкит (системные Reasoning/Final + research + MCP), билдер `NextStepToolsBuilder` генерирует pydantic-union для выбора следующего шага; ограничивает поиск/итерации.
- `SGRVampiCodeAgent`: кодовый агент без веб-поиска, специализированный системный промпт, усечение истории до N сообщений, строгий вызов Reasoning первым; при ошибке tool_calls завершает FinalAnswerTool.
- Хранение агентов в API — in-memory `agents_storage` (подходит для одиночного процесса, нет персистентности/горизонтального масштабирования).

## Тулкиты
- Базовые (`core/tools/base.py`): `ReasoningTool`, `FinalAnswerTool`, `NextStepToolsBuilder`; `MCPBaseTool` для вызова MCP через `fastmcp.Client`.
- Кодовые (`core/tools/coding.py`): read/write/edit с защитой по cwd, grep/find/list, run command, плюс веб-поиск/экстракт.
- Исследование (`core/tools/research.py`): Tavily поиск/экстракция (`services/tavily_search.py`), `CreateReportTool` генерирует Markdown-отчёт с цитированием/источниками.
- MCP: `MCP2ToolConverter` превращает схемы MCP-сервера в Pydantic-тулы на старте (lifespan FastAPI).

## Сервер
- FastAPI приложение (`__main__.py`): lifespan поднимает MCP-тулы; роуты health, список/состояние агентов, OpenAI-совместимый чат-эндпоинт с стримингом; хранит агенты в памяти.

## Риски/тонкости
- `AgentStatesEnum.FINISH_STATES` хранится как член Enum со множеством; в цикле используется `FINISH_STATES.value`, что нетривиально.
- `SGRVampiCodeAgent._get_code_system_prompt` временно меняет `config.prompts.system_prompt_file` глобально (может вызвать гонки при нескольких агентских экземплярах).
- In-memory state в API теряется при рестарте, нет TTL/очистки/шардинга между воркерами.
