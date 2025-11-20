"""
CLI client with local agent execution and beautiful streaming output.

Usage:
    # Interactive chat with continuous conversation
    python cli_stream.py chat
    
    # Adjust typing speed
    python cli_stream.py chat --speed 0.005  # Slower
    python cli_stream.py chat --speed 0      # Instant
    
    # Single task
    python cli_stream.py task "Your question"
    
    # Fast mode (no typing effect)
    python cli_stream.py fast "Your question"

Key features:
    - Local agent execution (no API calls)
    - Character-by-character JSON streaming
    - Syntax highlighting (keys, values, brackets)
    - Continuous conversation (history is preserved!)
    - Clean interface without panels
"""

import asyncio
import datetime
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from sgr_deep_research.core.agents.sgr_vampi_code_agent import SGRVampiCodeAgent
from sgr_deep_research.core.models import AgentStatesEnum
from sgr_deep_research.settings import get_config

# Initialize
app = typer.Typer()
console = Console()
config = get_config()


def log_cli_error(message: str, exc: Exception | None = None):
    """Append CLI errors to a dedicated log file without spamming console."""
    logs_dir = Path(config.execution.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "cli_stream_errors.log"
    lines = [f"{datetime.datetime.now().isoformat()} - {message}"]
    if exc is not None:
        lines.append(f"{type(exc).__name__}: {exc}")
        tb = traceback.format_exc()
        if tb.strip():
            lines.append(tb)
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def print_banner():
    """Display centered startup banner using Rich components."""
    
    # Создаём таблицу для содержимого
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="center", style="bold white")
    
    # ASCII кот-вампир
    vampire_cat = Text()
    vampire_cat.append("    ╱|、\n", style="bold magenta")
    vampire_cat.append("  (˚ˎ 。7\n", style="bold magenta")
    vampire_cat.append("   |、˜〵\n", style="bold magenta")
    vampire_cat.append("  じしˍ,)ノ", style="bold magenta")
    
    table.add_row(vampire_cat)
    table.add_row("")
    table.add_row(Text("🦇 SGR VAMPI CODE 🦇", style="bold white", justify="center"))
    table.add_row(Text("AI Coding Assistant with Streaming JSON", style="bold yellow"))
    table.add_row("")
    
    # Возможности
    features = Table.grid(padding=(0, 1))
    features.add_column(style="green bold", width=3)
    features.add_column(style="white")
    
    features.add_row("", Text("Возможности:", style="bold cyan"))
    features.add_row("✓", "Чтение и анализ кода в репозитории")
    features.add_row("✓", "Создание и редактирование файлов")
    features.add_row("✓", "Поиск по коду (grep, семантический поиск)")
    features.add_row("✓", "Рефакторинг и улучшение кода")
    features.add_row("✓", "Непрерывный диалог с сохранением контекста")
    features.add_row("✓", "Потоковый вывод с красивой подсветкой JSON")
    
    table.add_row(features)
    table.add_row("")
    
    # Команды
    commands = Table.grid(padding=(0, 1))
    commands.add_column(style="bold", width=15)
    commands.add_column(style="dim white")
    
    commands.add_row(Text("Команды:", style="bold yellow"), "")
    commands.add_row(Text("/exit, /quit", style="bold red"), "- Выйти из чата")
    commands.add_row(Text("/clear", style="bold green"), "- Очистить экран")
    commands.add_row(Text("/help", style="bold blue"), "- Показать справку")
    
    table.add_row(commands)
    table.add_row("")
    
    # Model info
    model_info = f"Режим: Локальный | Модель: {config.openai.model}"
    table.add_row(Text(model_info, style="dim"))
    
    # Server info
    server_info = f"Сервер: {config.openai.base_url} | Агент: SGR Vampi Code"
    table.add_row(Text(server_info, style="dim"))
    
    # Оборачиваем в Panel
    panel = Panel(
        table,
        border_style="bold red",
        padding=(1, 2),
        expand=False
    )
    
    console.print(panel, justify="center")


