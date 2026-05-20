"""
Parses agent responses for executable actions (file writes, shell commands)
and prompts the user for permission before running them.

Agents signal an action by wrapping content in a tagged code block:

    EXEC:file:path/to/file.py
    ```
    <file content>
    ```

    EXEC:bash
    ```
    npm install && npm run build
    ```

File changes are collected and shown as a compact summary — one "apply all?"
prompt for the whole batch. Bash commands are confirmed individually.
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
from rich.table import Table

console = Console()


@dataclass
class Action:
    kind: Literal["file", "bash"]
    label: str       # file path or command summary
    content: str     # file content or bash script
    agent_name: str


def parse_actions(response_text: str, agent_name: str) -> list[Action]:
    """Extract EXEC: tagged blocks from an agent response."""
    actions: list[Action] = []

    chunks = re.split(r"(?=EXEC:(?:file:|bash))", response_text, flags=re.IGNORECASE)

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.upper().startswith("EXEC:"):
            continue

        file_match = re.match(
            r"EXEC:file:([^\n]+)\n"
            r"```[^\n]*\n"
            r"(.*?)"
            r"```",
            chunk,
            re.IGNORECASE | re.DOTALL,
        )
        if file_match:
            path = file_match.group(1).strip()
            content = file_match.group(2).strip()
            if content:
                actions.append(Action(kind="file", label=path, content=content, agent_name=agent_name))
            continue

        bash_match = re.match(
            r"EXEC:bash\s*\n"
            r"```[^\n]*\n"
            r"(.*?)"
            r"```",
            chunk,
            re.IGNORECASE | re.DOTALL,
        )
        if bash_match:
            content = bash_match.group(1).strip()
            if content:
                lines = content.splitlines()
                label = (lines[0] if lines else "shell command")[:80]
                actions.append(Action(kind="bash", label=label, content=content, agent_name=agent_name))

    return actions


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
    File changes: show a compact summary, one 'apply all?' prompt.
    Bash commands: confirmed individually (higher risk).
    Returns outcome strings fed back to the agent pipeline.
    """
    if not actions:
        return []

    outcomes: list[str] = []
    file_actions = [a for a in actions if a.kind == "file"]
    bash_actions  = [a for a in actions if a.kind == "bash"]

    # ── File changes — one collective prompt ─────────────────────────
    if file_actions:
        console.print()

        # Which agents are involved
        agents_involved = sorted({a.agent_name for a in file_actions})
        agent_str = " & ".join(f"[bold yellow]{n}[/bold yellow]" for n in agents_involved)
        n = len(file_actions)
        console.print(
            f"{agent_str} want{'s' if len(agents_involved) == 1 else ''} to write "
            f"[bold]{n}[/bold] file{'s' if n > 1 else ''} to [cyan]{project_dir}[/cyan]:"
        )

        # Compact file table
        table = Table(show_header=False, box=None, padding=(0, 1, 0, 0))
        table.add_column("icon", style="dim", no_wrap=True)
        table.add_column("path", style="cyan", no_wrap=True)
        table.add_column("info", style="dim")
        for a in file_actions:
            lines = a.content.splitlines()
            preview = lines[0][:55].strip() if lines else ""
            if len(lines[0]) > 55 if lines else False:
                preview += "…"
            table.add_row("✏", a.label, f"{len(lines)} lines  {preview}")
        console.print(table)

        approved = Confirm.ask(
            f"\n  Apply {'all ' if n > 1 else ''}{'change' if n == 1 else 'changes'}?",
            default=False,
        )

        if approved:
            console.print()
            for a in file_actions:
                dest = (project_dir / a.label).resolve()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(a.content, encoding="utf-8")
                console.print(f"  [green]✓[/green]  {a.label}")
                outcomes.append(f"FILE WRITTEN: {a.label}")
            console.print()
        else:
            console.print("  [dim]Changes skipped.[/dim]\n")
            for a in file_actions:
                outcomes.append(f"FILE SKIPPED: {a.label}")

    # ── Bash commands — individual prompts ───────────────────────────
    for action in bash_actions:
        console.print()
        console.print(f"[bold yellow]{action.agent_name}[/bold yellow] wants to run:")
        _show_bash_action(action)
        approved = Confirm.ask("  Allow?", default=False)

        if approved:
            console.print("  [dim]Running…[/dim]")
            result = subprocess.run(
                action.content,
                shell=True,
                cwd=project_dir,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            if result.returncode == 0:
                console.print("  [green]✓ Done.[/green]")
                outcomes.append(f"BASH OK: {action.label}")
            else:
                console.print(f"  [red]✗ Exited {result.returncode}[/red]")
                outcomes.append(f"BASH FAILED (exit {result.returncode}): {action.label}")
        else:
            console.print("  [dim]Skipped.[/dim]")
            outcomes.append(f"BASH SKIPPED: {action.label}")

    return outcomes
