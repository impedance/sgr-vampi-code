"""Coding tools for repository operations using OS-level commands."""

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field

from sgr_deep_research.core.tools.base import BaseTool

if TYPE_CHECKING:
    from sgr_deep_research.core.models import ResearchContext

logger = logging.getLogger(__name__)


class ReadFileTool(BaseTool):
    """Read file contents from the repository.
    
    Use this tool to read source code files, configuration files, or any text-based files.
    """

    file_path: str = Field(description="Relative or absolute path to the file to read")
    start_line: int | None = Field(default=None, description="Optional starting line number (1-indexed)")
    end_line: int | None = Field(default=None, description="Optional ending line number (1-indexed)")

    async def __call__(self, context: "ResearchContext") -> str:
        try:
            path = Path(self.file_path).expanduser().resolve()
            
            if not path.exists():
                return f"Error: File not found: {self.file_path}"
            
            if not path.is_file():
                return f"Error: Path is not a file: {self.file_path}"
            
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            
            if self.start_line is not None or self.end_line is not None:
                start = (self.start_line or 1) - 1
                end = (self.end_line or total_lines)
                lines = lines[start:end]
                result_lines = [f"{i + start + 1}|{line.rstrip()}" for i, line in enumerate(lines)]
            else:
                result_lines = [f"{i + 1}|{line.rstrip()}" for i, line in enumerate(lines)]
            
            return f"File: {self.file_path}\nTotal lines: {total_lines}\n\n" + "\n".join(result_lines)
            
        except Exception as e:
            logger.error(f"Error reading file {self.file_path}: {e}")
            return f"Error reading file: {str(e)}"


class WriteFileTool(BaseTool):
    """Write or create a file in the repository.
    
    Use this tool to create new files or completely overwrite existing files.
    """

    file_path: str = Field(description="Relative or absolute path to the file to write")
    content: str = Field(description="Complete content to write to the file")
    create_dirs: bool = Field(default=True, description="Create parent directories if they don't exist")

    async def __call__(self, context: "ResearchContext") -> str:
        try:
            path = Path(self.file_path).expanduser().resolve()
            
            if self.create_dirs:
                path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.content)
            
            lines_count = len(self.content.splitlines())
            return f"Successfully wrote {lines_count} lines to {self.file_path}"
            
        except Exception as e:
            logger.error(f"Error writing file {self.file_path}: {e}")
            return f"Error writing file: {str(e)}"


class EditFileTool(BaseTool):
    """Edit specific lines in an existing file using search and replace.
    
    Use this tool to make targeted edits to existing files.
    """

    file_path: str = Field(description="Relative or absolute path to the file to edit")
    search_text: str = Field(description="Exact text to search for (must be unique in the file)")
    replace_text: str = Field(description="Text to replace the search text with")

    async def __call__(self, context: "ResearchContext") -> str:
        try:
            path = Path(self.file_path).expanduser().resolve()
            
            if not path.exists():
                return f"Error: File not found: {self.file_path}"
            
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if self.search_text not in content:
                return f"Error: Search text not found in {self.file_path}"
            
            count = content.count(self.search_text)
            if count > 1:
                return f"Error: Search text appears {count} times in {self.file_path}. Please make search text more specific."
            
            new_content = content.replace(self.search_text, self.replace_text, 1)
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            return f"Successfully edited {self.file_path}"
            
        except Exception as e:
            logger.error(f"Error editing file {self.file_path}: {e}")
            return f"Error editing file: {str(e)}"


class GrepTool(BaseTool):
    """Search for patterns in files using grep.
    
    Use this tool to find text patterns across files in the repository.
    """

    pattern: str = Field(description="Search pattern (supports regex)")
    path: str = Field(default=".", description="Directory or file to search in")
    case_insensitive: bool = Field(default=False, description="Perform case-insensitive search")
    file_pattern: str | None = Field(default=None, description="File pattern to filter (e.g., '*.py')")
    context_lines: int = Field(default=0, description="Number of context lines to show before/after match")
    max_results: int = Field(default=100, description="Maximum number of results to return")

    async def __call__(self, context: "ResearchContext") -> str:
        try:
            cmd = ["grep", "-r", "-n"]
            
            if self.case_insensitive:
                cmd.append("-i")
            
            if self.context_lines > 0:
                cmd.extend(["-C", str(self.context_lines)])
            
            if self.file_pattern:
                cmd.extend(["--include", self.file_pattern])
            
            cmd.append(self.pattern)
            cmd.append(self.path)
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0 and process.returncode != 1:
                return f"Error running grep: {stderr.decode()}"
            
            output = stdout.decode()
            
            if not output:
                return f"No matches found for pattern: {self.pattern}"
            
            lines = output.splitlines()
            if len(lines) > self.max_results:
                lines = lines[:self.max_results]
                result = "\n".join(lines) + f"\n\n... (truncated, showing first {self.max_results} results)"
            else:
                result = "\n".join(lines)
            
            return f"Search results for '{self.pattern}':\n\n{result}"
            
        except Exception as e:
            logger.error(f"Error running grep: {e}")
            return f"Error running grep: {str(e)}"