class JSONStreamPrinter:
    """Beautiful JSON streaming printer with typing effect."""

    def __init__(self, typing_speed: float = 0.001):
        self.typing_speed = typing_speed
        self.json_buffer = ""
        self.tool_name = ""
        self.current_indent = 0

    def _get_color_for_tool(self, tool_name: str) -> str:
        """Get color based on tool name."""
        color_map = {
            "reasoningtool": "yellow",
            "finalanswertool": "cyan",
            "clarificationtool": "magenta",
            "codesearchtool": "green",
            "codewritetool": "blue",
            "default": "white"
        }
        return color_map.get(tool_name.lower(), color_map["default"])

    def _colorize_json_char(self, char: str, context: str) -> Text:
        """Colorize individual JSON character based on context."""
        text = Text()
        
        # Determine color based on character and context
        if char in '{}':
            text.append(char, style="bold cyan")
        elif char in '[]':
            text.append(char, style="bold magenta")
        elif char in '":,':
            text.append(char, style="dim white")
        elif char.isdigit():
            text.append(char, style="yellow")
        elif context == "key":
            text.append(char, style="bold green")
        elif context == "string":
            text.append(char, style="white")
        else:
            text.append(char, style="white")
        
        return text

    def _detect_context(self, buffer: str, pos: int) -> str:
        """Detect if we're in a key, value, string, etc."""
        # Simple heuristic: count quotes before this position
        before = buffer[:pos]
        quote_count = before.count('"') - before.count('\\"')
        
        if quote_count % 2 == 1:  # Inside quotes
            # Check if it's after a colon (value) or not (key)
            last_colon = before.rfind(':')
            last_quote = before.rfind('"')
            if last_colon > last_quote:
                return "string"
            else:
                return "key"
        return "other"

    def print_tool_header(self, tool_name: str):
        """Print tool name header."""
        self.tool_name = tool_name
        color = self._get_color_for_tool(tool_name)
        
        console.print()
        console.print(f"[bold {color}]╭─── {tool_name.upper()} ───╮[/bold {color}]")
        console.print()

    def stream_char(self, char: str):
        """Stream a single character with typing effect."""
        self.json_buffer += char
        pos = len(self.json_buffer) - 1
        context = self._detect_context(self.json_buffer, pos)
        
        colored_char = self._colorize_json_char(char, context)
        console.print(colored_char, end="")
        
        # Flush to make it appear immediately
        sys.stdout.flush()
        
        # Typing effect delay
        if self.typing_speed > 0:
            time.sleep(self.typing_speed)

    def stream_chunk(self, chunk: str):
        """Stream a chunk of JSON."""
        for char in chunk:
            self.stream_char(char)

    def finalize_tool(self):
        """Finalize tool output."""
        console.print()
        
        # Try to parse and pretty print if complete
        try:
            data = json.loads(self.json_buffer)
            console.print()
            console.print("[dim]─── Parsed Result ───[/dim]")
            self._print_parsed_json(data)
        except json.JSONDecodeError:
            # Incomplete JSON, skip pretty print
            pass
        
        color = self._get_color_for_tool(self.tool_name)
        console.print(f"[bold {color}]╰─────────────────────╯[/bold {color}]")
        console.print()
        
        # Reset buffer
        self.json_buffer = ""

    def _print_parsed_json(self, data: Dict[str, Any], indent: int = 0):
        """Print parsed JSON in a readable format."""
        indent_str = "  " * indent
        
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    console.print(f"{indent_str}[bold green]{key}:[/bold green]")
                    self._print_parsed_json(value, indent + 1)
                elif isinstance(value, str) and len(value) > 80:
                    console.print(f"{indent_str}[bold green]{key}:[/bold green] [dim]{value[:80]}...[/dim]")
                else:
                    console.print(f"{indent_str}[bold green]{key}:[/bold green] {value}")
        elif isinstance(data, list):
            for i, item in enumerate(data, 1):
                if isinstance(item, (dict, list)):
                    console.print(f"{indent_str}[yellow]{i}.[/yellow]")
                    self._print_parsed_json(item, indent + 1)
                else:
                    console.print(f"{indent_str}[yellow]•[/yellow] {item}")


