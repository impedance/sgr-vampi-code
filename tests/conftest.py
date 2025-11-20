import importlib
import textwrap
from pathlib import Path

import pytest
from contextlib import asynccontextmanager

from sgr_deep_research import settings
from sgr_deep_research.services.mcp_service import MCP2ToolConverter


@pytest.fixture()
def test_config_path(tmp_path: Path) -> Path:
    config_content = textwrap.dedent(
        f"""
        openai:
          api_key: "test-openai-key"
          base_url: "https://api.openai.com/v1"
          model: "gpt-4o-mini"
          max_tokens: 100
          temperature: 0
          proxy: ""
        tavily:
          api_key: "test-tavily-key"
          api_base_url: "https://api.tavily.com"
        execution:
          max_steps: 1
          reports_dir: "{tmp_path / "reports"}"
          logs_dir: "{tmp_path / "logs"}"
        mcp:
          context_limit: 15000
          transport_config: {{}}
        logging:
          config_file: "logging_config.yaml"
        """
    ).strip()

    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_content)
    return config_path


@pytest.fixture()
def test_app(monkeypatch: pytest.MonkeyPatch, test_config_path: Path):
    monkeypatch.setenv("APP_CONFIG", str(test_config_path))
    settings.get_config.cache_clear()
    MCP2ToolConverter._instances.clear()
    async def _noop_build_tools(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "sgr_deep_research.services.mcp_service.MCP2ToolConverter.build_tools_from_mcp",
        _noop_build_tools,
        raising=False,
    )

    import sgr_deep_research.api.endpoints as endpoints

    endpoints.agents_storage.clear()

    import sgr_deep_research.__main__ as main

    importlib.reload(main)
    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    main.app.router.lifespan_context = _noop_lifespan
    return main.app
