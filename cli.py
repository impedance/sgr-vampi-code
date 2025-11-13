"""
CLI client for SGR Vampi Code Agent.

Real-time streaming display with live panel updates.
"""

import json
import os
import sys
from typing import Any

import typer
from openai import OpenAI
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

# Initialize
app = typer.Typer()
console = Console()

# OpenAI client
client = OpenAI(
    api_key="dummy",
    base_url="http://localhost:8010/v1"
)


def print_banner():
    """Display centered startup banner."""
    banner = """
[bold cyan]╔══════════════════════════════════════════════════════════════════════╗[/bold cyan]
[bold cyan]║                                                                      ║[/bold cyan]
[bold cyan]║[/bold cyan]              [bold white]🤖  SGR Vampi Code - AI Coding Assistant[/bold white]              [bold cyan]║[/bold cyan]
[bold cyan]║                                                                      ║[/bold cyan]
[bold cyan]║[/bold cyan]      [white]Type your coding tasks, ask questions, or request analysis[/white]      [bold cyan]║[/bold cyan]
[bold cyan]║                                                                      ║[/bold cyan]
[bold cyan]║[/bold cyan]      [bold yellow]Commands:[/bold yellow] [bold red]/exit[/bold red] - quit  [bold green]/clear[/bold green] - clear  [bold blue]/help[/bold blue] - help      [bold cyan]║[/bold cyan]
[bold cyan]║                                                                      ║[/bold cyan]
[bold cyan]╚══════════════════════════════════════════════════════════════════════╝[/bold cyan]
"""
    console.print(Align.center(banner))