class LocalAgentStreamHandler:
    """Handle local agent execution with streaming output."""

    def __init__(self, typing_speed: float = 0.001, debug: bool = False):
        self.typing_speed = typing_speed
        self.debug = debug
        self.debug_file = None
        self.tools = {}  # {tool_id: {name, printer, buffer}}
        self.agent = None

    def _log(self, msg: str):
        """Debug logging."""
        if self.debug and self.debug_file:
            self.debug_file.write(msg + "\n")
            self.debug_file.flush()

    async def stream_agent(self, agent: SGRVampiCodeAgent) -> tuple[str, list | None, str]:
        """Stream agent execution with beautiful JSON output."""
        
        # Debug setup
        if self.debug:
            filename = f"debug_stream_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            self.debug_file = open(filename, "w", encoding="utf-8")
            console.print(f"[dim]📝 Debug: {filename}[/dim]\n")
        
        console.print(f"[dim]Agent: {agent.name}[/dim]")
        console.print(f"[dim]Session ID: ...{agent.id[-12:]}[/dim]")
        console.print()
        
        chunk_num = 0
        clarifications = None
        content_buffer = ""
        
        # Start agent execution in background
        agent_task = asyncio.create_task(agent.execute())
        
        # Stream output from agent's streaming generator
        try:
            async for chunk_data in agent.streaming_generator.stream():
                chunk_num += 1
                self._log(f"\n{'='*60}\nCHUNK #{chunk_num}\n{'='*60}\n{chunk_data}")
                
                # Parse SSE format: "data: {json}\n\n"
                if not chunk_data.startswith("data: "):
                    continue
                
                data_str = chunk_data[6:].strip()
                if data_str == "[DONE]":
                    break
                
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                
                # Extract delta from chunk
                if "choices" not in chunk or not chunk["choices"]:
                    continue
                
                choice = chunk["choices"][0]
                delta = choice.get("delta", {})
                
                # === HANDLE TOOL CALLS ===
                if "tool_calls" in delta and delta["tool_calls"]:
                    for tc in delta["tool_calls"]:
                        if "function" not in tc:
                            continue
                        
                        tool_id = tc.get("id", f"idx_{tc.get('index', 0)}")
                        
                        # Initialize tool
                        if tool_id not in self.tools:
                            self.tools[tool_id] = {
                                "name": "",
                                "printer": JSONStreamPrinter(typing_speed=self.typing_speed),
                                "buffer": "",
                                "completed": False,
                                "header_printed": False
                            }
                        
                        tool = self.tools[tool_id]
                        
                        # Update name
                        func = tc["function"]
                        if "name" in func and func["name"]:
                            tool["name"] = func["name"]
                            if not tool["header_printed"]:
                                tool["printer"].print_tool_header(tool["name"])
                                tool["header_printed"] = True
                            self._log(f"Tool: {tool['name']}")
                        
                        # Stream arguments character by character
                        if "arguments" in func and func["arguments"]:
                            args = func["arguments"]
                            tool["buffer"] = args  # Full arguments in one chunk
                            
                            # Stream each character
                            tool["printer"].stream_chunk(args)
                            
                            self._log(f"  Streamed: {len(args)} chars")
                            
                            # Check if JSON is complete
                            try:
                                data = json.loads(tool["buffer"])
                                if not tool["completed"]:
                                    self._log(f"  ✓ JSON complete for {tool['name']}")
                                    tool["completed"] = True
                                    
                                    # Finalize output
                                    tool["printer"].finalize_tool()
                                    
                                    # Handle clarifications
                                    if tool["name"].lower() == "clarificationtool":
                                        clarifications = data.get("questions", [])
                                    
                                    # Render FinalAnswerTool as Markdown
                                    if tool["name"].lower() == "finalanswertool" and "answer" in data:
                                        console.print("\n")
                                        console.print(Panel(
                                            Markdown(data["answer"]),
                                            title="📋 Ответ",
                                            border_style="green",
                                            padding=(1, 2)
                                        ))
                            
                            except json.JSONDecodeError:
                                # Still accumulating
                                pass
                
                # === HANDLE CONTENT ===
                if "content" in delta and delta["content"]:
                    text = delta["content"]
                    content_buffer += text
                    
                    # Only stream non-JSON text
                    stripped = text.strip()
                    if stripped and not stripped.startswith('{') and not stripped.startswith('}'):
                        console.print(text, end="", style="white")
                        sys.stdout.flush()
        
        except Exception as e:
            console.print(f"\n[red]Ошибка стриминга: {e}[/red]")
            console.print("[yellow]Подробности в logs/cli_stream_errors.log[/yellow]")
            log_cli_error("Streaming error", e)
        
        # Wait for agent to complete
        try:
            await agent_task
        except Exception as e:
            console.print(f"\n[red]Ошибка выполнения агента: {e}[/red]")
            console.print("[yellow]Подробности в logs/cli_stream_errors.log[/yellow]")
            log_cli_error("Agent execution error", e)
        
        # Debug close
        if self.debug and self.debug_file:
            self._log(f"\n{'='*60}\nEND - {chunk_num} chunks\n{'='*60}")
            self.debug_file.close()
            console.print(f"\n[dim]✅ Debug saved ({chunk_num} chunks)[/dim]\n")
        
        return content_buffer, clarifications, agent.name


