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
            "and the team handles requirements, architecture, planning, and code.\n\n"
            "[dim]· Type a [bold]number[/bold] to resume a project  "
            "· Type a [bold]name[/bold] to start new\n"
            "· [bold]Just start talking[/bold] for quick adhoc questions (no project needed)\n"
            "· Type [bold]/help[/bold] for all commands[/dim]",
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

    def show_token_usage(self, exchange_tokens: int, session_tokens: int, calls: int):
        """Show a compact per-message token summary after each exchange."""
        pct = min(session_tokens / 80_000, 1.0)
        bar_color = "green" if pct < 0.5 else "yellow" if pct < 0.8 else "red"
        pct_str = f"{int(pct * 100)}%"
        warn = "  [yellow]⚠ context large — consider /clear[/yellow]" if pct > 0.75 else ""
        console.print(
            f"[dim]~{exchange_tokens:,} tokens this message  ·  "
            f"session ~{session_tokens:,}  ·  "
            f"[{bar_color}]{pct_str} of safe context[/{bar_color}]"
            f"{warn}[/dim]"
        )

    def show_memory_saved(self, category: str, snippet: str):
        short = snippet[:70] + "..." if len(snippet) > 70 else snippet
        console.print(
            f"\n[dim green]💾 Saved to memory  [{category}]  {short}[/dim green]"
        )

    def show_team(self, active_roster: list, personas: dict, skill_counts: dict | None = None):
        table = Table(
            title="Current Team Roster",
            show_header=True,
            header_style="bold",
            border_style="dim",
        )
        table.add_column("Role", style="dim")
        table.add_column("Name")
        table.add_column("@mention", style="cyan")
        table.add_column("Skills", style="dim", justify="right")
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
            mention = f"@{name.lower()}"
            count = str(skill_counts.get(role, 0)) if skill_counts else "—"
            table.add_row(
                role,
                f"{emoji} [{color}]{name}[/{color}]",
                mention,
                count,
                descriptions.get(role, "—"),
            )

        console.print()
        console.print(table)
        console.print()

    def show_skills(self, skills: dict, personas: dict):
        if not skills:
            console.print("\n[dim]No skills saved yet. Use /skill add <role> to teach the team.[/dim]\n")
            return
        console.print()
        for role, skill_list in skills.items():
            p = personas.get(role, {})
            name = p.get("name", role.upper())
            emoji = p.get("emoji", "")
            color = p.get("color", "white")
            console.rule(
                f"{emoji} [{color}]{name}[/{color}] [dim]({role}) — {len(skill_list)} skill(s)[/dim]",
                style=color
            )
            for skill in skill_list:
                console.print(f"  [cyan]•[/cyan] [bold]{skill['name']}[/bold]")
                if skill['preview']:
                    preview = skill['preview'][:100].replace('\n', ' ')
                    console.print(f"    [dim]{preview}…[/dim]")
            console.print()

    def show_status(self, project_name: str, info: dict | None, active_roster: list,
                    model: str, real_files: list, doc_files: list,
                    memory_entries: list, category_counts: dict,
                    total_skills: int, session_stats: dict):
        from rich.panel import Panel
        from pathlib import Path

        est_tokens = session_stats.get("estimated_tokens", 0)
        calls = session_stats.get("calls", 0)
        msg_count = info.get("message_count", 0) if info else 0
        last_active = info.get("last_active", "—") if info else "—"

        # Token bar
        token_pct = min(est_tokens / 80000, 1.0)
        bar_len = 20
        filled = int(bar_len * token_pct)
        bar_color = "green" if token_pct < 0.5 else "yellow" if token_pct < 0.8 else "red"
        bar = f"[{bar_color}]{'█' * filled}[/{bar_color}][dim]{'░' * (bar_len - filled)}[/dim]"

        # File list (cap at 8)
        if real_files:
            shown = real_files[:8]
            file_lines = "  ".join(f"[dim]{Path(f).name}[/dim]" for f in shown)
            if len(real_files) > 8:
                file_lines += f"  [dim]+{len(real_files)-8} more[/dim]"
        else:
            file_lines = "[dim]none yet[/dim]"

        # Memory summary
        mem_parts = [f"[cyan]{cat}[/cyan] {n}" for cat, n in category_counts.items()]
        mem_line = "  ".join(mem_parts) if mem_parts else "[dim]none yet[/dim]"

        lines = [
            f"[bold]Project:[/bold]  {project_name}",
            f"[bold]Messages:[/bold] {msg_count}  ·  Last active: [dim]{last_active}[/dim]",
            f"[bold]Team:[/bold]     {' · '.join(active_roster)}  [dim](model: {model})[/dim]",
            f"[bold]Skills:[/bold]   {total_skills} total across team",
            "",
            f"[bold]Memory[/bold] ({len(memory_entries)} items)",
            f"  {mem_line}",
            "",
            f"[bold]Files[/bold] ({len(real_files)} created · {len(doc_files)} docs)",
            f"  {file_lines}",
            "",
            f"[bold]Session[/bold]  {calls} calls · ~{est_tokens:,} tokens estimated",
            f"  {bar}  {int(token_pct*100)}% of safe context",
        ]
        if token_pct > 0.75:
            lines.append("\n  [yellow]⚠ Context getting large — consider /clear[/yellow]")

        console.print()
        console.print(Panel(
            "\n".join(lines),
            title=f"[bold]Status — {project_name}[/bold]",
            border_style="cyan",
            padding=(1, 2),
        ))
        console.print()

    def show_codebase_loaded(self, path, ctx: dict):
        from rich.panel import Panel
        tech = ", ".join(ctx.get("tech_stack", [])) or "unknown"
        total = ctx.get("total_files", "?")
        key_count = len(ctx.get("key_files", {}))
        tree = ctx.get("structure_tree", "")
        # Show first 30 lines of tree
        tree_preview = "\n".join(tree.splitlines()[:30])
        if len(tree.splitlines()) > 30:
            tree_preview += f"\n[dim]… +{len(tree.splitlines())-30} more[/dim]"

        console.print(Panel(
            f"[bold green]✓ Codebase loaded[/bold green]\n\n"
            f"[bold]Path:[/bold]       {path}\n"
            f"[bold]Tech stack:[/bold] [cyan]{tech}[/cyan]\n"
            f"[bold]Files:[/bold]      {total} total · {key_count} key files read\n\n"
            f"[bold]Structure:[/bold]\n[dim]{tree_preview}[/dim]\n\n"
            "[dim]Mode: [bold]READ-ONLY[/bold]  —  use [bold]/edit-mode on[/bold] to enable writes\n"
            "Agents see the full structure above. They can request specific files with READ_FILE:<path>.[/dim]",
            title="[bold]Codebase Loaded[/bold]",
            border_style="green",
            padding=(1, 2),
        ))
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
            "[bold]Talk to the team[/bold]\n"
            "  Just type naturally — Aria routes to the right agents automatically\n"
            "  [cyan]@sam build the login page[/cyan]    — talk directly to one agent\n"
            "  [cyan]@jordan review the API design[/cyan]\n"
            "  Press [bold]Ctrl+C[/bold] at any time to interrupt a running agent\n\n"
            "[bold]General Chat (no project needed)[/bold]\n"
            "  Just start typing a question or sentence and the team will answer\n"
            "  without creating a project. History is saved as [dim]💬 general chat[/dim].\n"
            "  Use [cyan]/new <name>[/cyan] or [cyan]/switch[/cyan] to move into a project anytime.\n\n"
            "[bold]Commands[/bold]\n"
            "  [cyan]/team[/cyan]              Show current team roster\n"
            "  [cyan]/add <role>[/cyan]        Add agent  (e.g. [dim]/add qa[/dim])\n"
            "  [cyan]/remove <role>[/cyan]     Remove agent  (e.g. [dim]/remove devops[/dim])\n"
            "  [cyan]/memory[/cyan]            Show project memory\n"
            "  [cyan]/history[/cyan]           Show recent conversation\n"
            "  [cyan]/clear[/cyan]             Clear context window (keeps memory)\n"
            "  [cyan]/skill list [role][/cyan]   List skills for a role (or all roles)\n"
            "  [cyan]/skill add <role>[/cyan]    Teach an agent a new skill\n"
            "  [cyan]/skill remove <role> <n>[/cyan] Remove a skill\n"
            "  [cyan]/export <type>[/cyan]     Generate a doc (requirements, architecture, sprint-plan…)\n"
            "  [cyan]/load <path>[/cyan]       Load an existing codebase for review or editing\n"
            "  [cyan]/unload[/cyan]            Unload the current codebase\n"
            "  [cyan]/edit-mode on|off[/cyan]  Enable/disable writes to the loaded codebase\n"
            "  [cyan]/model [alias][/cyan]     Show or change model  (haiku · sonnet · opus)\n"
            "  [cyan]/status[/cyan]            Project snapshot — files, memory, tokens, docs\n"
            "  [cyan]/project[/cyan]           Show current project info\n"
            "  [cyan]/switch [name][/cyan]     Switch to another project (shows picker if no name)\n"
            "  [cyan]/new <name>[/cyan]        Create and switch to a brand new project\n"
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
