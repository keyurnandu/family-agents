#!/usr/bin/env python3
"""
Tech Organization Agent System
Run: python cli.py [--project NAME]
"""

import re
import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

console = Console()
BASE_DIR = Path(__file__).parent


def _check_cli():
    if not shutil.which("claude"):
        console.print(
            "[bold red]Error:[/bold red] The [cyan]claude[/cyan] CLI is not installed or not in PATH.\n"
            "Install Claude Code from [link]https://claude.ai/code[/link] and log in once,\n"
            "then run this again — no API key needed."
        )
        sys.exit(1)


def _show_project_picker(projects: list) -> None:
    """Print the numbered project list."""
    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column("Num", style="bold cyan", no_wrap=True)
    table.add_column("Name", style="bold white", no_wrap=True)
    table.add_column("Info", style="dim")
    for i, p in enumerate(projects, 1):
        table.add_row(
            str(i),
            p["name"],
            f"{p['message_count']} msgs · {p['last_active']}",
        )
    console.print()
    console.rule("[bold]Your Projects[/bold]", style="cyan")
    console.print(table)
    console.rule(style="dim")


def _pick_project(db, display) -> str:
    """
    Interactive project picker shown on startup when no --project flag was given.

    - No saved projects  →  ask for a name (first-run experience)
    - Saved projects exist →  show numbered list; accept number, new name, or /command
    """
    while True:
        saved = db.list_projects()

        if not saved:
            # First run — keep it simple
            console.print("\n[dim]No projects yet. Give your first project a name to get started.[/dim]")
            prompt_text = "[bold cyan]Project name[/bold cyan]"
        else:
            _show_project_picker(saved)
            prompt_text = (
                "[bold cyan]Resume [dim][1"
                + (f"-{len(saved)}" if len(saved) > 1 else "")
                + "][/dim], new name, or [dim]/help[/dim][/bold cyan]"
            )

        raw = Prompt.ask(f"\n{prompt_text}").strip()

        # Empty input → re-prompt
        if not raw:
            continue

        # Slash commands
        if raw.startswith("/"):
            cmd = raw.lower()
            if cmd in ("/help", "/h"):
                display.show_help()
            elif cmd == "/list":
                pass  # loop will re-draw the list on next iteration
            elif cmd in ("/quit", "/exit", "/q"):
                console.print("[dim]Goodbye![/dim]")
                sys.exit(0)
            else:
                console.print(
                    f"[yellow]Unknown command:[/yellow] {raw}  "
                    "[dim]Available here: /help · /list · /quit[/dim]"
                )
            continue

        # Numeric selection → resume existing project
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(saved):
                return saved[idx]["name"]
            console.print(f"[yellow]Please enter a number between 1 and {len(saved)}.[/yellow]")
            continue

        # Anything else → treat as a new (or existing) project name
        # Reject obviously bad names
        if "/" in raw or "\\" in raw:
            console.print("[yellow]Project name can't contain slashes. Try again.[/yellow]")
            continue

        return raw


@click.command()
@click.option("--project", "-p", default=None, help="Project name to resume or create")
@click.option("--list", "list_projects", is_flag=True, help="List all saved projects")
@click.option("--model", "-m", default=None, help="Override the default model")
def main(project: str | None, list_projects: bool, model: str | None):
    """
    Tech Organization Agent System — your AI dev team in the terminal.

    Start a new project:   python cli.py
    Resume a project:      python cli.py --project my-app
    List projects:         python cli.py --list
    """
    _check_cli()

    # Late imports so the CLI check fires first
    from orchestrator import Orchestrator
    from utils.db_manager import DBManager
    from utils.display import Display

    db = DBManager(BASE_DIR / "db" / "conversations.db")
    display = Display()

    if list_projects:
        projects = db.list_projects()
        if not projects:
            console.print("\n[dim]No projects found. Start one with:[/dim]  python cli.py\n")
        else:
            console.print("\n[bold]Saved Projects[/bold]\n")
            for p in projects:
                desc = f"  [dim]{p.get('description', '')}[/dim]" if p.get("description") else ""
                console.print(
                    f"  [cyan]{p['name']}[/cyan]  "
                    f"[dim]{p['message_count']} messages · last active {p['last_active']}[/dim]"
                    f"{desc}"
                )
            console.print()
        return

    display.show_welcome()

    if not project:
        project = _pick_project(db, display)

    project_dir = BASE_DIR / "projects" / project
    project_dir.mkdir(parents=True, exist_ok=True)   # always visible immediately

    existing = db.get_project(project)
    if existing:
        console.print(
            f"\n[green]Resuming:[/green] [bold]{project}[/bold]  "
            f"[dim]({existing['message_count']} messages in history)[/dim]"
        )
    else:
        console.print(f"\n[green]Starting new project:[/green] [bold]{project}[/bold]")
        db.ensure_project(project)
    console.print(f"[dim]Project files will be written to:[/dim] [cyan]{project_dir}[/cyan]")

    orchestrator = Orchestrator(
        project_name=project,
        base_dir=BASE_DIR,
        db=db,
        display=display,
        model_override=model,
    )

    console.print(
        "\n[dim]Describe your project or ask the team anything. "
        "Type [bold]/help[/bold] for commands.[/dim]\n"
    )

    # ----------------------------------------------------------------
    # Main REPL loop
    # ----------------------------------------------------------------
    while True:
        try:
            user_input = Prompt.ask("[bold white]You[/bold white]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session saved. Goodbye![/dim]")
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            cmd = user_input.lower()

            if cmd in ("/quit", "/exit", "/q"):
                console.print("[dim]Session saved. Goodbye![/dim]")
                break

            elif cmd == "/help":
                display.show_help()

            elif cmd == "/team":
                orchestrator.show_team()

            elif cmd.startswith("/add "):
                role = cmd.split(" ", 1)[1].strip()
                orchestrator.add_agent(role)

            elif cmd.startswith("/remove "):
                role = cmd.split(" ", 1)[1].strip()
                orchestrator.remove_agent(role)

            elif cmd == "/memory":
                orchestrator.show_memory()

            elif cmd == "/history":
                orchestrator.show_history()

            elif cmd == "/project":
                orchestrator.show_project_info()

            elif cmd == "/clear":
                orchestrator.clear_context()

            else:
                console.print(
                    f"[yellow]Unknown command:[/yellow] {user_input}  "
                    "[dim](type /help for commands)[/dim]"
                )
            continue

        # @mention — talk directly to one agent, bypassing Aria's routing
        # e.g.  @sam can you add unit tests?
        #        @jordan what architecture do you recommend?
        mention = re.match(r"^@(\w+)\s+(.*)", user_input, re.DOTALL)
        if mention:
            role = mention.group(1).lower()
            message = mention.group(2).strip()
            orchestrator.direct_message(role, message)
            continue

        # Regular message → route through orchestrator
        orchestrator.process(user_input)


if __name__ == "__main__":
    main()
