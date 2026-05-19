from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

console = Console()


class Display:
    def show_welcome(self):
        panel = Panel(
            "[bold cyan]Tech Organization Agent System[/bold cyan]\n\n"
            "Your AI development team is ready to collaborate.\n"
            "You are the [bold white]Customer[/bold white] — describe your project, ask questions,\n"
            "and the team will handle requirements, architecture, and planning.\n\n"
            "[dim]Type [bold]/help[/bold] to see available commands.[/dim]",
            title="[bold]Welcome[/bold]",
            border_style="cyan",
            padding=(1, 2),
        )
        console.print(panel)

    def show_agent_response(self, name: str, response: str, color: str, emoji: str):
        console.print()
        console.rule(f"{emoji} [bold {color}]{name}[/bold {color}]", style=color)
        console.print(response)

    def show_orchestrator_response(self, response: str):
        if response.strip():
            console.print()
            console.rule(
                "[bold bright_cyan]🎯 Aria (Coordinator)[/bold bright_cyan]",
                style="bright_cyan",
            )
            console.print(response)

    def show_memory_saved(self, category: str, snippet: str):
        short = snippet[:70] + "..." if len(snippet) > 70 else snippet
        console.print(
            f"\n[dim green]💾 Saved to memory  [{category}]  {short}[/dim green]"
        )

    def show_team(self, active_roster: list, personas: dict):
        table = Table(
            title="Current Team Roster",
            show_header=True,
            header_style="bold",
            border_style="dim",
        )
        table.add_column("Role", style="dim")
        table.add_column("Name")
        table.add_column("Speciality")

        descriptions = {
            "pm": "Project planning, timelines, stakeholder management",
            "bsa": "Requirements, user stories, process mapping",
            "developer": "Implementation, APIs, database, code",
            "lead": "Architecture, technical direction, code review",
            "researcher": "Technology evaluation, best practices",
            "qa": "Testing strategy, quality gates, bug taxonomy",
            "devops": "CI/CD, cloud infrastructure, deployments",
        }

        for role in active_roster:
            p = personas.get(role, {})
            name = p.get("name", role.upper())
            emoji = p.get("emoji", "")
            color = p.get("color", "white")
            table.add_row(
                role,
                f"{emoji} [{color}]{name}[/{color}]",
                descriptions.get(role, "—"),
            )

        console.print()
        console.print(table)
        console.print()

    def show_memory(self, entries: list, project_name: str):
        if not entries:
            console.print(
                f"\n[dim]No project memory saved yet for [bold]{project_name}[/bold].[/dim]\n"
            )
            return

        table = Table(
            title=f"Project Memory — {project_name}",
            show_header=True,
            header_style="bold",
            border_style="dim",
        )
        table.add_column("Category", style="cyan", no_wrap=True)
        table.add_column("Source", style="dim", no_wrap=True)
        table.add_column("Saved At", style="dim", no_wrap=True)
        table.add_column("Content")

        for entry in entries:
            table.add_row(
                entry.get("category", ""),
                entry.get("source", ""),
                entry.get("timestamp", ""),
                entry.get("content", "").strip(),
            )

        console.print()
        console.print(table)
        console.print()

    def show_history(self, history: list):
        if not history:
            console.print("\n[dim]No conversation history yet.[/dim]\n")
            return

        console.print()
        for msg in history:
            role = msg["role"]
            ts = msg.get("timestamp", "")
            preview = msg["content"]
            if len(preview) > 200:
                preview = preview[:200] + " [dim]…[/dim]"

            if role == "user":
                console.print(f"[dim]{ts}[/dim]  [bold white]You:[/bold white]  {preview}")
            else:
                console.print(f"[dim]{ts}[/dim]  [bold cyan]Team:[/bold cyan]  {preview}")
            console.print()

    def show_help(self):
        panel = Panel(
            "[bold]Commands[/bold]\n"
            "  [cyan]/team[/cyan]              Show current team roster\n"
            "  [cyan]/add <role>[/cyan]        Add agent  (e.g. [dim]/add qa[/dim])\n"
            "  [cyan]/remove <role>[/cyan]     Remove agent  (e.g. [dim]/remove devops[/dim])\n"
            "  [cyan]/memory[/cyan]            Show project memory\n"
            "  [cyan]/history[/cyan]           Show recent conversation\n"
            "  [cyan]/clear[/cyan]             Clear context window (keeps memory)\n"
            "  [cyan]/project[/cyan]           Show current project info\n"
            "  [cyan]/quit[/cyan]  [cyan]/exit[/cyan]       Exit\n\n"
            "[bold]Available Roles[/bold]\n"
            "  [green]pm[/green] · [yellow]bsa[/yellow] · [blue]developer[/blue] · [magenta]lead[/magenta] · "
            "[cyan]researcher[/cyan] · [bright_green]qa[/bright_green] · [bright_yellow]devops[/bright_yellow]\n\n"
            "[bold]Memory Tips[/bold]\n"
            "  Say [italic]'remember that…'[/italic] or [italic]'note that…'[/italic] to save facts\n"
            "  Important decisions are automatically captured",
            title="[bold]Help[/bold]",
            border_style="dim",
            padding=(1, 2),
        )
        console.print(panel)
