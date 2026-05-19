#!/usr/bin/env python3
"""
Tech Organization Agent System
Run: python cli.py [--project NAME]
"""

import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.prompt import Prompt

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
        project = Prompt.ask("\n[bold cyan]Project name[/bold cyan]").strip()
        if not project:
            console.print("[red]Project name cannot be empty.[/red]")
            sys.exit(1)

    existing = db.get_project(project)
    if existing:
        console.print(
            f"\n[green]Resuming:[/green] [bold]{project}[/bold]  "
            f"[dim]({existing['message_count']} messages in history)[/dim]"
        )
    else:
        console.print(f"\n[green]Starting new project:[/green] [bold]{project}[/bold]")
        db.ensure_project(project)

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

        # Regular message → route through orchestrator
        orchestrator.process(user_input)


if __name__ == "__main__":
    main()
