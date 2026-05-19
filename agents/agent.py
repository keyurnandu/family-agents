from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from utils.claude_client import call_claude

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
        orchestrator=None,
    ):
        self.role = role
        self.persona = persona
        self.base_dir = base_dir
        self.memory = memory
        self.model = model
        self.orchestrator = orchestrator

        self.name = persona.get("name", role.upper())
        self.color = persona.get("color", "white")
        self.emoji = persona.get("emoji", "")

    def _build_system_prompt(self) -> str:
        role_memory = self.memory.load_role_memory(self.role)
        project_memory = self.memory.load_project_memory()

        project_section = (
            f"## Project Memory\n{project_memory}"
            if project_memory
            else "## Project Memory\nNone yet."
        )

        return "\n\n".join([
            f"You are {self.name}, a {self.role.upper()} on a software development team.",

            # Hard constraint — must come before role memory so it takes priority
            "## CRITICAL CONSTRAINT\n"
            "You are running as a TEXT-ONLY agent. "
            "You have NO access to Write, Edit, Read, Bash, or any file-system tools. "
            "Do NOT attempt to call any tools. "
            "Do NOT mention Claude Code, settings.json, .claude folders, or permission dialogs — "
            "none of that applies here. "
            "The ONLY way to deliver files or run commands is via EXEC: tagged blocks in your text.",

            role_memory,
            project_section,

            "## Working Instructions\n"
            "- Stay in your domain — answer from your role's perspective\n"
            "- Be specific and actionable\n"
            "- Ask clarifying questions when requirements are ambiguous\n"
            "- Prefix persistent facts with REMEMBER:\n"
            "- Prefix peer questions with ASK_COLLEAGUE:<role>: <question>",

            "## Delivering Files and Commands\n"
            "Output EXEC: blocks and the system will show the customer a permission prompt "
            "before anything is executed.\n"
            "\n"
            "Write a file:\n"
            "EXEC:file:path/to/file.ext\n"
            "```\n"
            "<full file content>\n"
            "```\n"
            "\n"
            "Run a shell command:\n"
            "EXEC:bash\n"
            "```\n"
            "<commands>\n"
            "```\n"
            "\n"
            "- Explain what you are doing BEFORE each EXEC: block\n"
            "- Always include the COMPLETE file content, never a partial snippet\n"
            "- Use relative paths from the project root\n"
            "- If it should exist on disk, it MUST be in an EXEC: block — no exceptions",
        ])

    def _get_peer_input(self, colleague_role: str, question: str) -> str:
        """Ask a peer agent a single question (no further nesting)."""
        if not self.orchestrator:
            return "(peer consultation unavailable)"

        active = getattr(self.orchestrator, "active_roster", [])
        if colleague_role not in active:
            return f"({colleague_role} is not on the active team)"

        peer: Agent | None = self.orchestrator.agents.get(colleague_role)
        if not peer:
            return f"(agent {colleague_role} not found)"

        peer_system = peer._build_system_prompt()
        prompt = (
            f"Your colleague {self.name} ({self.role}) asks:\n\n"
            f"{question}\n\n"
            "Give a concise, expert answer from your role's perspective."
        )
        try:
            return call_claude(prompt=prompt, system_prompt=peer_system, model=self.model)
        except Exception as e:
            return f"(peer consultation failed: {e})"

    def respond(self, task: str, context: str, history_text: str) -> str:
        """Generate a response, handling one round of peer consultation if needed."""
        import re
        system_prompt = self._build_system_prompt()

        prompt_parts = []
        if history_text:
            prompt_parts.append(f"CONVERSATION HISTORY:\n{history_text}")
        if context:
            prompt_parts.append(f"CONTEXT:\n{context}")
        prompt_parts.append(f"YOUR TASK:\n{task}")
        prompt = "\n\n".join(prompt_parts)

        try:
            response = call_claude(prompt=prompt, system_prompt=system_prompt, model=self.model)
        except Exception as e:
            return f"(error calling {self.name}: {e})"

        # Handle ASK_COLLEAGUE markers (one round only)
        colleagues_needed = re.findall(
            r"ASK_COLLEAGUE:(\w+):\s*(.+?)(?=\nASK_COLLEAGUE:|$)", response, re.DOTALL
        )
        if not colleagues_needed:
            return response

        enriched_prompt = (
            f"{prompt}\n\n"
            "You previously indicated needing colleague input. Here are their answers:\n"
        )
        for colleague_role, question in colleagues_needed:
            answer = self._get_peer_input(colleague_role.strip(), question.strip())
            enriched_prompt += f"\n[{colleague_role.upper()}]: {answer}\n"

        enriched_prompt += "\nNow provide your complete response incorporating this input."

        try:
            return call_claude(
                prompt=enriched_prompt, system_prompt=system_prompt, model=self.model
            )
        except Exception as e:
            return response
