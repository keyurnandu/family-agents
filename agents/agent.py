from __future__ import annotations

import re
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
        max_mem = 40
        if self.orchestrator:
            max_mem = getattr(self.orchestrator, "config", {}).get("max_memory_entries", 40)
        project_memory = self.memory.load_project_memory(limit=max_mem)

        project_section = (
            f"## Project Memory\n{project_memory}"
            if project_memory
            else "## Project Memory\nNone yet."
        )

        skills_text = self.memory.load_skills(self.role)

        sections = [
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
        ]
        if skills_text:
            sections.append(f"## Additional Skills & Expertise\n{skills_text}")

        # Inject previously exported project documents (requirements, sprint plans, etc.)
        docs_text = self.memory.load_project_docs()
        if docs_text:
            sections.append(
                "## Project Documents\n"
                + docs_text
            )

        # Inject loaded codebase context
        if self.orchestrator:
            loaded_path = getattr(self.orchestrator, "loaded_path", None)
            ctx = getattr(self.orchestrator, "codebase_context", {})
            edit_mode = getattr(self.orchestrator, "edit_mode", False)
            if loaded_path and ctx:
                codebase_lines = [
                    f"## Loaded Codebase: {loaded_path}",
                    f"Tech stack: {', '.join(ctx.get('tech_stack', [])) or 'unknown'}",
                    f"Total files: {ctx.get('total_files', '?')}",
                    "",
                    "### Folder Structure",
                    "```",
                    ctx.get("structure_tree", ""),
                    "```",
                ]
                for fname, content in ctx.get("key_files", {}).items():
                    codebase_lines += [f"\n### {fname}", "```", content, "```"]
                codebase_lines += [
                    "",
                    "### Accessing and editing files",
                    f"The codebase is at: {loaded_path}",
                    "To read any file inside it, output this marker on its own line:",
                    "  READ_FILE:<relative-path-from-codebase-root>",
                    "The Python harness (not Claude Code tools) will fetch the file and pass it back to you.",
                    "This works for ANY file in the codebase regardless of the current working directory.",
                    "",
                    "To suggest file changes, output EXEC:file: blocks with paths relative to the codebase root.",
                    "The user will be shown a compact summary and asked once whether to apply all changes.",
                    "Do NOT worry about working directory restrictions — file writes are handled by the Python harness.",
                ]
                sections.append("\n".join(codebase_lines))

        sections.append(
            "## Working Instructions\n"
            "- Stay in your domain — answer from your role's perspective\n"
            "- Be specific and actionable\n"
            "- Ask clarifying questions when requirements are ambiguous\n"
            "- Prefix persistent facts with REMEMBER:\n"
            "- Prefix peer questions with ASK_COLLEAGUE:<role>: <question>"
        )
        sections.append(
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
            "- If it should exist on disk, it MUST be in an EXEC: block — no exceptions"
        )
        return "\n\n".join(sections)

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

        # Handle READ_FILE: markers for deep-dive requests
        if self.orchestrator:
            loaded_path = getattr(self.orchestrator, "loaded_path", None)
            if loaded_path:
                read_requests = re.findall(r"READ_FILE:([^\n]+)", response)
                if read_requests:
                    file_contents: dict[str, str] = {}
                    READ_FILE_LIMIT = 8000  # chars — generous for a targeted file read
                    for req in read_requests[:5]:  # cap at 5 files per response
                        fpath = (loaded_path / req.strip()).resolve()
                        # Safety: only read files inside the loaded path
                        try:
                            fpath.relative_to(loaded_path)
                            if fpath.exists() and fpath.is_file():
                                raw = fpath.read_text(encoding="utf-8", errors="replace")
                                if len(raw) > READ_FILE_LIMIT:
                                    file_contents[req.strip()] = (
                                        raw[:READ_FILE_LIMIT]
                                        + f"\n\n[File truncated — {len(raw):,} chars total. "
                                        "Request a specific section or line range if you need more.]"
                                    )
                                else:
                                    file_contents[req.strip()] = raw
                        except (ValueError, Exception):
                            pass
                    if file_contents:
                        file_ctx = "\n\n".join(
                            f"### {fname}\n```\n{content}\n```"
                            for fname, content in file_contents.items()
                        )
                        follow_up = (
                            f"{prompt}\n\n"
                            "You requested these files. Here are their contents:\n\n"
                            f"{file_ctx}\n\n"
                            "Now provide your complete analysis/response."
                        )
                        try:
                            response = call_claude(
                                prompt=follow_up,
                                system_prompt=system_prompt,
                                model=self.model,
                            )
                        except Exception:
                            pass  # keep original response

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
