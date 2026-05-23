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

# Reserved name for the project-free general chat workspace
GENERAL = "_general"

# Words that signal the user is talking, not naming a project
_CHAT_STARTERS = {
    "what", "how", "why", "when", "where", "who", "which", "can", "could",
    "should", "would", "will", "is", "are", "do", "does", "did", "has", "have",
    "tell", "help", "explain", "show", "give", "build", "create", "make",
    "write", "i", "we", "my", "our", "let", "please", "hi", "hello", "hey",
}


def _check_cli():
    if not shutil.which("claude"):
        console.print(
            "[bold red]Error:[/bold red] The [cyan]claude[/cyan] CLI is not installed or not in PATH.\n"
            "Install Claude Code from [link]https://claude.ai/code[/link] and log in once,\n"
            "then run this again — no API key needed."
        )
        sys.exit(1)


def _is_chat_input(text: str) -> bool:
    """Return True if the input looks like a chat message rather than a project name."""
    # Questions
    if text.endswith("?") or text.endswith("!"):
        return True
    words = text.split()
    # More than two words → definitely a sentence
    if len(words) > 2:
        return True
    # Starts with a common conversation word
    if words and words[0].lower() in _CHAT_STARTERS:
        return True
    return False


def _show_project_list(saved: list) -> None:
    """Print the numbered project table, excluding the general chat workspace."""
    real = [p for p in saved if p["name"] != GENERAL]
    general = next((p for p in saved if p["name"] == GENERAL), None)

    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column("Num", style="bold cyan", no_wrap=True)
    table.add_column("Name", style="bold white", no_wrap=True)
    table.add_column("Info", style="dim")
    for i, p in enumerate(real, 1):
        table.add_row(str(i), p["name"], f"{p['message_count']} msgs · {p['last_active']}")

    console.print()
    console.rule("[bold]Your Projects[/bold]", style="cyan")
    if real:
        console.print(table)
    if general:
        console.print(
            f"  [dim]💬 General chat  ·  {general['message_count']} msgs · {general['last_active']}  "
            "(type [bold]/switch _general[/bold] to resume)[/dim]"
        )
    console.rule(style="dim")
    return real  # caller may need the filtered list


def _show_startup_hint(saved: list) -> None:
    """Print project list (if any) and usage hint including general chat."""
    real = [p for p in saved if p["name"] != GENERAL]
    general = next((p for p in saved if p["name"] == GENERAL), None)

    if real:
        _show_project_list(saved)
        console.print(
            "\n[dim]Type a [bold]number[/bold] to resume a project, a [bold]name[/bold] to start new, "
            "[bold]just start talking[/bold] for quick adhoc questions, "
            "or [bold]/help[/bold] for commands.[/dim]\n"
        )
    elif general:
        # Only general chat exists — no real projects yet
        console.print(
            f"\n[dim]💬 General chat  ·  {general['message_count']} msgs · {general['last_active']}  "
            "(type [bold]/switch _general[/bold] to resume)[/dim]"
        )
        console.print(
            "\n[dim]Type a [bold]name[/bold] to start a project, "
            "[bold]just start talking[/bold] for adhoc questions, "
            "or [bold]/help[/bold] for commands.[/dim]\n"
        )
    else:
        console.print(
            "\n[dim]Type a [bold]name[/bold] to start a project, "
            "[bold]just start talking[/bold] for adhoc questions, "
            "or [bold]/help[/bold] for commands.[/dim]\n"
        )


