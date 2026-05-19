from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console

from agents.agent import Agent
from utils.action_executor import parse_actions, prompt_and_execute
from utils.claude_client import call_claude, call_claude_json
from utils.db_manager import DBManager
from utils.display import Display
from utils.memory_manager import MemoryManager

console = Console()

ROLE_DESCRIPTIONS = {
    "pm": "Project planning, timelines, stakeholder management, scope",
    "bsa": "Requirements, user stories, process mapping, acceptance criteria",
    "developer": "Implementation, APIs, database design, code architecture",
    "lead": "Technical architecture, system design, technology selection, code review",
    "researcher": "Technology evaluation, best practices, comparative analysis",
    "qa": "Testing strategy, quality gates, test cases, bug taxonomy",
    "devops": "CI/CD pipelines, cloud infrastructure, deployments, monitoring",
}

# JSON schema the orchestrator uses to decide routing.
# Work is organised into sequential PHASES. Within each phase all agents
# run in parallel. Each phase's combined output is passed as context to
# the next phase, so Dev always receives completed requirements before
# starting, and QA always receives completed implementation before testing.
ROUTING_SCHEMA = {
    "type": "object",
    "properties": {
        "phases": {
            "type": "array",
            "description": (
                "Ordered list of work phases. Phases run one after another. "
                "Agents inside a phase run in parallel. "
                "Example: [{name:'Requirements', agents:['pm','bsa'], tasks:{...}}, "
                "{name:'Implementation', agents:['developer','lead'], tasks:{...}}, "
                "{name:'QA', agents:['qa'], tasks:{...}}]. "
                "Use a single phase when the work does not need sequencing."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Short label for this phase, e.g. 'Requirements', 'Implementation', 'QA'",
                    },
                    "agents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Roles to run in parallel during this phase (active team only)",
                    },
                    "tasks": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Specific task for each agent in this phase",
                    },
                },
                "required": ["name", "agents", "tasks"],
            },
        },
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "decision", "requirement", "technical",
                            "constraint", "assumption", "stakeholder",
                        ],
                    },
                },
                "required": ["content", "category"],
            },
            "description": "Facts to persist to project memory",
        },
        "team_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "remove"]},
                    "role": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["action", "role", "reason"],
            },
            "description": "Add or remove agents from the active roster",
        },
    },
    "required": ["phases"],
}


