# План внедрения тестового набора (золотая середина)

## Шаг 1. Инфраструктура тестов
- Создать каталог `tests/`, настроить `pyproject.toml` или `uv` на установку extras `tests`.
- Общие фикстуры: мок LLM/Tavily/MCP, временная рабочая директория, генератор snapshot-хелпера для SSE-чанков (выкидывает динамические поля id/time).
- Вспомогательные фабрики: сборка `ChatRequest` с разными сценарио (с tool_calls/без), генератор fake agent_id, фабрика временных файлов/деревьев.

## Шаг 2. Контрактные тесты стриминга/агента
- Проверить SSE-формат: список чанков включает `data: {}` и завершается `[DONE]`, tool_calls упакованы по контракту OpenAI.
- Reasoning-first: первый tool_call всегда `ReasoningTool`; при отсутствии tool_calls агент пишет Final с ошибкой.
- История: усечение/сохранение последних N сообщений; продолжение сессии по `model=agent_id`.
- Ограничения: итерации/поиски не превышают лимиты, состояния завершаются в `FINISH_STATES`.

## Шаг 3. Тесты тулкитов
- File tools: `read/write/edit`, `find/list/grep` — не выходят за workspace, уважают игнор списки, корректно фильтруют скрытые.
- RunCommandTool: таймаут/код возврата, stdout/stderr сохраняются; запрет опасных команд в тестовом окружении.
- CreateReportTool: создаёт Markdown c ссылками на источники в `reports_dir`.
- NextStepToolsBuilder: добавление пользовательского тула без изменения базового набора (OCP).

## Шаг 4. API/CLI слои
- FastAPI `/health`, `/v1/chat/completions` (happy path и негативные кейсы — пустые messages, невалидные модели).
- CLI `cli_stream.py fast/task/chat`: smoke на локальном запуске с моками; ensure exit code 0.
- Преобразование ответов в OpenAI-формат (role/content/delta) — snapshot ключевых полей.

## Шаг 5. Конфиг/старт/логирование
- Загрузка `config.yaml`/env: дефолты подхватываются, каталоги логов/репортов создаются.
- MCP off/on: при отсутствии `mcp.transport_config` тулы не добавляются, предупреждение логируется; при наличии — converter добавляет тулы.
- Логирование: `logger.info` с `agent_id`, `tool`, `iteration` присутствует; отсутствие лишних `print`.

## Шаг 6. Автоматизация и регрессия
- Добавить `make test` (`uv run pytest -q`) и CI-джобу.
- Покрыть ключевые регрессии известными багами (глобальное переключение system_prompt, FINISH_STATES как set).
- Бюджет по времени: baseline < 2-3 мин на CI; тяжёлые интеграции (реальные Tavily/MCP) пометить `@pytest.mark.external` и запускать опционально.

## Этапы внедрения (с отслеживанием)
- [x] Этап 1 — Базовый дым (high): `test_health`, `/v1/chat/completions` без tool_calls → Final с ошибкой (SSE `[DONE]`), добавить `make test`.
- [ ] Этап 2 — Контракты стриминга (high): snapshot SSE чанков; проверка первого сall Reasoning и fallback Final.
- [ ] Этап 3 — Тулкиты файлов (high): workspace guard, скрытые/игнор в find/list/grep.
- [ ] Этап 4 — RunCommand/таймауты (med): echo success, sleep timeout, stdout/stderr/exit.
- [ ] Этап 5 — История/лимиты/состояния (med): усечение истории, лимиты итераций/поисков → FINISH_STATES.
- [ ] Этап 6 — CreateReport/MCP toggle (med): Markdown с источниками, добавление/отсутствие MCP тулов по конфигу.
- [ ] Этап 7 — CLI smoke (med): `cli_stream.py fast/task/chat` с моками, код 0, `[DONE]`.
- [ ] Этап 8 — Негативные API кейсы (low): пустые messages, невалидный model → 400/422.
- [ ] Этап 9 — Регрессии (low): system_prompt swap изолирован; FINISH_STATES set обрабатывается циклом состояний.