def _open_project(name: str, db, display, model, force_new: bool = False, config: dict | None = None):
    """
    Initialise a project by name and return a ready Orchestrator.
    The _general workspace opens silently with no project-folder noise.
    If the project had a codebase loaded last session, prompts to reload it.
    """
    from pathlib import Path
    from orchestrator import Orchestrator

    project_dir = BASE_DIR / "projects" / name
    project_dir.mkdir(parents=True, exist_ok=True)

    existing = db.get_project(name)

    if name == GENERAL:
        # Silent open — no banner, no folder line
        db.ensure_project(name)
    elif existing and not force_new:
        console.print(
            f"\n[green]Resuming:[/green] [bold]{name}[/bold]  "
            f"[dim]({existing['message_count']} messages in history)[/dim]"
        )
        console.print(f"[dim]Project files → [/dim][cyan]{project_dir}[/cyan]\n")
    else:
        if force_new and existing:
            console.print(
                f"\n[yellow]A project named [bold]{name}[/bold] already exists — resuming it.[/yellow]"
            )
        else:
            console.print(f"\n[green]Starting new project:[/green] [bold]{name}[/bold]")
        db.ensure_project(name)
        console.print(f"[dim]Project files → [/dim][cyan]{project_dir}[/cyan]\n")

    orch = Orchestrator(
        project_name=name,
        base_dir=BASE_DIR,
        db=db,
        display=display,
        model_override=model,
        config=config,
    )

    # ── Auto-reload codebase from the previous session (no prompt) ────
    saved_cb = orch.memory.load_loaded_path()
    if saved_cb:
        cb_path = Path(saved_cb)
        if cb_path.exists() and cb_path.is_dir():
            orch.load_codebase(saved_cb)
        else:
            # Path no longer exists — silently drop the saved reference
            orch.memory.clear_loaded_path()

    return orch