class RealtimeStreamHandler:
    """Handle streaming with real-time panel updates."""

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.debug_file = None
        
        # Buffers
        self.tools = {}  # {tool_id: {name, buffer, live_display}}
        self.content_buffer = ""
        
        # Live display references
        self.current_live = None
        self.reasoning_complete = False

    def _log(self, msg: str):
        """Debug logging."""
        if self.debug and self.debug_file:
            self.debug_file.write(msg + "\n")
            self.debug_file.flush()

    def _create_reasoning_panel(self, json_buffer: str) -> Panel:
        """Create reasoning panel from partial/complete JSON."""
        # Try to parse what we have
        data = {}
        try:
            data = json.loads(json_buffer)
        except json.JSONDecodeError:
            # Partial JSON - try to extract what we can
            # Show the raw buffer as "loading"
            return Panel(
                f"[dim]🤔 Reasoning in progress...\n\n{json_buffer[:200]}...[/dim]",
                title="[bold yellow]🤖 Agent Reasoning[/bold yellow]",
                border_style="yellow",
                padding=(1, 2),
            )
        
        # We have valid JSON - display it properly
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("", style="bold yellow", width=20)
        table.add_column("", style="white")

        steps = data.get("reasoning_steps", [])
        if steps:
            table.add_row("🧠 Reasoning:", "")
            for i, step in enumerate(steps, 1):
                table.add_row("", f"  {i}. {step}")
            table.add_row("", "")

        situation = data.get("current_situation", "")
        if situation:
            table.add_row("📊 Situation:", situation)
            table.add_row("", "")

        plan = data.get("plan_status", "")
        if plan:
            table.add_row("📋 Plan:", plan)
            table.add_row("", "")

        enough = data.get("enough_data")
        if enough is not None:
            table.add_row("✅ Data Ready:", "Yes" if enough else "No")
            table.add_row("", "")

        next_steps = data.get("remaining_steps", [])
        if next_steps:
            table.add_row("➡️  Next Steps:", "")
            for i, step in enumerate(next_steps, 1):
                table.add_row("", f"  {i}. {step}")
            table.add_row("", "")

        done = data.get("task_completed")
        if done is not None:
            table.add_row("🏁 Completed:", "✓ Yes" if done else "○ No")

        return Panel(
            table,
            title="[bold yellow]🤖 Agent Reasoning[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        )

    def _create_answer_panel(self, json_buffer: str) -> Panel:
        """Create answer panel from partial/complete JSON."""
        data = {}
        try:
            data = json.loads(json_buffer)
        except json.JSONDecodeError:
            return Panel(
                f"[dim]💬 Answer loading...\n\n{json_buffer[:150]}...[/dim]",
                title="[bold cyan]💬 Answer[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
        
        parts = []
        
        reasoning = data.get("reasoning", "")
        if reasoning:
            parts.append(f"[dim italic]💭 {reasoning}[/dim italic]")
            parts.append("")
        
        steps = data.get("completed_steps", [])
        if steps:
            parts.append("[green]✓ Completed:[/green]")
            for step in steps:
                parts.append(f"  [dim]• {step}[/dim]")
            parts.append("")
        
        answer = data.get("answer", "")
        if answer:
            parts.append(answer)
        
        return Panel(
            "\n".join(parts) if parts else "[dim]Processing...[/dim]",
            title="[bold cyan]💬 Answer[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )

    def _update_tool_display(self, tool_id: str, live: Live):
        """Update the live display for a tool."""
        tool = self.tools[tool_id]
        name = tool["name"]
        buffer = tool["buffer"]
        
        if name == "reasoningtool":
            panel = self._create_reasoning_panel(buffer)
            live.update(panel)
        elif name == "finalanswertool":
            panel = self._create_answer_panel(buffer)
            live.update(panel)

    def stream(self, model: str, messages: list) -> tuple[str, list | None, str | None]:
        """Stream with real-time updates."""
        
        # Debug setup
        if self.debug:
            import datetime
            filename = f"debug_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            self.debug_file = open(filename, "w", encoding="utf-8")
            console.print(f"[dim]📝 Debug: {filename}[/dim]\n")
        
        # Start streaming
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            temperature=0.3,
        )

        agent_id = None
        chunk_num = 0
        clarifications = None
        
        for chunk in response:
            chunk_num += 1
            self._log(f"\n{'='*60}\nCHUNK #{chunk_num}\n{'='*60}\n{chunk}")
            
            # Extract agent ID
            if hasattr(chunk, "model") and chunk.model and "_" in chunk.model:
                if not agent_id:
                    agent_id = chunk.model
            
            # Get delta
            if not hasattr(chunk, "choices") or not chunk.choices:
                continue
            
            delta = chunk.choices[0].delta
            if not delta:
                continue
            
            # === HANDLE TOOL CALLS ===
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    if not tc.function:
                        continue
                    
                    tool_id = tc.id if tc.id else f"idx_{tc.index}"
                    
                    # Initialize tool
                    if tool_id not in self.tools:
                        self.tools[tool_id] = {
                            "name": "",
                            "buffer": "",
                            "live": None,
                            "completed": False
                        }
                    
                    tool = self.tools[tool_id]
                    
                    # Update name
                    if tc.function.name:
                        tool["name"] = tc.function.name
                        self._log(f"Tool: {tool['name']}")
                    
                    # Accumulate arguments - THIS IS THE KEY PART
                    if tc.function.arguments:
                        tool["buffer"] += tc.function.arguments
                        self._log(f"  Buffer now: {len(tool['buffer'])} chars")
                        
                        # === REAL-TIME UPDATE ===
                        name = tool["name"]
                        
                        # Start live display if needed
                        if name in ["reasoningtool", "finalanswertool"]:
                            if tool["live"] is None:
                                # Create new Live display
                                tool["live"] = Live(console=console, auto_refresh=False)
                                tool["live"].start()
                            
                            # Update display with current buffer
                            self._update_tool_display(tool_id, tool["live"])
                            tool["live"].refresh()
                        
                        # Check if JSON is complete
                        try:
                            data = json.loads(tool["buffer"])
                            if not tool["completed"]:
                                self._log(f"  ✓ JSON complete for {name}")
                                tool["completed"] = True
                                
                                # Stop live and print final version
                                if tool["live"]:
                                    tool["live"].stop()
                                    tool["live"] = None
                                
                                # Print final clean version
                                if name == "reasoningtool":
                                    console.print(self._create_reasoning_panel(tool["buffer"]))
                                    console.print()
                                    self.reasoning_complete = True
                                elif name == "finalanswertool":
                                    console.print(self._create_answer_panel(tool["buffer"]))
                                    console.print()
                                elif name == "clarificationtool":
                                    clarifications = data.get("questions", [])
                        
                        except json.JSONDecodeError:
                            # Still accumulating
                            pass
            
            # === HANDLE CONTENT ===
            if hasattr(delta, "content") and delta.content:
                text = delta.content
                self.content_buffer += text
                
                # Stream text directly (non-JSON)
                if not text.strip().startswith("{") and not text.strip().startswith("}"):
                    console.print(text, end="", style="white")
                    sys.stdout.flush()
        
        # Cleanup any remaining live displays
        for tool in self.tools.values():
            if tool["live"]:
                tool["live"].stop()
        
        # Debug close
        if self.debug and self.debug_file:
            self._log(f"\n{'='*60}\nEND - {chunk_num} chunks\n{'='*60}")
            self.debug_file.close()
            console.print(f"\n[dim]✅ Debug saved ({chunk_num} chunks)[/dim]\n")
        
        return self.content_buffer, clarifications, agent_id


@app.command()
def chat(
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging"),
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace path for the agent")
):
    """
    Start interactive chat with the coding agent.
    """
    print_banner()
    workspace_path = os.path.abspath(workspace)
    console.print(f"[dim]Workspace: {workspace_path}[/dim]\n")
    
    # State
    current_model = "sgr_tool_calling_agent"
    history = []
    
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
[bold cyan]Commands:[/bold cyan]
  /exit, /quit, /q   - Exit
  /clear, /cls       - Clear screen
  /help, /h          - Show help

[bold cyan]Tips:[/bold cyan]
  • Ask coding questions
  • Request code reviews
  • Explore the codebase
  • Request modifications
""")
            continue
        
        if not user_input.strip():
            continue
        
        # Add to history
        history.append({"role": "user", "content": user_input})
        
        # Stream response
        console.print("\n[bold green]Agent[/bold green]:\n")
        
        try:
            handler = RealtimeStreamHandler(debug=debug)
            content, clarifications, agent_id = handler.stream(current_model, history)
            
            # Update model for continuous conversation
            if agent_id:
                current_model = agent_id
            
            # Handle clarifications
            if clarifications:
                console.print("\n[bold yellow]❓ Questions:[/bold yellow]")
                for i, q in enumerate(clarifications, 1):
                    console.print(f"  {i}. {q}")
            
            # Add to history
            history.append({"role": "assistant", "content": content})
        
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            if debug:
                import traceback
                console.print(f"[dim]{traceback.format_exc()}[/dim]")
            history.pop()


@app.command()
def task(
    prompt: str = typer.Argument(..., help="Task to execute"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug logging"),
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace path for the agent")
):
    """
    Execute a single task and exit.
    """
    workspace_path = os.path.abspath(workspace)
    console.print(f"[bold cyan]Task:[/bold cyan] {prompt}\n")
    console.print(f"[dim]Workspace: {workspace_path}[/dim]\n")
    console.print("[bold green]Agent:[/bold green]\n")
    
    try:
        handler = RealtimeStreamHandler(debug=debug)
        content, clarifications, _ = handler.stream(
            "sgr_tool_calling_agent",
            [{"role": "user", "content": prompt}]
        )
        
        if clarifications:
            console.print("\n[bold yellow]❓ Questions:[/bold yellow]")
            for i, q in enumerate(clarifications, 1):
                console.print(f"  {i}. {q}")
            console.print("\n[dim]Use 'chat' mode to continue.[/dim]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if debug:
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
