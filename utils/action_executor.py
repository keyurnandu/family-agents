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
    """Extract EXEC: tagged blocks from an agent response."""
    actions: list[Action] = []

    # Match EXEC:file:<path> or EXEC:bash blocks (with or without ``` fences)
    pattern = re.compile(
        r"EXEC:(file:([^\n]+)|bash)\s*\n"   # tag line
        r"(?:```[a-z]*\n)?"                  # optional opening fence
        r"(.*?)"                             # content (non-greedy)
        r"(?:```\s*\n?|(?=EXEC:|$))",        # closing fence OR next block
        re.DOTALL | re.IGNORECASE,
    )

    for match in pattern.finditer(response_text):
        full_tag = match.group(1)   # "file:src/app.py" or "bash"
        file_path = match.group(2)  # only set for file actions
        content = match.group(3).strip()

        if not content:
            continue

        if file_path:
            actions.append(
                Action(
                    kind="file",
                    label=file_path.strip(),
                    content=content,
                    agent_name=agent_name,
                )
            )
        else:
            # Use first line as the label for display
            label = content.splitlines()[0][:80]
            actions.append(
                Action(
                    kind="bash",
                    label=label,
                    content=content,
                    agent_name=agent_name,
                )
            )

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
                    text=True,
                    encoding="utf-8",
                    errors="replace",
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
