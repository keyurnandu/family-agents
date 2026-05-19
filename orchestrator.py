from __future__ import annotations

from pathlib import Path
from typing import Optional

import anthropic
import yaml
from rich.console import Console

from agents.agent import Agent
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

        self.model = model_override or self.config["model"]
        self.client = anthropic.Anthropic()
        self.memory = MemoryManager(base_dir, project_name)

        self.active_roster: list[str] = list(self.config["team"]["default_roster"])

        # Load conversation history from DB
        history = db.load_history(project_name, limit=self.config.get("max_history_messages", 10))
        self.messages: list[dict] = [
            {"role": m["role"], "content": m["content"]} for m in history
        ]

        # Instantiate all agents up front
        self.agents: dict[str, Agent] = {}
        for role in (
            self.config["team"]["default_roster"]
            + self.config["team"]["available_agents"]
        ):
            persona = self.config["agent_personas"].get(role, {})
            self.agents[role] = Agent(
                role=role,
                persona=persona,
                base_dir=base_dir,
                memory=self.memory,
                model=self.model,
                client=self.client,
                orchestrator=self,
            )

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------
    def _build_system_prompt(self) -> str:
        role_memory = self.memory.load_role_memory("orchestrator")
        project_memory = self.memory.load_project_memory()
        personas = self.config["agent_personas"]

        team_lines = []
        for role in self.active_roster:
            p = personas.get(role, {})
            name = p.get("name", role.upper())
            team_lines.append(f"- {name} ({role.upper()}): {ROLE_DESCRIPTIONS.get(role, '')}")
        team_str = "\n".join(team_lines) if team_lines else "No active team members."

        available = [
            r
            for r in self.config["team"]["available_agents"]
            if r not in self.active_roster
        ]

        memory_section = (
            f"## Project Memory\n{project_memory}"
            if project_memory
            else "## Project Memory\nNone recorded yet."
        )

        return (
            f"{role_memory}\n\n"
            f"## Project: {self.project_name}\n\n"
            f"{memory_section}\n\n"
            f"## Active Team\n{team_str}\n\n"
            f"## Available to Add\n{', '.join(available) if available else 'All agents are active.'}\n\n"
            "## Instructions\n"
            "- Route work to the right specialists via `consult_agent`\n"
            "- Save important decisions and requirements via `save_to_memory`\n"
            "- Manage the team roster via `update_team` when complexity changes\n"
            "- After collecting specialist input, synthesize a clear response for the customer\n"
            "- If the customer says 'remember', 'note that', or states a key constraint, save it immediately\n"
        )

    # ------------------------------------------------------------------
    # Tool definitions
    # ------------------------------------------------------------------
    def _get_tools(self) -> list:
        all_roles = list(ROLE_DESCRIPTIONS.keys())
        categories = ["decision", "requirement", "technical", "constraint", "assumption", "stakeholder"]

        return [
            {
                "name": "consult_agent",
                "description": (
                    "Consult a specialist team member for their expert contribution. "
                    "Call once per specialist needed. Only consult agents on the active team."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "agent_role": {
                            "type": "string",
                            "enum": all_roles,
                        },
                        "task": {
                            "type": "string",
                            "description": "What you need from this agent — be specific",
                        },
                        "context": {
                            "type": "string",
                            "description": "Relevant context from the customer message",
                        },
                    },
                    "required": ["agent_role", "task", "context"],
                },
            },
            {
                "name": "save_to_memory",
                "description": (
                    "Persist an important fact, decision, requirement, or constraint "
                    "to project memory so it survives across sessions."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The fact or decision to save",
                        },
                        "category": {
                            "type": "string",
                            "enum": categories,
                        },
                    },
                    "required": ["content", "category"],
                },
            },
            {
                "name": "update_team",
                "description": (
                    "Add or remove an agent from the active team roster based on project needs."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["add", "remove"]},
                        "agent_role": {
                            "type": "string",
                            "description": "Role to add or remove",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why this change is warranted",
                        },
                    },
                    "required": ["action", "agent_role", "reason"],
                },
            },
        ]

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------
    def _handle_tool(self, tool_name: str, tool_input: dict) -> str:
        personas = self.config["agent_personas"]

        if tool_name == "consult_agent":
            role = tool_input["agent_role"]
            if role not in self.active_roster:
                return (
                    f"'{role}' is not on the active team. "
                    "Add them via update_team first, or pick an active team member."
                )
            agent = self.agents.get(role)
            if not agent:
                return f"Agent '{role}' not found."

            p = personas.get(role, {})
            name = p.get("name", role.upper())
            color = p.get("color", "white")
            emoji = p.get("emoji", "")

            with console.status(
                f"[{color}]{emoji} {name} is thinking…[/{color}]", spinner="dots"
            ):
                agent_response = agent.respond(
                    task=tool_input["task"],
                    context=tool_input["context"],
                    conversation_history=self.messages,
                )

            self.display.show_agent_response(name, agent_response, color, emoji)

            # Auto-extract REMEMBER: markers
            saved = self.memory.extract_and_save_memories(agent_response, role)
            if saved:
                console.print(
                    f"[dim green]  (💾 {saved} memory item(s) captured from {name})[/dim green]"
                )

            return agent_response

        elif tool_name == "save_to_memory":
            content = tool_input["content"]
            category = tool_input["category"]
            did_save = self.memory.save_project_memory(
                content=content, category=category, source="aria"
            )
            if did_save:
                self.display.show_memory_saved(category, content)
            return f"Saved: {content}"

        elif tool_name == "update_team":
            action = tool_input["action"]
            role = tool_input["agent_role"]
            reason = tool_input.get("reason", "")
            p = personas.get(role, {})
            name = p.get("name", role.upper())

            if action == "add":
                if role not in self.active_roster:
                    self.active_roster.append(role)
                    console.print(
                        f"\n[green]+ {p.get('emoji','')} {name} ({role}) joined the team[/green]"
                        f"  [dim]— {reason}[/dim]"
                    )
                    return f"Added {role} to team."
                return f"{role} already on team."

            elif action == "remove":
                if role in self.active_roster:
                    self.active_roster.remove(role)
                    console.print(
                        f"\n[red]- {name} ({role}) removed from team[/red]"
                        f"  [dim]— {reason}[/dim]"
                    )
                    return f"Removed {role} from team."
                return f"{role} not on team."

        return "Unknown tool."

    # ------------------------------------------------------------------
    # Main entry point: process a user message
    # ------------------------------------------------------------------
    def process(self, user_input: str):
        self.db.save_message(self.project_name, "user", user_input)
        self.messages.append({"role": "user", "content": user_input})

        # Check for explicit memory instructions from the customer
        import re
        explicit_patterns = [
            r"(?:please\s+)?remember\s+that\s+(.+)",
            r"(?:please\s+)?note\s+that\s+(.+)",
            r"(?:keep\s+in\s+mind\s+that\s+)(.+)",
        ]
        for pat in explicit_patterns:
            m = re.search(pat, user_input, re.IGNORECASE)
            if m:
                self.memory.save_project_memory(
                    content=m.group(1).strip(),
                    category="requirement",
                    source="customer",
                )
                self.display.show_memory_saved("requirement", m.group(1).strip())

        system_prompt = self._build_system_prompt()
        tools = self._get_tools()

        loop_messages = list(self.messages)
        final_response = ""
        iterations = 0
        max_iter = self.config.get("max_tool_iterations", 12)

        console.print()

        while iterations < max_iter:
            iterations += 1
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.config.get("max_tokens", 4096),
                system=system_prompt,
                messages=loop_messages,
                tools=tools,
            )

            if response.stop_reason == "end_turn":
                parts = [b.text for b in response.content if hasattr(b, "text")]
                final_response = "\n".join(parts)
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                loop_messages.append({"role": "assistant", "content": response.content})

                for block in response.content:
                    if block.type == "tool_use":
                        result = self._handle_tool(block.name, block.input)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )

                loop_messages.append({"role": "user", "content": tool_results})
            else:
                break

        if final_response.strip():
            self.display.show_orchestrator_response(final_response)
            self.db.save_message(self.project_name, "assistant", final_response)
            self.messages.append({"role": "assistant", "content": final_response})

        console.print()

    # ------------------------------------------------------------------
    # Slash command handlers
    # ------------------------------------------------------------------
    def add_agent(self, role: str):
        personas = self.config["agent_personas"]
        if role in self.active_roster:
            console.print(f"[yellow]{role} is already on the team.[/yellow]")
        elif role in personas:
            self.active_roster.append(role)
            p = personas[role]
            console.print(
                f"[green]+ {p.get('emoji','')} {p.get('name', role)} ({role}) added to team.[/green]"
            )
        else:
            console.print(
                f"[red]Unknown role: {role}[/red]  "
                f"Available: {', '.join(ROLE_DESCRIPTIONS.keys())}"
            )

    def remove_agent(self, role: str):
        personas = self.config["agent_personas"]
        if role not in self.active_roster:
            console.print(f"[yellow]{role} is not currently on the team.[/yellow]")
        else:
            self.active_roster.remove(role)
            p = personas.get(role, {})
            console.print(
                f"[red]- {p.get('name', role)} ({role}) removed from team.[/red]"
            )

    def show_team(self):
        self.display.show_team(self.active_roster, self.config["agent_personas"])

    def show_memory(self):
        entries = self.memory.list_memory_entries()
        self.display.show_memory(entries, self.project_name)

    def show_history(self, limit: int = 10):
        history = self.db.load_history(self.project_name, limit=limit)
        self.display.show_history(history)

    def show_project_info(self):
        info = self.db.get_project(self.project_name)
        console.print(f"\n[bold]Project:[/bold] {self.project_name}")
        if info:
            console.print(f"  Messages:     {info['message_count']}")
            console.print(f"  Last active:  {info.get('last_active', 'unknown')}")
        mem_entries = self.memory.list_memory_entries()
        console.print(f"  Memory items: {len(mem_entries)}")
        console.print(f"  Active team:  {', '.join(self.active_roster)}")
        console.print()

    def clear_context(self):
        self.messages = []
        console.print(
            "[dim]Context window cleared. Project memory and DB history preserved.[/dim]"
        )
