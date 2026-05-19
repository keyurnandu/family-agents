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
import yaml
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


def _show_startup_hint(saved: list, config: dict, display) -> None:
    """Print saved project list and a one-line usage hint."""
    if saved:
        table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        table.add_column("Num", style="bold cyan", no_wrap=True)
        table.add_column("Name", style="bold white", no_wrap=True)
        table.add_column("Info", style="dim")
        for i, p in enumerate(saved, 1):
            table.add_row(
                str(i),
                p["name"],
                f"{p['message_count']} msgs · {p['last_active']}",
            )
        console.print()
        console.rule("[bold]Your Projects[/bold]", style="cyan")
        console.print(table)
        console.rule(style="dim")
        console.print(
            "\n[dim]Type a [bold]number[/bold] to resume, a [bold]name[/bold] to start new, "
            "or [bold]/help[/bold] for commands.[/dim]\n"
        )
    else:
        console.print(
            "\n[dim]No projects yet — type a [bold]name[/bold] to create your first one, "
            "or [bold]/help[/bold] for commands.[/dim]\n"
        )


def _handle_pre_project_command(cmd: str, raw: str, saved: list, config: dict, display) -> None:
    """Handle slash commands typed before a project is open. Returns None always."""
    if cmd in ("/help", "/h"):
        display.show_help()
    elif cmd in ("/team", "/roster"):
        default_roster = config["team"]["default_roster"]
        available = config["team"]["available_agents"]
        console.print("\n[dim]Default team — use /add <role> inside a project to adjust.[/dim]")
        display.show_team(default_roster, config["agent_personas"])
        console.print(
            f"[dim]Also available: {', '.join(available)}[/dim]\n"
        )
    elif cmd == "/list":
        if not saved:
            console.print("\n[dim]No projects yet.[/dim]\n")
        else:
            console.print()
            for i, p in enumerate(saved, 1):
                console.print(
                    f"  [cyan]{i}.[/cyan] [bold]{p['name']}[/bold]  "
                    f"[dim]{p['message_count']} msgs · {p['last_active']}[/dim]"
                )
            console.print()
    elif cmd in ("/quit", "/exit", "/q"):
        console.print("[dim]Goodbye![/dim]")
        sys.exit(0)
    else:
        console.print(
            f"[yellow]{raw}[/yellow] is only available inside a project.  "
            "[dim]Select or create one first.[/dim]"
        )


@click.command()
@click.option("--project", "-p", default=None, help="Project name to resume or create")
@click.option("--list", "list_projects", is_flag=True, help="List all saved projects")
@click.option("--model", "-m", default=None, help="Override the default model")
def main(project: str | None, list_projects: bool, model: str | None):
    """
    Tech Organization Agent System — your AI dev team in the terminal.

    Start:                 python cli.py
    Jump into a project:   python cli.py --project my-app
    List projects:         python cli.py --list
    """
    _check_cli()

    from orchestrator import Orchestrator
    from utils.db_manager import DBManager
    from utils.display import Display

    db = DBManager(BASE_DIR / "db" / "conversations.db")
    display = Display()

    with open(BASE_DIR / "config" / "settings.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # ── python cli.py --list ──────────────────────────────────────────
    if list_projects:
        saved = db.list_projects()
        if not saved:
            console.print("\n[dim]No projects found. Start one with:[/dim]  python cli.py\n")
        else:
            console.print("\n[bold]Saved Projects[/bold]\n")
            for p in saved:
                console.print(
                    f"  [cyan]{p['name']}[/cyan]  "
                    f"[dim]{p['message_count']} messages · last active {p['last_active']}[/dim]"
                )
            console.print()
        return

    display.show_welcome()

    orchestrator = None

    # ── python cli.py --project <name>: skip the picker entirely ──────
    if project:
        project_dir = BASE_DIR / "projects" / project
        project_dir.mkdir(parents=True, exist_ok=True)
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

    # ── No --project flag: show hint and let user pick via You: prompt ─
    else:
        _show_startup_hint(db.list_projects(), config, display)

    # ── Main REPL loop ────────────────────────────────────────────────
    while True:
        try:
            user_input = Prompt.ask("[bold white]You[/bold white]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session saved. Goodbye![/dim]")
            break

        if not user_input:
            continue

        # ── Project not yet open: resolve it from this input ──────────
        if orchestrator is None:
            saved = db.list_projects()

            # Slash command before a project is chosen
            if user_input.startswith("/"):
                _handle_pre_project_command(
                    user_input.lower(), user_input, saved, config, display
                )
                continue

            # Numeric selection
            if user_input.isdigit():
                idx = int(user_input) - 1
                if 0 <= idx < len(saved):
                    project = saved[idx]["name"]
                else:
                    console.print(
                        f"[yellow]No project at position {user_input}.[/yellow]  "
                        f"[dim]Choose 1–{len(saved)} or type a name.[/dim]"
                    )
                    continue
            else:
                # Reject names with slashes
                if "/" in user_input or "\\" in user_input:
                    console.print("[yellow]Project name can't contain slashes. Try again.[/yellow]")
                    continue
                project = user_input

            # Initialise the project and orchestrator
            project_dir = BASE_DIR / "projects" / project
            project_dir.mkdir(parents=True, exist_ok=True)
            existing = db.get_project(project)
            if existing:
                console.print(
                    f"\n[green]Resuming:[/green] [bold]{project}[/bold]  "
                    f"[dim]({existing['message_count']} messages in history)[/dim]"
                )
            else:
                console.print(f"\n[green]Starting new project:[/green] [bold]{project}[/bold]")
                db.ensure_project(project)
            console.print(
                f"[dim]Project files will be written to:[/dim] [cyan]{project_dir}[/cyan]\n"
            )
            orchestrator = Orchestrator(
                project_name=project,
                base_dir=BASE_DIR,
                db=db,
                display=display,
                model_override=model,
            )
            continue

        # ── Inside a project: normal slash commands ───────────────────
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
                orchestrator.add_agent(cmd.split(" ", 1)[1].strip())
            elif cmd.startswith("/remove "):
                orchestrator.remove_agent(cmd.split(" ", 1)[1].strip())
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

        # ── @mention: talk directly to one agent ─────────────────────
        mention = re.match(r"^@(\w+)\s+(.*)", user_input, re.DOTALL)
        if mention:
            orchestrator.direct_message(mention.group(1).lower(), mention.group(2).strip())
            continue

        # ── Regular message → route through Aria ─────────────────────
        orchestrator.process(user_input)


if __name__ == "__main__":
    main()