def _pick_from_list(raw: str, saved: list) -> str | None:
    """
    If raw is a valid number selecting from the real (non-general) saved projects,
    return that project name. Otherwise return the raw string as a project name.
    Returns None if the number is out of range (caller should re-prompt).
    """
    real = [p for p in saved if p["name"] != GENERAL]
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(real):
            return real[idx]["name"]
        console.print(
            f"[yellow]No project at position {raw}.[/yellow]  "
            f"[dim]Choose 1–{len(real)} or type a name.[/dim]"
        )
        return None
    return raw


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
        real = [p for p in saved if p["name"] != GENERAL]
        if not real:
            console.print("\n[dim]No projects yet. Just start talking for adhoc questions.[/dim]\n")
        else:
            _show_project_list(saved)
            console.print()
    elif cmd in ("/quit", "/exit", "/q"):
        console.print("[dim]Goodbye![/dim]")
        sys.exit(0)
    elif cmd == "/status":
        console.print("[dim]Open a project first to see its status.[/dim]")
    elif raw.lower().startswith("/model"):
        parts = raw.split(None, 1)
        arg = parts[1].strip().lower() if len(parts) > 1 else ""
        current = config.get("model", "sonnet")
        if not arg:
            console.print(
                f"[dim]Default model: [bold]{current}[/bold]  "
                "· Change with [cyan]/model haiku|sonnet|opus[/cyan][/dim]"
            )
        elif arg in ("haiku", "sonnet", "opus"):
            config["model"] = arg
            console.print(
                f"[green]✓ Default model set to:[/green] [bold]{arg}[/bold]  "
                "[dim](applies to the next project you open)[/dim]\n"
            )
        else:
            console.print(
                f"[yellow]Unknown model:[/yellow] {arg}  "
                "[dim]Available: haiku · sonnet · opus[/dim]"
            )
    else:
        console.print(
            f"[yellow]{raw}[/yellow] is only available inside a project.  "
            "[dim]Select or create one first, or just start talking for adhoc questions.[/dim]"
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
        real = [p for p in saved if p["name"] != GENERAL]
        if not real:
            console.print("\n[dim]No projects found. Start one with:[/dim]  python cli.py\n")
        else:
            _show_project_list(saved)
            console.print()
        return

    display.show_welcome()

    orchestrator = None
    current_project = project  # None until resolved

    # ── python cli.py --project <name>: skip straight in ─────────────
    if current_project:
        orchestrator = _open_project(current_project, db, display, model, config=config)
        if current_project != GENERAL:
            console.print(
                "[dim]Describe your project or ask the team anything. "
                "Type [bold]/help[/bold] for commands.[/dim]\n"
            )
    else:
        _show_startup_hint(db.list_projects())

    # ── Main REPL loop ────────────────────────────────────────────────
    while True:
        try:
            active_model = orchestrator.model if orchestrator else (model or config.get("model", "sonnet"))
            user_input = Prompt.ask(f"[bold white]You[/bold white] [dim]({active_model})[/dim]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session saved. Goodbye![/dim]")
            break

        if not user_input:
            continue

        # ── Multiline paste mode ──────────────────────────────────────
        # Triggers: /paste  OR  """
        # Type either trigger to open paste mode. Paste or type content
        # in the ··· prompts. Type /end or """ alone to send everything
        # as one message. Prevents pasted terminal output being processed
        # line-by-line and consuming tokens.
        _PASTE_OPEN  = user_input.strip() in ('/paste', '"""') or user_input.startswith('"""')
        _PASTE_CLOSE = lambda l: l.strip() in ('/end', '"""')  # noqa: E731
        if _PASTE_OPEN:
            console.print(
                "[dim]Paste mode opened — paste your content below, "
                "then type [bold]/end[/bold] (or [bold]\"\"\"[/bold]) to send.[/dim]"
            )
            lines = []
            while True:
                try:
                    line = Prompt.ask("[dim]  ···[/dim]")
                except (KeyboardInterrupt, EOFError):
                    console.print("\n[dim]Paste cancelled.[/dim]")
                    lines = []
                    break
                if _PASTE_CLOSE(line):
                    break
                lines.append(line)
            if not lines:
                continue
            user_input = "\n".join(lines)
            console.print(
                f"[dim]  Submitting {len(lines)} lines as one message…[/dim]\n"
            )

        # ── No project open yet ───────────────────────────────────────
        if orchestrator is None:
            saved = db.list_projects()

            # Slash commands
            if user_input.startswith("/"):
                cmd_lower = user_input.lower()
                parts_pre = user_input.split(None, 1)

                if cmd_lower.startswith("/load"):
                    # Derive project name from the folder being loaded so each
                    # codebase gets its own isolated memory, history, and docs.
                    path_arg = parts_pre[1].strip() if len(parts_pre) > 1 else ""
                    if path_arg:
                        from pathlib import Path as _Path
                        folder_name = _Path(path_arg).name or GENERAL
                        # Sanitize: strip characters not safe for a project name
                        import re as _re
                        folder_name = _re.sub(r"[^\w\-]", "-", folder_name).strip("-") or GENERAL
                        current_project = folder_name
                        console.print(
                            f"[dim]📂 Opening project [bold]{folder_name}[/bold] "
                            f"for {path_arg}[/dim]"
                        )
                    else:
                        current_project = GENERAL
                    orchestrator = _open_project(current_project, db, display, model, config=config)
                    # fall through to the in-session command handler below

                elif cmd_lower == "/unload":
                    current_project = GENERAL
                    orchestrator = _open_project(GENERAL, db, display, model, config=config)
                    # fall through to the in-session command handler below

                else:
                    _handle_pre_project_command(user_input, saved, config, display)
                    continue

            # @mention → route through general chat
            elif re.match(r"^@\w+", user_input):
                console.print(
                    "[dim]💬 Routing to general chat (no project open)…[/dim]"
                )
                current_project = GENERAL
                orchestrator = _open_project(GENERAL, db, display, model, config=config)
                # fall through to @mention handler below

            # Chat input → auto-open general workspace
            elif _is_chat_input(user_input):
                console.print(
                    "[dim]💬 General chat — use [bold]/new <name>[/bold] or "
                    "[bold]/switch[/bold] to open a project anytime.[/dim]"
                )
                current_project = GENERAL
                orchestrator = _open_project(GENERAL, db, display, model, config=config)
                # fall through to regular message handler below

            else:
                # Looks like a project name
                if "/" in user_input or "\\" in user_input:
                    console.print("[yellow]Project name can't contain slashes. Try again.[/yellow]")
                    continue

                name = _pick_from_list(user_input, saved)
                if name is None:
                    continue  # bad number — error already printed

                current_project = name
                orchestrator = _open_project(current_project, db, display, model, config=config)
                continue

        # ── Inside a project or general chat: slash commands ──────────
        if user_input.startswith("/"):
            cmd = user_input.lower()
            parts = cmd.split(None, 1)
            # Preserve original casing for arguments (project names are case-sensitive)
            raw_parts = user_input.split(None, 1)

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

            elif cmd == "/redo":
                # Re-submit or edit the last interrupted/sent message
                last = orchestrator.last_user_input
                if not last:
                    console.print("\n[dim]Nothing to redo — no previous message recorded.[/dim]\n")
                else:
                    console.print(
                        f"\n[dim]Last message:[/dim] [bold white]{last[:120]}{'…' if len(last) > 120 else ''}[/bold white]"
                    )
                    try:
                        edited = Prompt.ask(
                            "[bold cyan]Edit or press Enter to re-send[/bold cyan]",
                            default=last,
                        ).strip()
                    except (KeyboardInterrupt, EOFError):
                        console.print("\n[dim]Cancelled.[/dim]")
                        edited = ""
                    if edited:
                        console.print()
                        orchestrator.process(edited)
                    else:
                        console.print("[dim]Nothing sent.[/dim]\n")

            elif parts[0] == "/load":
                path_arg = parts[1].strip() if len(parts) > 1 else ""
                if not path_arg:
                    console.print(
                        "[yellow]Usage:[/yellow] /load <path>  "
                        "[dim]e.g. /load C:\\projects\\my-app[/dim]"
                    )
                else:
                    orchestrator.load_codebase(path_arg)

            elif cmd == "/unload":
                orchestrator.unload_codebase()

            elif parts[0] == "/model":
                arg = parts[1].strip().lower() if len(parts) > 1 else ""
                MODEL_ALIASES = {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}
                if not arg:
                    console.print(
                        f"[dim]Current model: [bold]{orchestrator.model}[/bold]  "
                        "· Change with [cyan]/model haiku|sonnet|opus[/cyan][/dim]"
                    )
                elif arg in MODEL_ALIASES:
                    old = orchestrator.model
                    orchestrator.model = MODEL_ALIASES[arg]
                    # Propagate to all agents
                    for agent in orchestrator.agents.values():
                        agent.model = MODEL_ALIASES[arg]
                    console.print(
                        f"[green]✓ Model switched:[/green] {old} → [bold]{orchestrator.model}[/bold]  "
                        "[dim](takes effect on the next message)[/dim]\n"
                    )
                else:
                    console.print(
                        f"[yellow]Unknown model:[/yellow] {arg}  "
                        "[dim]Available: haiku · sonnet · opus[/dim]"
                    )

            elif cmd == "/status":
                orchestrator.show_status()

            elif cmd == "/state":
                state = orchestrator._load_project_state()
                if state.strip():
                    from rich.syntax import Syntax
                    console.print()
                    console.rule("[bold bright_cyan]📍 Project State[/bold bright_cyan]", style="bright_cyan")
                    console.print(Syntax(state, "markdown", theme="monokai"))
                    console.print()
                else:
                    console.print(
                        "\n[dim]No state.md yet — state is built automatically after the "
                        "first exchange.[/dim]\n"
                    )

            elif parts[0] == "/export":
                doc_type = parts[1].strip() if len(parts) > 1 else ""
                if not doc_type:
                    console.print(
                        "[dim]Usage: /export <type>\n"
                        "Types: requirements · architecture · technical-spec · sprint-plan · api-docs · test-plan · deployment-plan[/dim]"
                    )
                else:
                    orchestrator.export_doc(doc_type)

            elif parts[0] == "/retrospective" or cmd == "/retro":
                orchestrator.run_retrospective()

            elif parts[0] == "/feedback":
                # /feedback @sam never use uv
                # /feedback sam always check imports first
                rest = raw_parts[1].strip() if len(raw_parts) > 1 else ""
                if not rest:
                    console.print(
                        "[dim]Usage: /feedback <agent> <lesson>\n"
                        "  e.g. /feedback @sam never use uv on Windows\n"
                        "  e.g. /feedback jordan always audit imports before running tests[/dim]"
                    )
                else:
                    # Split agent identifier from lesson
                    tokens = rest.lstrip("@").split(None, 1)
                    if len(tokens) < 2:
                        console.print(
                            "[dim]Usage: /feedback <agent> <lesson>  "
                            "e.g. /feedback sam never use uv[/dim]"
                        )
                    else:
                        orchestrator.add_feedback(tokens[0], tokens[1])

            elif parts[0] == "/auto":
                arg = parts[1].strip().lower() if len(parts) > 1 else ""
                auto_enabled = orchestrator.memory.load_auto_mode()

                if not arg or arg == "status":
                    status_label = "[bold green]ON[/bold green]" if auto_enabled else "[dim]OFF[/dim]"
                    console.print(f"\n[bold]Auto Mode:[/bold] {status_label}")
                    if auto_enabled:
                        console.print(
                            "[dim]• File writes auto-approved\n"
                            "• Safe bash commands auto-approved\n"
                            "• Destructive commands still require manual approval\n"
                            "• Aria auto-pilots to the next step (max 5 iterations)[/dim]"
                        )
                    console.print()

                elif arg == "on":
                    orchestrator.memory.save_auto_mode(True)
                    console.print(
                        "\n[bold green]✓ Auto mode ON[/bold green]\n"
                        "[dim]• File writes: auto-approved  ⚡\n"
                        "• Safe bash: auto-approved  ⚡\n"
                        "• Destructive bash (rm -rf, DROP TABLE, git push --force): manual approval\n"
                        "• Aria auto-pilots between phases (max 5 iterations)\n"
                        "• Press Ctrl+C at any time to interrupt[/dim]\n"
                    )

                elif arg == "off":
                    orchestrator.memory.save_auto_mode(False)
                    console.print(
                        "\n[dim]Auto mode OFF — all actions require manual approval.[/dim]\n"
                    )

                else:
                    console.print(
                        "[dim]Usage:\n"
                        "  /auto on      — enable auto-approve + auto-pilot\n"
                        "  /auto off     — disable auto mode\n"
                        "  /auto status  — show current auto mode setting[/dim]"
                    )

            elif parts[0] == "/tdd":
                arg = parts[1].strip().lower() if len(parts) > 1 else ""
                tdd_enabled, tdd_health_cmd = orchestrator.memory.load_tdd_mode()

                if not arg or arg == "status":
                    status_label = "[bold green]ON[/bold green]" if tdd_enabled else "[dim]OFF[/dim]"
                    console.print(f"\n[bold]TDD Mode:[/bold] {status_label}")
                    if tdd_enabled:
                        if tdd_health_cmd:
                            console.print(f"[dim]Health check:[/dim] [cyan]{tdd_health_cmd}[/cyan]")
                        else:
                            console.print("[dim]Health check: not set — use [cyan]/tdd health <cmd>[/cyan] to add one[/dim]")
                        console.print(
                            "[dim]Workflow: Casey writes tests first → Sam implements → "
                            "health check runs after every file write[/dim]"
                        )
                    console.print()

                elif arg == "on":
                    # Auto-suggest a health check command based on the loaded codebase
                    suggested = ""
                    if orchestrator.loaded_path:
                        lp = orchestrator.loaded_path
                        if (lp / "venv" / "Scripts" / "python.exe").exists():
                            py = r"venv\Scripts\python.exe"
                        elif (lp / "venv" / "bin" / "python").exists():
                            py = "venv/bin/python"
                        else:
                            py = "python"
                        # Suggest import check for Python projects
                        if (lp / "app" / "main.py").exists():
                            suggested = f'{py} -c "from app.main import app"'
                        elif (lp / "src" / "main.py").exists():
                            suggested = f'{py} -c "import src.main"'
                        elif (lp / "requirements.txt").exists() or (lp / "pyproject.toml").exists():
                            suggested = f"{py} -m pytest --collect-only -q"
                        elif (lp / "package.json").exists():
                            suggested = "npm test -- --passWithNoTests"
                    # Prompt for health check command
                    hint = f" [dim](Enter for: {suggested})[/dim]" if suggested else " [dim](Enter to skip)[/dim]"
                    try:
                        new_cmd = Prompt.ask(
                            f"[bold cyan]Health check command[/bold cyan]{hint}"
                        ).strip()
                    except (KeyboardInterrupt, EOFError):
                        console.print("\n[dim]Cancelled.[/dim]")
                        continue
                    if not new_cmd and suggested:
                        new_cmd = suggested
                    orchestrator.memory.save_tdd_mode(True, new_cmd)
                    # Add qa to the team if not already there
                    if "qa" not in orchestrator.active_roster and "qa" in orchestrator.agents:
                        orchestrator.active_roster.append("qa")
                        qa_p = config["agent_personas"].get("qa", {})
                        console.print(
                            f"[green]+ {qa_p.get('emoji','')} Casey (qa) added to team[/green]  "
                            "[dim]— TDD requires a QA engineer[/dim]"
                        )
                    console.print(f"\n[bold green]✓ TDD mode ON[/bold green]")
                    console.print(
                        "[dim]Workflow: Casey writes failing tests → Sam implements → "
                        "health check runs after every approved file write[/dim]"
                    )
                    if new_cmd:
                        console.print(f"[dim]Health check: [cyan]{new_cmd}[/cyan][/dim]")
                    else:
                        console.print("[dim]No health check set — TDD routing active, no auto-check[/dim]")
                    console.print()

                elif arg == "off":
                    orchestrator.memory.save_tdd_mode(False, tdd_health_cmd)
                    console.print("\n[dim]TDD mode OFF — normal routing restored.[/dim]\n")

                elif arg.startswith("health"):
                    # /tdd health <cmd> — update just the health check command
                    raw_sub = raw_parts[1].strip() if len(raw_parts) > 1 else ""
                    new_cmd = raw_sub[len("health"):].strip() if raw_sub.lower().startswith("health") else ""
                    if not new_cmd:
                        try:
                            new_cmd = Prompt.ask("[bold cyan]New health check command[/bold cyan]").strip()
                        except (KeyboardInterrupt, EOFError):
                            console.print("\n[dim]Cancelled.[/dim]")
                            continue
                    if new_cmd:
                        orchestrator.memory.save_tdd_mode(tdd_enabled, new_cmd)
                        console.print(f"\n[green]✓ Health check updated:[/green] [cyan]{new_cmd}[/cyan]\n")
                    else:
                        console.print("[dim]No change.[/dim]")

                else:
                    console.print(
                        "[dim]Usage:\n"
                        "  /tdd on              — enable TDD mode (prompts for health check)\n"
                        "  /tdd off             — disable TDD mode\n"
                        "  /tdd status          — show current TDD settings\n"
                        "  /tdd health <cmd>    — update the health check command[/dim]"
                    )

            elif parts[0] == "/skill":
                sub = (parts[1] if len(parts) > 1 else "").split(None, 2)
                action = sub[0] if sub else ""
                if action == "list":
                    role_f = sub[1] if len(sub) > 1 else None
                    orchestrator.show_skills(role_f)
                elif action == "add":
                    role_str = sub[1].strip() if len(sub) > 1 else ""
                    skill_name_arg = sub[2].strip() if len(sub) > 2 else ""
                    if not role_str:
                        console.print("[yellow]Usage:[/yellow] /skill add <role> [skill-name]  e.g. /skill add developer react-native")
                    else:
                        if not skill_name_arg:
                            try:
                                skill_name_arg = Prompt.ask("[bold cyan]Skill name[/bold cyan] (e.g. react-native, aws)").strip()
                            except (KeyboardInterrupt, EOFError):
                                console.print("\n[dim]Cancelled.[/dim]")
                                continue
                        if skill_name_arg:
                            try:
                                desc = Prompt.ask(
                                    f"[bold cyan]Describe what they should know[/bold cyan] "
                                    "[dim](Enter to auto-generate)[/dim]"
                                ).strip()
                            except (KeyboardInterrupt, EOFError):
                                desc = ""
                            orchestrator.add_skill(role_str, skill_name_arg, desc)
                elif action == "remove":
                    if len(sub) < 3:
                        console.print("[yellow]Usage:[/yellow] /skill remove <role> <skill-name>")
                    else:
                        orchestrator.remove_skill(sub[1].strip(), sub[2].strip())
                else:
                    console.print(
                        "[dim]Usage:\n"
                        "  /skill list [role]              — list skills\n"
                        "  /skill add <role> [name]        — add a skill\n"
                        "  /skill remove <role> <name>     — remove a skill[/dim]"
                    )

            # ── /switch [name|number] ─────────────────────────────────
            elif parts[0] == "/switch":
                saved = db.list_projects()
                existing_names = {p["name"] for p in saved}

                def _resolve_project_name(name: str) -> str:
                    """Return the canonical project name (preserving DB casing), case-insensitive."""
                    if name in existing_names:
                        return name
                    for existing in existing_names:
                        if existing.lower() == name.lower():
                            return existing
                    return name  # not found — return as-is so _validate_switch can error

                def _validate_switch(name: str) -> bool:
                    """Return True if name is a valid switch target, print error if not."""
                    if name == GENERAL:
                        return True
                    if name in existing_names:
                        return True
                    # Not found — suggest close matches
                    close = [n for n in existing_names if n != GENERAL and
                             (n.lower().startswith(name[:3].lower()) or name[:3].lower() in n.lower() or
                              abs(len(n) - len(name)) <= 3)]
                    msg = f"[yellow]No project named '[bold]{name}[/bold]'.[/yellow]"
                    if close:
                        suggestions = "  ".join(f"[cyan]{c}[/cyan]" for c in close[:3])
                        msg += f"  Did you mean: {suggestions}?"
                    else:
                        msg += "  [dim]Use /new to create it, or /switch to pick from the list.[/dim]"
                    console.print(msg)
                    return False

                if len(parts) > 1:
                    # Use raw_parts to preserve original casing; strip surrounding quotes
                    arg = raw_parts[1].strip().strip('"\'') if len(raw_parts) > 1 else parts[1].strip()
                    if arg.lower() == GENERAL:
                        name = GENERAL
                    else:
                        name = _pick_from_list(arg, saved)
                        if name is None:
                            continue
                        name = _resolve_project_name(name)  # fix casing
                        if not _validate_switch(name):
                            continue
                else:
                    _show_startup_hint(saved)
                    try:
                        arg = Prompt.ask("[bold cyan]Switch to[/bold cyan]").strip()
                    except (KeyboardInterrupt, EOFError):
                        console.print("\n[dim]Staying in current workspace.[/dim]")
                        continue
                    if not arg:
                        console.print("[dim]Staying in current workspace.[/dim]")
                        continue
                    name = _pick_from_list(arg, saved) if arg != GENERAL else GENERAL
                    if name is None:
                        continue
                    if not _validate_switch(name):
                        continue

                if name == current_project:
                    label = "💬 general chat" if name == GENERAL else f"[bold]{current_project}[/bold]"
                    console.print(f"[dim]Already in {label}.[/dim]")
                    continue

                label = "💬 general chat" if current_project == GENERAL else f"[bold]{current_project}[/bold]"
                console.print(f"\n[dim]Leaving {label} — session saved.[/dim]")
                current_project = name
                orchestrator = _open_project(current_project, db, display, model, config=config)
                if current_project != GENERAL:
                    console.print(
                        "[dim]Describe your project or ask the team anything. "
                        "Type [bold]/help[/bold] for commands.[/dim]\n"
                    )

            # ── /new <name> ───────────────────────────────────────────
            elif parts[0] == "/new":
                if len(raw_parts) < 2 or not raw_parts[1].strip():
                    console.print(
                        "[yellow]Usage:[/yellow] /new <project-name>  "
                        "[dim]e.g. /new restaurant-saas[/dim]"
                    )
                    continue
                name = raw_parts[1].strip().strip("\"'")
                if "/" in name or "\\" in name:
                    console.print("[yellow]Project name can't contain slashes.[/yellow]")
                    continue
                label = "💬 general chat" if current_project == GENERAL else f"[bold]{current_project}[/bold]"
                console.print(f"\n[dim]Leaving {label} — session saved.[/dim]")
                current_project = name
                orchestrator = _open_project(current_project, db, display, model, force_new=True, config=config)

            else:
                console.print(
                    f"[yellow]Unknown command:[/yellow] {user_input}  "
                    "[dim](type /help for commands)[/dim]"
                )
            continue

        # ── @mention: talk directly to one agent ─────────────────────
        mention = re.match(r"^@(\w+)\s+(.*)", user_input, re.DOTALL)
        if mention:
            from utils.claude_client import snapshot_stats, get_session_stats
            pre = snapshot_stats()
            orchestrator.direct_message(mention.group(1).lower(), mention.group(2).strip())
            post = get_session_stats()
            exchange_tokens = post["estimated_tokens"] - (pre["input_chars"] + pre["output_chars"]) // 4
            display.show_token_usage(max(exchange_tokens, 0), post["estimated_tokens"], post["calls"],
                                     safe_context=config.get("safe_context_tokens", 200_000))
            continue

        # ── Regular message → route through Aria ─────────────────────
        from utils.claude_client import snapshot_stats, get_session_stats
        pre = snapshot_stats()
        orchestrator.process(user_input)
        post = get_session_stats()
        exchange_tokens = post["estimated_tokens"] - (pre["input_chars"] + pre["output_chars"]) // 4
        display.show_token_usage(max(exchange_tokens, 0), post["estimated_tokens"], post["calls"],
                                 safe_context=config.get("safe_context_tokens", 200_000))


if __name__ == "__main__":
    main()
