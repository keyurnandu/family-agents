from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from utils.claude_client import call_claude

if TYPE_CHECKING:
    from utils.memory_manager import MemoryManager

ALL_ROLES = ["pm", "bsa", "developer", "lead", "researcher", "qa", "devops"]

_CODE_TASK_RE = re.compile(
    r"\b(?:implement|code|refactor|debug|fix|read|file|class|function|method|"
    r"import|test|review|write|create|update|edit|change|add|remove|deploy|"
    r"build|run|epic|story|sprint|feature|bug|error|stack|module|api|endpoint)\b",
    re.IGNORECASE,
)

_IMPL_RE = re.compile(
    r"\b(?:implement|write|create|build|add|fix|refactor|update|modify|"
    r"change|work\s+on|complete|finish|do|start|begin|tackle|wire|"
    r"integrate|connect|hook\s+up|configure|set\s+up|apply|generate|"
    r"epic|story|sprint|feature|us-e\d|e\d-\d)\b",
    re.IGNORECASE,
)

_FULL_FILE_RE = re.compile(
    r"\b(?:full|entire|complete|whole|all\s+of|everything\s+in|"
    r"review|audit|check|analyse|analyze|inspect|examine|read\s+through)\b",
    re.IGNORECASE,
)

# Memory categories each role actually needs — avoids injecting irrelevant entries.
# "note" and "decision" are cross-cutting and go to everyone.
# "requirement" is for planning roles; "technical"/"epic-plan" for builders.
_ROLE_MEMORY_CATEGORIES: dict[str, set[str]] = {
    "pm":         {"note", "decision", "requirement", "epic-plan"},
    "bsa":        {"note", "decision", "requirement", "epic-plan"},
    "developer":  {"note", "decision", "technical", "epic-plan"},
    "lead":       {"note", "decision", "technical", "epic-plan"},
    "researcher": {"note", "decision", "technical"},
    "qa":         {"note", "decision", "technical", "epic-plan"},
    "devops":     {"note", "decision", "technical"},
}

_IMPL_ROLES = {"developer", "lead", "qa", "devops"}