class Orchestrator:
    def __init__(
        self,
        project_name: str,
        base_dir: Path,
        db: DBManager,
        display: Display,
        model_override: Optional[str] = None,
    ):
        self.project_name = project_name
        self.base_dir = base_dir
        self.db = db
        self.display = display

        with open(base_dir / "config" / "settings.yaml", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.model = model_override or self.config.get("model", "sonnet")
        self.memory = MemoryManager(base_dir, project_name)
        self.active_roster: list[str] = list(self.config["team"]["default_roster"])

        # In-memory conversation log (user/assistant turns as plain dicts)
        history = db.load_history(
            project_name, limit=self.config.get("max_history_messages", 10)
        )
        self.messages: list[dict] = [
            {"role": m["role"], "content": m["content"]} for m in history
        ]

        # Instantiate all agents
        self.agents: dict[str, Agent] = {}
        all_roles = (
            self.config["team"]["default_roster"]
            + self.config["team"]["available_agents"]
        )
        for role in all_roles:
            persona = self.config["agent_personas"].get(role, {})
            self.agents[role] = Agent(
                role=role,
                persona=persona,
                base_dir=base_dir,
                memory=self.memory,
                model=self.model,
                orchestrator=self,
            )

        # True only for brand-new projects with no prior history.
        # Triggers auto-scaffolding after the first message.
        # Skipped for the _general chat workspace.
        self.is_new_project: bool = (
            len(history) == 0 and project_name != "_general"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_history(self) -> str:
        if not self.messages:
            return ""
        lines = []
        for m in self.messages[-6:]:
            label = "Customer" if m["role"] == "user" else "Team"
            content = m["content"][:600] + "…" if len(m["content"]) > 600 else m["content"]
            lines.append(f"[{label}]: {content}")
        return "\n".join(lines)

    def _routing_system_prompt(self) -> str:
        role_memory = self.memory.load_role_memory("orchestrator")
        project_memory = self.memory.load_project_memory()

        team_lines = [
            f"- {role} ({self.config['agent_personas'].get(role, {}).get('name', role)}): "
            f"{ROLE_DESCRIPTIONS.get(role, '')}"
            for role in self.active_roster
        ]
        available = [
            r
            for r in self.config["team"]["available_agents"]
            if r not in self.active_roster
        ]

        return (
            f"{role_memory}\n\n"
            f"## Project: {self.project_name}\n\n"
            f"## Project Memory\n{project_memory or 'None yet.'}\n\n"
            f"## Active Team\n" + "\n".join(team_lines) + "\n\n"
            f"## Available to Add\n{', '.join(available) or 'All agents active.'}\n\n"
            "## Routing Instructions\n"
            "Organise work into sequential PHASES when tasks have dependencies:\n"
            "  - Phase 1 (Requirements): pm + bsa gather requirements and write user stories\n"
            "  - Phase 2 (Implementation): developer + lead implement once requirements are done\n"
            "  - Phase 3 (QA): qa writes and runs tests once implementation is done\n"
            "  - Phase 4 (DevOps): devops deploys once QA passes\n"
            "Agents WITHIN a phase run in parallel. Each phase's output is fed as context "
            "into the next phase, so Dev always receives completed requirements and QA "
            "always receives completed implementation.\n"
            "Use a SINGLE phase when work does not need sequencing "
            "(e.g. simple questions, architectural discussions, research tasks).\n\n"
            "Return ONLY valid JSON matching the provided schema. "
            "Only include agents that are on the active team. "
            "If the message is a simple clarification or greeting, use an empty agents list."
        )

    def _synthesis_prompt(self, user_input: str, agent_responses: dict) -> str:
        parts = [
            f"The customer said:\n{user_input}\n\n"
            "The team has weighed in:\n"
        ]
        personas = self.config["agent_personas"]
        for role, response in agent_responses.items():
            name = personas.get(role, {}).get("name", role.upper())
            parts.append(f"[{name} — {role.upper()}]\n{response}\n")

        parts.append(
            "\nAs Aria, the coordinator, synthesize these into a clear, unified response "
            "for the customer. Be concise. Credit team members where relevant. "
            "If there are open questions for the customer, group them at the end."
        )
        return "\n".join(parts)

    def _scaffold_project(self, user_input: str, requirements_output: dict):
        """
        Run once after the first message of a new project.
        Developer + Lead propose and create the full folder/file structure.
        All file writes are permission-gated via the normal EXEC: flow.
        """
        personas = self.config["agent_personas"]
        project_dir = self.base_dir / "projects" / self.project_name

        console.print(
            "\n[bold bright_cyan]🏗️  Scaffolding project structure…[/bold bright_cyan]"
            "  [dim](Developer standards — you'll be asked before anything is written)[/dim]\n"
        )

        # Summarise what was gathered in the requirements phase
        req_summary = ""
        if requirements_output:
            parts = []
            for role, resp in requirements_output.items():
                name = personas.get(role, {}).get("name", role.upper())
                parts.append(f"[{name}]:\n{resp[:1000]}")
            req_summary = "\n\n".join(parts)

        scaffold_task = (
            f"Project name: {self.project_name}\n"
            f"Customer description: {user_input}\n\n"
            + (f"Requirements gathered so far:\n{req_summary}\n\n" if req_summary else "")
            + "Your job is to scaffold the complete project structure to developer standards.\n\n"
            "Create ALL of the following using EXEC:file: blocks:\n"
            "1. README.md — project name, one-line description, tech stack, setup steps, usage\n"
            "2. .gitignore — appropriate for the chosen tech stack\n"
            "3. .env.example — placeholder environment variables (no real secrets)\n"
            "4. Dependency file — package.json / requirements.txt / pom.xml / go.mod / etc.\n"
            "5. Folder structure — create a .gitkeep in each empty directory so it exists\n"
            "6. Entry point — e.g. src/index.js, src/main.py, src/App.tsx with basic boilerplate\n"
            "7. Any stack-specific config — tsconfig.json, .eslintrc, pytest.ini, Makefile, etc.\n\n"
            "Rules:\n"
            "- Infer the tech stack from the description. If ambiguous, pick sensible defaults.\n"
            "- Use relative paths from the project root.\n"
            "- Every file must have real starter content — no empty files except .gitkeep.\n"
            "- Follow the conventions of the chosen stack exactly.\n"
            "- Do NOT ask for permission or confirmation — output all EXEC: blocks now."
        )

        # Run Developer and Lead in parallel for scaffolding
        scaffold_roles = [r for r in ["developer", "lead"] if r in self.active_roster]
        if not scaffold_roles:
            scaffold_roles = self.active_roster[:1]

        def _scaffold_one(role: str) -> tuple[str, str]:
            agent = self.agents.get(role)
            if not agent:
                return role, ""
            return role, agent.respond(
                task=scaffold_task,
                context=f"Scaffolding new project: {self.project_name}",
                history_text="",
            )

        scaffold_responses: dict[str, str] = {}
        working = {r: personas.get(r, {}) for r in scaffold_roles}
        status_parts = [
            f"[{p.get('color','white')}]{p.get('emoji','')} {p.get('name', r)}[/{p.get('color','white')}]"
            for r, p in working.items()
        ]
        status_msg = "  ".join(status_parts) + "  [dim]scaffolding…[/dim]"

        try:
            with console.status(status_msg, spinner="dots"):
                with ThreadPoolExecutor(max_workers=len(scaffold_roles)) as pool:
                    futures = {pool.submit(_scaffold_one, r): r for r in scaffold_roles}
                    for future in as_completed(futures):
                        role, response = future.result()
                        if response:
                            scaffold_responses[role] = response
        except KeyboardInterrupt:
            console.print("\n[yellow]⚡ Scaffolding interrupted.[/yellow]")
            return

        # Display responses and execute permission-gated file writes
        for role, response in scaffold_responses.items():
            p = personas.get(role, {})
            self.display.show_agent_response(
                p.get("name", role.upper()), response, p.get("color", "white"), p.get("emoji", "")
            )
            actions = parse_actions(response, p.get("name", role.upper()))
            if actions:
                prompt_and_execute(actions, project_dir)

            self.memory.extract_and_save_memories(response, role)

        console.print(
            "\n[dim]🏗️  Scaffold complete — "
            "project structure is ready in [cyan]projects/"
            + self.project_name
            + "/[/cyan][/dim]\n"
        )

    # ------------------------------------------------------------------
    # Core routing
    # ------------------------------------------------------------------

    def _get_routing(self, user_input: str) -> dict:
        history_text = self._format_history()
        prompt_parts = []
        if history_text:
            prompt_parts.append(f"CONVERSATION HISTORY:\n{history_text}")
        prompt_parts.append(f"CUSTOMER MESSAGE:\n{user_input}")
        prompt_parts.append(
            f"ACTIVE TEAM: {', '.join(self.active_roster)}\n"
            "Decide which agents to consult, what to ask each, "
            "any memories to save, and any team changes needed."
        )
        prompt = "\n\n".join(prompt_parts)

        try:
            return call_claude_json(
                prompt=prompt,
                schema=ROUTING_SCHEMA,
                system_prompt=self._routing_system_prompt(),
                model=self.model,
            )
        except Exception as e:
            console.print(f"[dim yellow]Routing fallback (JSON parse error): {e}[/dim yellow]")
            # Route to the full active team in a single phase so nothing is silently dropped
            return {
                "phases": [
                    {
                        "name": "General",
                        "agents": list(self.active_roster),
                        "tasks": {r: user_input for r in self.active_roster},
                    }
                ]
            }

    # ------------------------------------------------------------------
    # Main entry: process one user message
    # ------------------------------------------------------------------

    def process(self, user_input: str):
        self.db.save_message(self.project_name, "user", user_input)
        self.messages.append({"role": "user", "content": user_input})

        # Capture explicit memory instructions from the customer
        for pat in [
            r"(?:please\s+)?remember\s+that\s+(.+)",
            r"(?:please\s+)?note\s+that\s+(.+)",
            r"keep\s+in\s+mind\s+that\s+(.+)",
        ]:
            m = re.search(pat, user_input, re.IGNORECASE)
            if m:
                saved = self.memory.save_project_memory(
                    content=m.group(1).strip(),
                    category="requirement",
                    source="customer",
                )
                if saved:
                    self.display.show_memory_saved("requirement", m.group(1).strip())

        console.print()
        with console.status("[bright_cyan]🎯 Aria is routing…[/bright_cyan]", spinner="dots"):
            routing = self._get_routing(user_input)

        # Apply team changes
        personas = self.config["agent_personas"]
        for change in routing.get("team_changes", []):
            action = change.get("action")
            role = change.get("role", "")
            reason = change.get("reason", "")
            p = personas.get(role, {})
            name = p.get("name", role.upper())
            if action == "add" and role not in self.active_roster and role in self.agents:
                self.active_roster.append(role)
                console.print(
                    f"[green]+ {p.get('emoji','')} {name} ({role}) joined the team[/green]"
                    f"  [dim]— {reason}[/dim]"
                )
            elif action == "remove" and role in self.active_roster:
                self.active_roster.remove(role)
                console.print(
                    f"[red]- {name} ({role}) left the team[/red]  [dim]— {reason}[/dim]"
                )

        # Save orchestrator-detected memories
        for mem in routing.get("memories", []):
            saved = self.memory.save_project_memory(
                content=mem.get("content", ""),
                category=mem.get("category", "note"),
                source="aria",
            )
            if saved:
                self.display.show_memory_saved(
                    mem.get("category", "note"), mem.get("content", "")
                )

        # ── Phase-aware execution ────────────────────────────────────────
        # Phases run sequentially. Agents within each phase run in parallel.
        # Each phase receives the previous phase's output as extra context.
        # ─────────────────────────────────────────────────────────────────
        phases: list[dict] = routing.get("phases", [])
        all_agent_responses: dict[str, str] = {}   # accumulated across all phases
        previous_phase_output: str = ""            # fed into the next phase as context
        project_dir = self.base_dir / "projects" / self.project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        def _call_one(role: str, task: str, ctx: str) -> tuple[str, str]:
            """Run one agent and return (role, response). Thread-safe."""
            agent = self.agents.get(role)
            if not agent:
                return role, "(agent not found)"
            return role, agent.respond(
                task=task,
                context=ctx,
                history_text=self._format_history(),
            )

        for phase_idx, phase in enumerate(phases):
            phase_name = phase.get("name", f"Phase {phase_idx + 1}")
            agents_to_call = [r for r in phase.get("agents", []) if r in self.active_roster]
            if not agents_to_call:
                continue

            # Build context for this phase: customer message + anything from prior phases
            phase_context = f"Customer said: {user_input}"
            if previous_phase_output:
                phase_context += f"\n\nOutput from previous phase:\n{previous_phase_output}"

            # Status line showing which agents are working in this phase
            working = {r: personas.get(r, {}) for r in agents_to_call}
            status_parts = [
                f"[{p.get('color','white')}]{p.get('emoji','')} {p.get('name', r)}[/{p.get('color','white')}]"
                for r, p in working.items()
            ]
            phase_label = f"[dim]({phase_name})[/dim]" if len(phases) > 1 else ""
            status_msg = "  ".join(status_parts) + f"  [dim]working in parallel…[/dim]  {phase_label}"

            phase_responses: dict[str, str] = {}
            try:
                with console.status(status_msg, spinner="dots"):
                    with ThreadPoolExecutor(max_workers=len(agents_to_call)) as pool:
                        task_map = phase.get("tasks", {})
                        futures = {
                            pool.submit(_call_one, r, task_map.get(r, user_input), phase_context): r
                            for r in agents_to_call
                        }
                        for future in as_completed(futures):
                            role, response = future.result()
                            phase_responses[role] = response
            except KeyboardInterrupt:
                console.print("\n[yellow]⚡ Interrupted — returning to prompt.[/yellow]")
                console.print()
                return

            # Display this phase's results; handle permission-gated actions
            for role, response in phase_responses.items():
                p = personas.get(role, {})
                name = p.get("name", role.upper())
                color = p.get("color", "white")
                emoji = p.get("emoji", "")

                self.display.show_agent_response(name, response, color, emoji)

                # Permission-gated action execution
                actions = parse_actions(response, name)
                if actions:
                    outcomes = prompt_and_execute(actions, project_dir)
                    if outcomes:
                        phase_responses[role] += "\n\nACTIONS TAKEN:\n" + "\n".join(outcomes)

                # Auto-extract REMEMBER: markers
                saved_count = self.memory.extract_and_save_memories(response, role)
                if saved_count:
                    console.print(
                        f"[dim green]  (💾 {saved_count} memory item(s) from {name})[/dim green]"
                    )

            all_agent_responses.update(phase_responses)

            # Build context summary for the next phase from this phase's output
            phase_summary_parts = []
            for role, resp in phase_responses.items():
                agent_name = personas.get(role, {}).get("name", role.upper())
                phase_summary_parts.append(f"[{agent_name}]:\n{resp[:1200]}")
            previous_phase_output = "\n\n".join(phase_summary_parts)

            # Print a phase separator when there are multiple phases and more to come
            if len(phases) > 1 and phase_idx < len(phases) - 1:
                console.print(
                    f"\n[dim]── {phase_name} complete · handing off to next phase ──[/dim]\n"
                )

        # alias for synthesis block below
        agent_responses = all_agent_responses

        # ── Auto-scaffold on first message of a new project ───────────
        if self.is_new_project and agent_responses:
            self.is_new_project = False  # only once per project lifetime
            self._scaffold_project(user_input, agent_responses)

        # Synthesize if multiple agents responded; otherwise Aria speaks directly
        final_response = ""
        if len(agent_responses) > 1:
            with console.status("[bright_cyan]🎯 Aria is synthesizing…[/bright_cyan]", spinner="dots"):
                synth_prompt = self._synthesis_prompt(user_input, agent_responses)
                try:
                    final_response = call_claude(
                        prompt=synth_prompt,
                        system_prompt=self.memory.load_role_memory("orchestrator"),
                        model=self.model,
                    )
                except Exception as e:
                    final_response = ""
                    console.print(f"[dim yellow]Synthesis skipped: {e}[/dim yellow]")
        elif len(agent_responses) == 0:
            # No agents called — Aria answers directly
            with console.status("[bright_cyan]🎯 Aria is responding…[/bright_cyan]", spinner="dots"):
                try:
                    final_response = call_claude(
                        prompt=(
                            f"{self._format_history()}\n\nCustomer: {user_input}\n\n"
                            "Respond as Aria, the project coordinator."
                        ),
                        system_prompt=self.memory.load_role_memory("orchestrator"),
                        model=self.model,
                    )
                except Exception as e:
                    final_response = f"(error: {e})"

        if final_response.strip():
            self.display.show_orchestrator_response(final_response)

        # Persist to DB and in-memory log
        combined = final_response or "\n\n".join(
            f"[{r}]: {resp}" for r, resp in agent_responses.items()
        )
        if combined:
            self.db.save_message(self.project_name, "assistant", combined)
            self.messages.append({"role": "assistant", "content": combined})
        else:
            console.print("[dim yellow]No response generated. Try rephrasing your message.[/dim yellow]")

        console.print()

    # ------------------------------------------------------------------
    # Direct @mention: bypass routing, talk to one agent directly
    # ------------------------------------------------------------------

    def _resolve_role(self, identifier: str) -> str | None:
        """
        Resolve an @mention identifier to an agent role key.
        Accepts either the role key ("developer") or the persona name ("sam").
        Returns None if no match found.
        """
        # Direct role key match
        if identifier in self.agents:
            return identifier
        # Match by persona name (case-insensitive)
        for role, persona in self.config["agent_personas"].items():
            if persona.get("name", "").lower() == identifier.lower():
                return role
        return None

    def direct_message(self, role: str, message: str):
        """Send a message directly to one named agent, skipping Aria's routing."""
        # Accept both role keys ("developer") and persona names ("sam")
        resolved = self._resolve_role(role)
        if not resolved:
            names = ", ".join(
                f"@{p.get('name','').lower()} ({r})"
                for r, p in self.config["agent_personas"].items()
                if r != "orchestrator"
            )
            console.print(
                f"[red]Unknown agent:[/red] [bold]@{role}[/bold]\n"
                f"[dim]Available: {names}[/dim]"
            )
            return
        role = resolved

        agent = self.agents.get(role)
        if not agent:
            console.print(f"[red]Agent not initialised: {role}[/red]")
            return
        if role not in self.active_roster:
            p_name = self.config["agent_personas"].get(role, {}).get("name", role)
            console.print(
                f"[yellow]{p_name} ({role}) is not on the active team. "
                f"Use /add {role} first.[/yellow]"
            )
            return

        p = self.config["agent_personas"].get(role, {})
        name = p.get("name", role.upper())
        color = p.get("color", "white")
        emoji = p.get("emoji", "")

        self.db.save_message(self.project_name, "user", f"@{role}: {message}")
        self.messages.append({"role": "user", "content": f"@{role}: {message}"})

        console.print()
        try:
            with console.status(
                f"[{color}]{emoji} {name} is working…[/{color}]", spinner="dots"
            ):
                response = agent.respond(
                    task=message,
                    context=f"The customer is speaking directly to you.",
                    history_text=self._format_history(),
                )
        except KeyboardInterrupt:
            console.print("\n[yellow]⚡ Interrupted.[/yellow]")
            console.print()
            return

        self.display.show_agent_response(name, response, color, emoji)

        project_dir = self.base_dir / "projects" / self.project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        actions = parse_actions(response, name)
        if actions:
            outcomes = prompt_and_execute(actions, project_dir)
            if outcomes:
                response += "\n\nACTIONS TAKEN:\n" + "\n".join(outcomes)

        self.memory.extract_and_save_memories(response, role)
        self.db.save_message(self.project_name, "assistant", response)
        self.messages.append({"role": "assistant", "content": response})
        console.print()

    # ------------------------------------------------------------------
    # Slash command handlers
    # ------------------------------------------------------------------

    def add_agent(self, role: str):
        p = self.config["agent_personas"]
        if role in self.active_roster:
            console.print(f"[yellow]{role} is already on the team.[/yellow]")
        elif role in p:
            self.active_roster.append(role)
            persona = p[role]
            console.print(
                f"[green]+ {persona.get('emoji','')} {persona.get('name', role)} ({role}) added.[/green]"
            )
        else:
            console.print(
                f"[red]Unknown role: {role}[/red]  "
                f"Available: {', '.join(ROLE_DESCRIPTIONS.keys())}"
            )

    def remove_agent(self, role: str):
        p = self.config["agent_personas"]
        if role not in self.active_roster:
            console.print(f"[yellow]{role} is not on the team.[/yellow]")
        else:
            self.active_roster.remove(role)
            persona = p.get(role, {})
            console.print(
                f"[red]- {persona.get('name', role)} ({role}) removed.[/red]"
            )

    def show_team(self):
        self.display.show_team(self.active_roster, self.config["agent_personas"])

    def show_memory(self):
        self.display.show_memory(self.memory.list_memory_entries(), self.project_name)

    def show_history(self, limit: int = 10):
        self.display.show_history(self.db.load_history(self.project_name, limit=limit))

    def show_project_info(self):
        info = self.db.get_project(self.project_name)
        console.print(f"\n[bold]Project:[/bold] {self.project_name}")
        if info:
            console.print(f"  Messages:     {info['message_count']}")
            console.print(f"  Last active:  {info.get('last_active', '—')}")
        console.print(f"  Memory items: {len(self.memory.list_memory_entries())}")
        console.print(f"  Active team:  {', '.join(self.active_roster)}")
        console.print(f"  Model:        {self.model}")
        console.print()

    def clear_context(self):
        self.messages = []
        console.print("[dim]Context cleared. DB history and project memory preserved.[/dim]")