@app.command()
def chat(
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging"),
    typing_speed: float = typer.Option(0.001, "--speed", "-s", help="Typing speed (seconds per char, 0 = instant)"),
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace path for the agent")
):
    """
    Start interactive chat with streaming JSON output using local agent.
    """
    print_banner()
    
    workspace_path = os.path.abspath(workspace)
    console.print(f"[dim]Workspace: {workspace_path}[/dim]\n")
    
    while True:
        # Get input
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]👋 Goodbye![/yellow]")
            break
        
        # Commands
        if user_input.lower() in ["/exit", "/quit", "/q"]:
            console.print("[yellow]👋 Goodbye![/yellow]")
            break
        
        if user_input.lower() in ["/clear", "/cls"]:
            os.system("clear" if os.name != "nt" else "cls")
            print_banner()
            continue
        
        if user_input.lower() in ["/help", "/h"]:
            console.print("""
[bold red]╔═══════════════════════════ СПРАВКА ════════════════════════════╗[/bold red]

[bold cyan]📝 Команды:[/bold cyan]
  [bold red]/exit[/bold red], [bold red]/quit[/bold red], [bold red]/q[/bold red]  - Выйти из чата
  [bold green]/clear[/bold green], [bold green]/cls[/bold green]       - Очистить экран
  [bold blue]/help[/bold blue], [bold blue]/h[/bold blue]           - Показать эту справку

[bold cyan]💎 Что умеет агент:[/bold cyan]
  [green]✓[/green] Читать файлы и анализировать код
  [green]✓[/green] Создавать и редактировать файлы
  [green]✓[/green] Искать по коду (grep, семантика)
  [green]✓[/green] Выполнять команды в терминале
  [green]✓[/green] Рефакторить и улучшать код
  [green]✓[/green] Отвечать на вопросы о кодовой базе

[bold cyan]🎯 Примеры запросов:[/bold cyan]
  • "Покажи структуру текущей директории"
  • "Найди все функции с TODO комментариями"
  • "Создай новый файл utils.py с функцией парсинга"
  • "Объясни, как работает класс StreamHandler"
  • "Исправь ошибки в файле main.py"

[bold cyan]⚙️  Настройки:[/bold cyan]
  Скорость печати: --speed 0.001 (быстрее: 0, медленнее: 0.01)
  Workspace: --workspace /path/to/project
  Отладка: --debug

[bold red]╚════════════════════════════════════════════════════════════════╝[/bold red]
""")
            continue
        
        if not user_input.strip():
            continue
        
        # Stream response
        console.print("\n[bold green]═══ Agent Response ═══[/bold green]\n")
        
        try:
            # Create new agent for each message
            # Each agent instance is independent and completes its task
            agent = SGRVampiCodeAgent(task=user_input, working_directory=workspace_path)
            handler = LocalAgentStreamHandler(typing_speed=typing_speed, debug=debug)
            content, clarifications, agent_name = asyncio.run(handler.stream_agent(agent))
            
            # Handle clarifications
            if clarifications:
                console.print("\n[bold yellow]❓ Questions:[/bold yellow]")
                for i, q in enumerate(clarifications, 1):
                    console.print(f"  {i}. {q}")
                
                # Get clarification response
                clarification_response = Prompt.ask("\n[bold cyan]Your answer[/bold cyan]")
                if clarification_response.strip():
                    asyncio.run(agent.provide_clarification(clarification_response))
                    handler = LocalAgentStreamHandler(typing_speed=typing_speed, debug=debug)
                    content, clarifications, agent_name = asyncio.run(handler.stream_agent(agent))
        
        except Exception as e:
            console.print(f"\n[red]Ошибка: {e}[/red]")
            console.print("[yellow]Подробности в logs/cli_stream_errors.log[/yellow]")
            log_cli_error("Chat mode error", e)


