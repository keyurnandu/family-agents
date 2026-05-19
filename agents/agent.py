from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import anthropic

if TYPE_CHECKING:
    from utils.memory_manager import MemoryManager

ALL_ROLES = ["pm", "bsa", "developer", "lead", "researcher", "qa", "devops"]


class Agent:
    """A specialist agent representing one team member role."""

    def __init__(
        self,
        role: str,
        persona: dict,
        base_dir: Path,
        memory: "MemoryManager",
        model: str,
        client: anthropic.Anthropic,
        orchestrator=None,
    ):
        self.role = role
        self.persona = persona
        self.base_dir = base_dir
        self.memory = memory
        self.model = model
        self.client = client
        self.orchestrator = orchestrator  # back-reference for peer consultation

        self.name = persona.get("name", role.upper())
        self.color = persona.get("color", "white")
        self.emoji = persona.get("emoji", "")

    def _build_system_prompt(self) -> str:
        role_memory = self.memory.load_role_memory(self.role)
        project_memory = self.memory.load_project_memory()

        project_section = (
            f"## Project Memory\n{project_memory}"
            if project_memory
            else "## Project Memory\nNo project memory recorded yet."
        )

        return (
            f"You are {self.name}, a {self.role.upper()} on a software development team.\n\n"
            f"{role_memory}\n\n"
            f"{project_section}\n\n"
            "## Working Instructions\n"
            "- Stay in your role — answer from your domain's perspective\n"
            "- Be specific and actionable; avoid vague generalities\n"
            "- Ask clarifying questions if requirements are ambiguous\n"
            "- Use `consult_colleague` when you genuinely need a peer's expertise\n"
            "- If you identify something that must be remembered across sessions, "
            "prefix it with REMEMBER: on its own line\n"
        )

    def _peer_tools(self) -> list:
        colleagues = [r for r in ALL_ROLES if r != self.role]
        return [
            {
                "name": "consult_colleague",
                "description": (
                    "Ask a specific colleague for their expert input on a question "
                    "that falls outside your own domain."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "colleague_role": {
                            "type": "string",
                            "enum": colleagues,
                            "description": "The role of the colleague to consult",
                        },
                        "question": {
                            "type": "string",
                            "description": "The specific question for your colleague",
                        },
                    },
                    "required": ["colleague_role", "question"],
                },
            }
        ]

    # ------------------------------------------------------------------
    # Internal: simple response (no peer consultation, used for peer calls)
    # ------------------------------------------------------------------
    def _respond_simple(self, task: str, context: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self._build_system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": f"Context from a colleague:\n{context}\n\nQuestion: {task}",
                }
            ],
        )
        return response.content[0].text if response.content else "(no response)"

    # ------------------------------------------------------------------
    # Internal: handle a peer consultation request
    # ------------------------------------------------------------------
    def _consult_peer(self, colleague_role: str, question: str) -> str:
        if not self.orchestrator:
            return f"Peer consultation unavailable (no orchestrator reference)."

        active = getattr(self.orchestrator, "active_roster", [])
        if colleague_role not in active:
            return (
                f"{colleague_role} is not currently on the team. "
                "I'll proceed with the information I have."
            )

        peer: Agent | None = self.orchestrator.agents.get(colleague_role)
        if not peer:
            return f"Could not locate {colleague_role} agent."

        return peer._respond_simple(
            task=question,
            context=f"Asked by {self.name} ({self.role})",
        )

    # ------------------------------------------------------------------
    # Public: full response with optional peer consultation
    # ------------------------------------------------------------------
    def respond(self, task: str, context: str, conversation_history: list) -> str:
        system_prompt = self._build_system_prompt()
        tools = self._peer_tools()

        # Use the last few turns for context; filter to simple string content only
        recent = [
            m
            for m in conversation_history[-8:]
            if isinstance(m.get("content"), str)
        ]

        task_msg = (
            f"The project coordinator has assigned you this task:\n\n"
            f"{task}\n\n"
            f"Coordinator context:\n{context}"
        )
        messages = recent + [{"role": "user", "content": task_msg}]

        loop_messages = messages
        iterations = 0
        max_iterations = 6

        while iterations < max_iterations:
            iterations += 1
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                messages=loop_messages,
                tools=tools,
            )

            if response.stop_reason == "end_turn":
                parts = [b.text for b in response.content if hasattr(b, "text")]
                return "\n".join(parts) or "(no response)"

            if response.stop_reason == "tool_use":
                tool_results = []
                loop_messages = loop_messages + [
                    {"role": "assistant", "content": response.content}
                ]

                for block in response.content:
                    if block.type == "tool_use" and block.name == "consult_colleague":
                        result = self._consult_peer(
                            colleague_role=block.input["colleague_role"],
                            question=block.input["question"],
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )

                loop_messages = loop_messages + [
                    {"role": "user", "content": tool_results}
                ]
            else:
                break

        return "(agent did not produce a final response)"
