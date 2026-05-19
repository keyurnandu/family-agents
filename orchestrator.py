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

# JSON schema the orchestrator uses to decide routing
ROUTING_SCHEMA = {
    "type": "object",
    "properties": {
        "agents": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Roles to consult (only from active team)",
        },
        "tasks": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": "Specific task string for each agent role",
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
                            "decision",
                            "requirement",
                            "technical",
                            "constraint",
                            "assumption",
                            "stakeholder",
                        ],
                    },
                },
                "required": ["content", "category"],
            },
            "description": "Facts that must be persisted to project memory",
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
            "description": "Add or remove agents based on project needs",
        },
    },
    "required": ["agents", "tasks"],
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
            "Return ONLY valid JSON matching the provided schema. "
            "Only include agents that are on the active team. "
            "If the message is a simple clarification or greeting, agents list can be empty."
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
            # Route to the full active team so no agents are silently dropped
            return {
                "agents": list(self.active_roster),
                "tasks": {r: user_input for r in self.active_roster},
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

        # Call agents — in parallel when there are multiple
        agent_responses: dict[str, str] = {}
        history_text = self._format_history()
        agents_to_call = [r for r in routing.get("agents", []) if r in self.active_roster]

        def _call_one(role: str) -> tuple[str, str]:
            """Run one agent and return (role, response). Thread-safe."""
            agent = self.agents.get(role)
            if not agent:
                return role, "(agent not found)"
            task = routing.get("tasks", {}).get(role, user_input)
            return role, agent.respond(
                task=task,
                context=f"Customer said: {user_input}",
                history_text=history_text,
            )

        if agents_to_call:
            # Build a live status line listing every agent that is currently working
            working = {r: personas.get(r, {}) for r in agents_to_call}
            status_parts = [
                f"[{p.get('color','white')}]{p.get('emoji','')} {p.get('name', r)}[/{p.get('color','white')}]"
                for r, p in working.items()
            ]
            status_msg = "  ".join(status_parts) + "  [dim]working in parallel…[/dim]"

            try:
                with console.status(status_msg, spinner="dots"):
                    with ThreadPoolExecutor(max_workers=len(agents_to_call)) as pool:
                        futures = {pool.submit(_call_one, r): r for r in agents_to_call}
                        for future in as_completed(futures):
                            role, response = future.result()
                            agent_responses[role] = response
            except KeyboardInterrupt:
                console.print("\n[yellow]⚡ Interrupted — returning to prompt.[/yellow]")
                console.print()
                return

        # Display results and handle actions (sequentially — needs user interaction)
        project_dir = self.base_dir / "projects" / self.project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        for role, response in agent_responses.items():
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
                    agent_responses[role] += "\n\nACTIONS TAKEN:\n" + "\n".join(outcomes)

            # Auto-extract REMEMBER: markers
            saved_count = self.memory.extract_and_save_memories(response, role)
            if saved_count:
                console.print(
                    f"[dim green]  (💾 {saved_count} memory item(s) from {name})[/dim green]"
                )

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

    def direct_message(self, role: str, message: str):
        """Send a message directly to one named agent, skipping Aria's routing."""
        agent = self.agents.get(role)
        if not agent:
            console.print(f"[red]Unknown role: {role}[/red]")
            return
        if role not in self.active_roster:
            console.print(
                f"[yellow]{role} is not on the active team. "
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