@app.command()
def task(
    prompt: str = typer.Argument(..., help="Task to execute"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging"),
    typing_speed: float = typer.Option(0.001, "--speed", "-s", help="Typing speed"),
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace path for the agent")
):
    """
    Execute a single task with streaming JSON output using local agent.
    """
    workspace_path = os.path.abspath(workspace)
    console.print(f"[bold cyan]Task:[/bold cyan] {prompt}\n")
    console.print(f"[dim]Workspace: {workspace_path}[/dim]\n")
    console.print("[bold green]═══ Agent Response ═══[/bold green]\n")
    
    try:
        agent = SGRVampiCodeAgent(task=prompt, working_directory=workspace_path)
        handler = LocalAgentStreamHandler(typing_speed=typing_speed, debug=debug)
        content, clarifications, _ = asyncio.run(handler.stream_agent(agent))
        
        if clarifications:
            console.print("\n[bold yellow]❓ Questions:[/bold yellow]")
            for i, q in enumerate(clarifications, 1):
                console.print(f"  {i}. {q}")
            console.print("\n[dim]Use 'chat' mode to continue.[/dim]")
    
    except Exception as e:
        console.print(f"[red]Ошибка: {e}[/red]")
        console.print("[yellow]Подробности в logs/cli_stream_errors.log[/yellow]")
        log_cli_error("Task mode error", e)
        raise typer.Exit(1)


@app.command()
def fast(
    prompt: str = typer.Argument(..., help="Task to execute"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging"),
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace path for the agent")
):
    """
    Execute task with instant output (no typing effect) using local agent.
    """
    workspace_path = os.path.abspath(workspace)
    console.print(f"[bold cyan]Task:[/bold cyan] {prompt}\n")
    console.print(f"[dim]Workspace: {workspace_path}[/dim]\n")
    console.print("[bold green]═══ Agent Response ═══[/bold green]\n")
    
    try:
        agent = SGRVampiCodeAgent(task=prompt, working_directory=workspace_path)
        handler = LocalAgentStreamHandler(typing_speed=0, debug=debug)
        content, clarifications, _ = asyncio.run(handler.stream_agent(agent))
        
        if clarifications:
            console.print("\n[bold yellow]❓ Questions:[/bold yellow]")
            for i, q in enumerate(clarifications, 1):
                console.print(f"  {i}. {q}")
    
    except Exception as e:
        console.print(f"[red]Ошибка: {e}[/red]")
        console.print("[yellow]Подробности в logs/cli_stream_errors.log[/yellow]")
        log_cli_error("Fast mode error", e)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