class RunCommandTool(BaseTool):
    """Execute a shell command in the repository.
    
    Use this tool to run terminal commands like git, build tools, linters, tests, etc.
    Be careful with destructive commands.
    """

    command: str = Field(description="Shell command to execute")
    working_dir: str = Field(default=".", description="Working directory for command execution")
    timeout: int = Field(default=30, description="Timeout in seconds")

    async def __call__(self, context: "ResearchContext") -> str:
        try:
            process = await asyncio.create_subprocess_shell(
                self.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return f"Error: Command timed out after {self.timeout} seconds"
            
            output = stdout.decode()
            error = stderr.decode()
            
            result = f"Command: {self.command}\n"
            result += f"Exit code: {process.returncode}\n\n"
            
            if output:
                result += f"STDOUT:\n{output}\n"
            
            if error:
                result += f"STDERR:\n{error}\n"
            
            if not output and not error:
                result += "(no output)"
            
            return result
            
        except Exception as e:
            logger.error(f"Error running command: {e}")
            return f"Error running command: {str(e)}"


class ListDirectoryTool(BaseTool):
    """List contents of a directory.
    
    Use this tool to explore directory structure and find files.
    Automatically excludes common build/dependency directories like .venv, node_modules, .git, etc.
    """

    path: str = Field(default=".", description="Directory path to list")
    recursive: bool = Field(default=False, description="List recursively")
    max_depth: int = Field(default=3, description="Maximum recursion depth (if recursive=True)")
    show_hidden: bool = Field(default=False, description="Show hidden files/directories")
    max_items: int = Field(default=500, description="Maximum number of items to show (to prevent context overflow)")
    
    # Directories to always skip (even if show_hidden=True)
    IGNORED_DIRS: ClassVar[set[str]] = {
        '.venv', 'venv', '.env', 'env',
        'node_modules', 'bower_components',
        '.git', '.svn', '.hg',
        '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
        '.tox', '.nox', '.eggs', '*.egg-info',
        'dist', 'build', '.dist-info',
        '.idea', '.vscode', '.vs',
        'coverage', '.coverage', 'htmlcov',
        '.DS_Store', 'Thumbs.db',
    }

    async def __call__(self, context: "ResearchContext") -> str:
        try:
            path = Path(self.path).expanduser().resolve()
            
            if not path.exists():
                return f"Error: Directory not found: {self.path}"
            
            if not path.is_dir():
                return f"Error: Path is not a directory: {self.path}"
            
            result = f"Contents of {self.path}:\n\n"
            
            def should_skip(name: str) -> bool:
                """Check if directory/file should be skipped."""
                # Skip hidden files/dirs if show_hidden=False
                if not self.show_hidden and name.startswith("."):
                    return True
                # Always skip ignored directories
                if name in self.IGNORED_DIRS:
                    return True
                # Skip egg-info directories
                if name.endswith('.egg-info'):
                    return True
                return False
            
            if self.recursive:
                items = []
                truncated = False
                for root, dirs, files in os.walk(path):
                    # Filter out ignored directories in-place
                    dirs[:] = [d for d in dirs if not should_skip(d)]
                    
                    level = root.replace(str(path), "").count(os.sep)
                    if level >= self.max_depth:
                        dirs.clear()
                        continue
                    
                    indent = "  " * level
                    rel_root = os.path.relpath(root, path)
                    if rel_root != ".":
                        if len(items) >= self.max_items:
                            truncated = True
                            break
                        items.append(f"{indent}{os.path.basename(root)}/")
                    
                    for file in sorted(files):
                        if should_skip(file):
                            continue
                        if len(items) >= self.max_items:
                            truncated = True
                            break
                        items.append(f"{indent}  {file}")
                    
                    if truncated:
                        break
                
                result += "\n".join(items)
                if truncated:
                    result += f"\n\n... (truncated, showing first {self.max_items} items)"
            else:
                items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
                lines = []
                for item in items:
                    if should_skip(item.name):
                        continue
                    
                    if item.is_dir():
                        lines.append(f"  {item.name}/")
                    else:
                        size = item.stat().st_size
                        lines.append(f"  {item.name} ({size} bytes)")
                
                result += "\n".join(lines)
            
            return result
            
        except Exception as e:
            logger.error(f"Error listing directory: {e}")
            return f"Error listing directory: {str(e)}"


class FindFilesTool(BaseTool):
    """Find files by name pattern in the repository.
    
    Use this tool to locate files matching a pattern.
    """

    pattern: str = Field(description="File name pattern (supports wildcards like *.py)")
    path: str = Field(default=".", description="Directory to search in")
    max_results: int = Field(default=100, description="Maximum number of results")

    async def __call__(self, context: "ResearchContext") -> str:
        try:
            cmd = ["find", self.path, "-type", "f", "-name", self.pattern]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return f"Error running find: {stderr.decode()}"
            
            output = stdout.decode().strip()
            
            if not output:
                return f"No files found matching pattern: {self.pattern}"
            
            files = output.splitlines()
            
            if len(files) > self.max_results:
                files = files[:self.max_results]
                result = "\n".join(files) + f"\n\n... (truncated, showing first {self.max_results} results)"
            else:
                result = "\n".join(files)
            
            return f"Files matching '{self.pattern}':\n\n{result}"
            
        except Exception as e:
            logger.error(f"Error finding files: {e}")
            return f"Error finding files: {str(e)}"


# Coding agent tools collection
coding_agent_tools = [
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    GrepTool,
    RunCommandTool,
    ListDirectoryTool,
    FindFilesTool,
]