_EXEC_INSTRUCTIONS = (
    "## Executing Actions\n"
    "When you want to create or modify a file, or run a shell command, use these exact tags "
    "so the system can ask the customer for permission before executing:\n\n"
    "Create / overwrite a file:\n"
    "```\nEXEC:file:path/to/file\n```\n<file content here>\n```\n\n"
    "Run a shell command:\n"
    "```\nEXEC:bash\n```\n<commands>\n```\n\n"
    "The customer will see a preview and approve or deny each action.\n\n"
    "When you need to run tests, **always** use EXEC:bash — never ask the customer "
    "to run them manually. The system captures the full output and feeds it back into "
    "your context so you can read the results and act on them."
)


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

    # ------------------------------------------------------------------
    # System prompt cache — rebuilt only when memory/skills change
    # ------------------------------------------------------------------
    _prompt_cache: dict = {}   # class-level; keyed by (role, project, cache_key)
    _PROMPT_CACHE_MAX = 20

    def _prompt_cache_key(self) -> str:
        """Cache key: memory entry count + skills mtime + codebase content hash.
        Including key_files hash means the cache invalidates when file contents
        change on disk (not just when the loaded path changes).
        """
        import hashlib
        mem_count = len(self.memory.list_memory_entries())
        skills_dir = self.memory._skills_dir / self.role
        skills_mtime = (
            max((f.stat().st_mtime for f in skills_dir.glob("*.md")), default=0)
            if skills_dir.exists() else 0
        )
        # Hash key_files content so edits to loaded files invalidate the cache
        ctx = getattr(self.orchestrator, "codebase_context", {}) if self.orchestrator else {}
        key_files_hash = hashlib.md5(
            str(sorted(ctx.get("key_files", {}).keys())).encode()
        ).hexdigest()[:8]
        raw = f"{self.role}:{self.memory.project_name}:{mem_count}:{skills_mtime:.0f}:{key_files_hash}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def _build_system_prompt(self, task: str = "") -> str:
        # ── Cache check ──────────────────────────────────────────────
        cache_key = self._prompt_cache_key()
        # Codebase context changes invalidate the cache — include loaded_path in key
        loaded_path = getattr(self.orchestrator, "loaded_path", None) if self.orchestrator else None
        full_key = (self.role, self.memory.project_name, cache_key, str(loaded_path))
        if full_key in Agent._prompt_cache:
            cached_base, cached_codebase_key = Agent._prompt_cache[full_key]
            # Return cached prompt if codebase hasn't changed
            if cached_codebase_key == str(loaded_path):
                return cached_base

        cfg = getattr(self.orchestrator, "config", {}) if self.orchestrator else {}
        max_mem = cfg.get("max_memory_entries", 15)
        max_docs = cfg.get("max_project_docs", 1)
        max_doc_chars = cfg.get("max_doc_chars", 1500)

        role_memory = self.memory.load_role_memory(self.role)

        # Role-filtered memory: each agent only sees categories relevant to their domain.
        # e.g. PM/BSA skip "technical" entries; Developer/Lead skip "requirement" noise.
        # Falls back to all categories for any role not in the filter map.
        role_categories = _ROLE_MEMORY_CATEGORIES.get(self.role)  # None = all
        project_memory = self.memory.load_project_memory(
            limit=max_mem, categories=role_categories
        )

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
            "The ONLY way to deliver files or run commands is via EXEC: tagged blocks in your text.\n\n"
            "BREVITY RULE: Never reproduce or reprint document content that is already in your context. "
            "When asked about a document, sprint, epics, or stories — respond with a SHORT summary "
            "(3–6 bullets max) and ask what to do next. Only provide full details when the user "
            "explicitly requests them (e.g. 'show me all stories in Epic 2'). "
            "Violating this rule wastes tokens and creates noise.",

            role_memory,
            project_section,
        ]
        if self.role in _IMPL_ROLES:
            sections.append(_EXEC_INSTRUCTIONS)
        if skills_text:
            sections.append(f"## Additional Skills & Expertise\n{skills_text}")

        # Inject previously exported project documents (requirements, sprint plans, etc.)
        docs_text = self.memory.load_project_docs(max_docs=max_docs, max_chars_each=max_doc_chars)
        if docs_text:
            sections.append("## Project Documents\n" + docs_text)

        # Inject loaded codebase context — LAZY: only when task is code/file related.
        # Always inject the access instructions so the agent knows how to request files.
        if self.orchestrator:
            ctx = getattr(self.orchestrator, "codebase_context", {})
            if loaded_path and ctx:
                is_code_task = bool(_CODE_TASK_RE.search(task)) if task else True

                if is_code_task:
                    # Full context for code-related tasks
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
                else:
                    # Minimal context for non-code tasks — just the path and file list
                    codebase_lines = [
                        f"## Loaded Codebase: {loaded_path}",
                        f"Tech stack: {', '.join(ctx.get('tech_stack', [])) or 'unknown'}",
                        f"Total files: {ctx.get('total_files', '?')} — use READ_FILE:<path> to access any file.",
                    ]

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
                    "",
                    "### EXEC:bash — working directory is already set",
                    f"The working directory is already set to: {loaded_path}",
                    "NEVER use absolute paths in EXEC:bash commands — always use relative paths.",
                    "Example: `venv\\Scripts\\python.exe -m pytest` NOT the full absolute path.",
                    "Using absolute paths on Windows causes WinError 206 (path too long).",
                ]
                sections.append("\n".join(codebase_lines))

        sections.append(
            "## Working Instructions\n"
            "- Stay in your domain — answer from your role's perspective\n"
            "- Be specific and actionable\n"
            "- Ask clarifying questions when requirements are ambiguous\n"
            "- Prefix persistent facts with REMEMBER:\n"
            "- Prefix peer questions with ASK_COLLEAGUE:<role>: <question>\n"
            "- NEVER reproduce or reprint document content that is already in your context "
            "(Project Documents section). If asked about a document, give a brief summary "
            "(3-5 bullets) and offer to go deeper on specific parts. Only provide full details "
            "when the user explicitly asks for them (e.g. 'show me all stories in Epic 2').\n"
            "- Keep responses concise. Avoid padding, preamble, and restating what the user said."
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
        result = "\n\n".join(sections)
        # Write to cache (keyed without task so it's reusable across calls)
        Agent._prompt_cache[full_key] = (result, str(loaded_path))
        if len(Agent._prompt_cache) > Agent._PROMPT_CACHE_MAX:
            oldest = next(iter(Agent._prompt_cache))
            del Agent._prompt_cache[oldest]
        return result

    def _get_peer_input(self, colleague_role: str, question: str) -> str:
        """Ask a peer agent a single question (no further nesting).

        Any instantiated agent can be consulted — including bench agents
        (researcher, qa, devops) that aren't on the active roster.
        This mirrors how Aria's routing can pull bench agents into phases.
        """
        if not self.orchestrator:
            return "(peer consultation unavailable)"

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

    def respond(
        self,
        task: str,
        context: str,
        history_text: str,
        shared_file_cache: dict | None = None,
        shared_file_lock=None,
    ) -> str:
        """Generate a response, handling one round of peer consultation if needed.

        shared_file_cache / shared_file_lock: when multiple agents run in parallel
        in the same phase, pass the same dict + Lock so each file is read from disk
        only once regardless of how many agents request it.
        """
        system_prompt = self._build_system_prompt(task=task)

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
            read_requests = re.findall(r"READ_FILE:([^\n]+)", response)
            if read_requests:
                file_contents: dict[str, str] = {}
                _disk_cache: dict[str, str] = {}  # dedup: avoid re-reading same file twice

                # Raise the limit when the task explicitly asks for the full/entire file
                # OR when the task is a review/audit — reviews need the whole file to be useful.
                want_full = bool(_FULL_FILE_RE.search(task))
                cfg = getattr(self.orchestrator, "config", {}) if self.orchestrator else {}
                _default_limit = cfg.get("max_read_file_chars", 20_000)
                READ_FILE_LIMIT = None if want_full else _default_limit

                project_docs_dir = self.base_dir / "projects" / self.memory.project_name

                for req in read_requests[:5]:  # cap at 5 files per response
                    req_clean = req.strip()

                    # 1. Check within-turn dedup cache (this agent)
                    if req_clean in _disk_cache:
                        file_contents[req_clean] = _disk_cache[req_clean]
                        continue

                    # 2. Check cross-agent shared cache (same phase, different agent already read it)
                    if shared_file_cache is not None and req_clean in shared_file_cache:
                        file_contents[req_clean] = shared_file_cache[req_clean]
                        _disk_cache[req_clean] = shared_file_cache[req_clean]
                        continue

                    raw = None

                    # 3. Check project docs/files first (requirements, sprint plans, etc.)
                    candidate = (project_docs_dir / req_clean).resolve()
                    try:
                        # Use string startswith instead of relative_to — more reliable
                        # on Windows/OneDrive where path normalisation can cause relative_to
                        # to raise ValueError even when the path is legitimately inside the root.
                        docs_root = str(project_docs_dir.resolve()).rstrip("\\/").lower()
                        if str(candidate).lower().startswith(docs_root):
                            if candidate.exists() and candidate.is_file():
                                raw = candidate.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        pass

                    # 4. Fall back to loaded codebase — exact path first
                    if raw is None and loaded_path:
                        try:
                            fpath = (loaded_path / req_clean).resolve()
                            cb_root = str(loaded_path.resolve()).rstrip("\\/").lower()
                            if str(fpath).lower().startswith(cb_root):
                                if fpath.exists() and fpath.is_file():
                                    raw = fpath.read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            pass

                    # 5. Fuzzy filename fallback — agents sometimes guess paths that are
                    #    one level off (tree only showed depth N, file is at depth N+1).
                    #    Search the whole codebase by filename and use the unique match.
                    if raw is None and loaded_path:
                        try:
                            filename = Path(req_clean).name
                            _IGNORE = {
                                ".git", "node_modules", "__pycache__",
                                ".venv", "venv", "dist", "build", ".next",
                            }
                            matches = [
                                f for f in loaded_path.rglob(filename)
                                if f.is_file()
                                and not any(ig in f.parts for ig in _IGNORE)
                            ]
                            if matches:
                                # Pick the match whose path best overlaps the requested path
                                req_parts = set(Path(req_clean).parts)
                                best = max(
                                    matches,
                                    key=lambda f: len(set(f.parts) & req_parts),
                                )
                                raw = best.read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            pass

                    if raw is not None:
                        stored = (
                            raw[:READ_FILE_LIMIT]
                            + f"\n\n[File truncated — {len(raw):,} chars total. "
                            "Say 'show full <filename>' for the complete file.]"
                            if READ_FILE_LIMIT and len(raw) > READ_FILE_LIMIT
                            else raw
                        )
                        file_contents[req_clean] = stored
                        _disk_cache[req_clean] = stored
                        # Populate shared cache so other parallel agents skip the disk read
                        if shared_file_cache is not None:
                            if shared_file_lock:
                                with shared_file_lock:
                                    shared_file_cache.setdefault(req_clean, stored)
                            else:
                                shared_file_cache.setdefault(req_clean, stored)
                if file_contents:
                    file_ctx = "\n\n".join(
                        f"### {fname}\n```\n{content}\n```"
                        for fname, content in file_contents.items()
                    )
                    # Detect intent: implementation tasks must output EXEC blocks now.
                    # Read/review tasks get the short-summary instruction.
                    is_impl_task = bool(_IMPL_RE.search(task))

                    if is_impl_task:
                        follow_up_instruction = (
                            "You now have the full file context. "
                            "THIS IS YOUR ONLY TURN TO WRITE CODE — there is no follow-up. "
                            "Rules:\n"
                            "- Do NOT say 'I will implement', 'stand by', 'here is the plan', "
                            "or any variant — that wastes the turn.\n"
                            "- Do NOT summarise or reproduce file contents.\n"
                            "- OUTPUT THE ACTUAL CODE NOW using EXEC:file: blocks.\n"
                            "- Every file that needs changing must have its own EXEC:file: block "
                            "with the COMPLETE new content.\n"
                            "- If you do not output EXEC:file: blocks in this response, "
                            "nothing will be written and the task fails."
                        )
                    else:
                        follow_up_instruction = (
                            "IMPORTANT: Do NOT reproduce or reprint this content. "
                            "Give a SHORT response — 3 to 6 bullet points maximum. "
                            "Summarise what you found and ask what to do next."
                        )

                    follow_up = (
                        f"{prompt}\n\n"
                        "You requested these files. Here are their contents:\n\n"
                        f"{file_ctx}\n\n"
                        f"{follow_up_instruction}"
                    )
                    try:
                        response = call_claude(
                            prompt=follow_up,
                            system_prompt=system_prompt,
                            model=self.model,
                        )
                    except Exception:
                        pass  # keep original response

                elif read_requests:
                    # READ_FILE was requested but NO files were found.
                    # Return a direct plain-text message — NO LLM call here.
                    # An LLM call at this point produces "sandbox wall" hallucinations.
                    not_found = ", ".join(r.strip() for r in read_requests[:5])
                    loaded = getattr(self.orchestrator, "loaded_path", None) if self.orchestrator else None
                    if loaded:
                        response = (
                            f"I couldn't find the requested file(s): `{not_found}`.\n\n"
                            f"The codebase is loaded at `{loaded}` — but those paths don't exist inside it. "
                            "Please check the path is correct relative to the codebase root, then try again."
                        )
                    else:
                        response = (
                            f"No codebase is currently loaded — I couldn't read `{not_found}`.\n\n"
                            "Use `/load <path>` to point the team at your project directory, "
                            "then ask your question again."
                        )

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
