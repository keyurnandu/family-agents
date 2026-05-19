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


def _show_project_list(saved: list) -> None:
    """Print the numbered project table."""
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


def _show_startup_hint(saved: list) -> None:
    """Print project list (if any) and a one-line usage hint."""
    if saved:
        _show_project_list(saved)
        console.print(
            "\n[dim]Type a [bold]number[/bold] to resume, a [bold]name[/bold] to start new, "
            "or [bold]/help[/bold] for commands.[/dim]\n"
        )
    else:
        console.print(
            "\n[dim]No projects yet — type a [bold]name[/bold] to create your first one, "
            "or [bold]/help[/bold] for commands.[/dim]\n"
        )


def _open_project(name: str, db, display, model, force_new: bool = False):
    """
    Initialise a project by name and return a ready Orchestrator.
    Prints resume/new status. Creates the project folder.
    If force_new=True, treats it as a new project even if name exists in DB.
    """
    from orchestrator import Orchestrator

    project_dir = BASE_DIR / "projects" / name
    project_dir.mkdir(parents=True, exist_ok=True)

    existing = db.get_project(name)
    if existing and not force_new:
        console.print(
            f"\n[green]Resuming:[/green] [bold]{name}[/bold]  "
            f"[dim]({existing['message_count']} messages in history)[/dim]"
        )
    else:
        if force_new and existing:
            console.print(
                f"\n[yellow]A project named [bold]{name}[/bold] already exists — resuming it.[/yellow]"
            )
        else:
            console.print(f"\n[green]Starting new project:[/green] [bold]{name}[/bold]")
        db.ensure_project(name)

    console.print(f"[dim]Project files → [/dim][cyan]{project_dir}[/cyan]\n")

    return Orchestrator(
        project_name=name,
        base_dir=BASE_DIR,
        db=db,
        display=display,
        model_override=model,
    )


def _pick_from_list(raw: str, saved: list) -> str | None:
    """
    If raw is a valid number selecting from saved, return that project name.
    Otherwise return None.
    """
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(saved):
            return saved[idx]["name"]
        console.print(
            f"[yellow]No project at position {raw}.[/yellow]  "
            f"[dim]Choose 1–{len(saved)} or type a name.[/dim]"
        )
        return None  # signal: bad number, re-prompt
    return raw  # not a number — treat as project name


def _handle_pre_project_command(raw: str, saved: list, config: dict, display) -> None:
    """Slash commands available before any project is open."""
    cmd = raw.lower()
    if cmd in ("/help", "/h"):
        display.show_help()
    elif cmd in ("/team", "/roster"):
        console.print("\n[dim]Default team — use /add <role> inside a project to adjust.[/dim]")
        display.show_team(config["team"]["default_roster"], config["agent_personas"])
        available = config["team"]["available_agents"]
        console.print(f"[dim]Also available: {', '.join(available)}[/dim]\n")
    elif cmd == "/list":
        if not saved:
            console.print("\n[dim]No projects yet.[/dim]\n")
        else:
            _show_project_list(saved)
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
            _show_project_list(saved)
            console.print()
        return

    display.show_welcome()

    orchestrator = None

    # ── python cli.py --project <name>: skip straight in ─────────────
    if project:
        orchestrator = _open_project(project, db, display, model)
        console.print(
            "[dim]Describe your project or ask the team anything. "
            "Type [bold]/help[/bold] for commands.[/dim]\n"
        )
    else:
        _show_startup_hint(db.list_projects())

    # ── Main REPL loop ────────────────────────────────────────────────
    while True:
        try:
            user_input = Prompt.ask("[bold white]You[/bold white]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session saved. Goodbye![/dim]")
            break

        if not user_input:
            continue

        # ── No project open yet: resolve from this input ──────────────
        if orchestrator is None:
            saved = db.list_projects()

            if user_input.startswith("/"):
                _handle_pre_project_command(user_input, saved, config, display)
                continue

            if "/" in user_input or "\\" in user_input:
                console.print("[yellow]Project name can't contain slashes. Try again.[/yellow]")
                continue

            name = _pick_from_list(user_input, saved)
            if name is None:
                continue  # bad number — already printed error

            project = name
            orchestrator = _open_project(project, db, display, model)
            continue

        # ── Inside a project: slash commands ─────────────────────────
        if user_input.startswith("/"):
            cmd = user_input.lower()
            parts = cmd.split(None, 1)  # ["/switch", "name"] or ["/switch"]

            if cmd in ("/quit", "/exit", "/q"):
                console.print("[dim]Session saved. Goodbye![/dim]")
                break

            elif cmd == "/help":
                display.show_help()

            elif cmd == "/team":
                orchestrator.show_team()

            elif cmd.startswith("/add "):
                orchestrator.add_agent(parts[1] if len(parts) > 1 else "")

            elif cmd.startswith("/remove "):
                orchestrator.remove_agent(parts[1] if len(parts) > 1 else "")

            elif cmd == "/memory":
                orchestrator.show_memory()

            elif cmd == "/history":
                orchestrator.show_history()

            elif cmd == "/project":
                orchestrator.show_project_info()

            elif cmd == "/clear":
                orchestrator.clear_context()

            # ── /switch [name|number] ─────────────────────────────────
            elif parts[0] == "/switch":
                saved = db.list_projects()

                if len(parts) > 1:
                    # Direct: /switch my-app  or  /switch 2
                    arg = parts[1].strip()
                    name = _pick_from_list(arg, saved)
                    if name is None:
                        continue
                else:
                    # No arg — show list and prompt inline
                    if saved:
                        _show_project_list(saved)
                        console.print(
                            "\n[dim]Type a number or project name (or press Enter to stay here):[/dim]"
                        )
                    else:
                        console.print("[dim]No other projects yet. Type a name to create one:[/dim]")
                    try:
                        arg = Prompt.ask("[bold cyan]Switch to[/bold cyan]").strip()
                    except (KeyboardInterrupt, EOFError):
                        console.print("\n[dim]Staying in current project.[/dim]")
                        continue
                    if not arg:
                        console.print("[dim]Staying in current project.[/dim]")
                        continue
                    name = _pick_from_list(arg, saved)
                    if name is None:
                        continue

                if name == project:
                    console.print(f"[dim]Already in [bold]{project}[/bold].[/dim]")
                    continue

                console.print(f"\n[dim]Leaving [bold]{project}[/bold] — session saved.[/dim]")
                project = name
                orchestrator = _open_project(project, db, display, model)

            # ── /new <name> ───────────────────────────────────────────
            elif parts[0] == "/new":
                if len(parts) < 2 or not parts[1].strip():
                    console.print(
                        "[yellow]Usage:[/yellow] /new <project-name>  "
                        "[dim]e.g. /new restaurant-saas[/dim]"
                    )
                    continue
                name = parts[1].strip()
                if "/" in name or "\\" in name:
                    console.print("[yellow]Project name can't contain slashes.[/yellow]")
                    continue
                console.print(f"\n[dim]Leaving [bold]{project}[/bold] — session saved.[/dim]")
                project = name
                orchestrator = _open_project(project, db, display, model, force_new=True)

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
