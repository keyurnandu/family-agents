"""
Parses agent responses for executable actions (file writes, shell commands)
and prompts the user for permission before running them — mirrors Claude Code's
"May I run this?" UX.

Agents signal an action by wrapping content in a tagged code block:

    EXEC:file:path/to/file.py
    ```
    <file content>
    ```

    EXEC:bash
    ```
    npm install && npm run build
    ```
"""
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax

console = Console()


@dataclass
class Action:
    kind: Literal["file", "bash"]
    label: str       # file path or command summary
    content: str     # file content or bash script
    agent_name: str


def parse_actions(response_text: str, agent_name: str) -> list[Action]:
    """Extract EXEC: tagged blocks from an agent response.

    Supports two formats:

        EXEC:file:path/to/file.py        EXEC:bash
        ```[lang]                         ```
        <content>                         <commands>
        ```                               ```
    """
    actions: list[Action] = []

    # Split on EXEC: boundaries so each chunk starts with a tag
    chunks = re.split(r"(?=EXEC:(?:file:|bash))", response_text, flags=re.IGNORECASE)

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.upper().startswith("EXEC:"):
            continue

        # --- EXEC:file:<path> ---
        file_match = re.match(
            r"EXEC:file:([^\n]+)\n"       # tag + path
            r"```[^\n]*\n"                # opening fence (``` or ```python etc.)
            r"(.*?)"                      # content
            r"```",                       # closing fence
            chunk,
            re.IGNORECASE | re.DOTALL,
        )
        if file_match:
            path = file_match.group(1).strip()
            content = file_match.group(2).strip()
            if content:
                actions.append(Action(kind="file", label=path, content=content, agent_name=agent_name))
            continue

        # --- EXEC:bash ---
        bash_match = re.match(
            r"EXEC:bash\s*\n"             # tag
            r"```[^\n]*\n"                # opening fence
            r"(.*?)"                      # commands
            r"```",                       # closing fence
            chunk,
            re.IGNORECASE | re.DOTALL,
        )
        if bash_match:
            content = bash_match.group(1).strip()
            if content:
                label = content.splitlines()[0][:80]
                actions.append(Action(kind="bash", label=label, content=content, agent_name=agent_name))

    return actions


def _show_file_action(action: Action):
    ext = Path(action.label).suffix.lstrip(".") or "text"
    syntax = Syntax(action.content, ext, theme="monokai", line_numbers=True)
    console.print(
        Panel(
            syntax,
            title=f"[bold]Create / overwrite[/bold]  [cyan]{action.label}[/cyan]",
            border_style="yellow",
        )
    )


def _show_bash_action(action: Action):
    syntax = Syntax(action.content, "bash", theme="monokai")
    console.print(
        Panel(
            syntax,
            title="[bold]Run command[/bold]",
            border_style="yellow",
        )
    )


def prompt_and_execute(actions: list[Action], project_dir: Path) -> list[str]:
    """
    Show each action to the user and ask for permission.
    Returns a list of outcome strings (shown back to the agent pipeline).
    """
    outcomes: list[str] = []

    for action in actions:
        console.print()
        agent_label = f"[bold yellow]{action.agent_name}[/bold yellow]"

        if action.kind == "file":
            console.print(
                f"{agent_label} wants to write  [cyan]{action.label}[/cyan]"
            )
            _show_file_action(action)
            approved = Confirm.ask("  Allow?", default=False)

            if approved:
                dest = project_dir / action.label
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(action.content, encoding="utf-8")
                console.print(f"  [green]✓ Written:[/green] {dest}")
                outcomes.append(f"FILE CREATED: {action.label}")
            else:
                console.print("  [dim]Skipped.[/dim]")
                outcomes.append(f"FILE SKIPPED: {action.label}")

        elif action.kind == "bash":
            console.print(f"{agent_label} wants to run a command")
            _show_bash_action(action)
            approved = Confirm.ask("  Allow?", default=False)

            if approved:
                console.print("  [dim]Running…[/dim]")
                result = subprocess.run(
                    action.content,
                    shell=True,
                    cwd=project_dir,
                    # inherit all streams so output/errors print live in the terminal
                    stdin=sys.stdin,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                )
                if result.returncode == 0:
                    console.print("  [green]✓ Command completed.[/green]")
                    outcomes.append(
                        f"BASH OK (exit 0): {action.label}"
                    )
                else:
                    console.print(
                        f"  [red]✗ Command exited with code {result.returncode}[/red]"
                    )
                    outcomes.append(
                        f"BASH FAILED (exit {result.returncode}): {action.label}"
                    )
            else:
                console.print("  [dim]Skipped.[/dim]")
                outcomes.append(f"BASH SKIPPED: {action.label}")

    return outcomes
