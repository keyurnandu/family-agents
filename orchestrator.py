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

# Maps export type keywords to the agent best suited to write that doc
EXPORT_TYPE_MAP = {
    "requirements":   ("bsa",       "requirements-doc"),
    "requirement":    ("bsa",       "requirements-doc"),
    "user-stories":   ("bsa",       "user-stories"),
    "architecture":   ("lead",      "architecture-doc"),
    "technical":      ("lead",      "technical-spec"),
    "tech-spec":      ("lead",      "technical-spec"),
    "technical-spec": ("lead",      "technical-spec"),
    "sprint":         ("pm",        "sprint-plan"),
    "sprint-plan":    ("pm",        "sprint-plan"),
    "roadmap":        ("pm",        "roadmap"),
    "plan":           ("pm",        "project-plan"),
    "api":            ("developer", "api-docs"),
    "api-docs":       ("developer", "api-docs"),
    "test":           ("qa",        "test-plan"),
    "test-plan":      ("qa",        "test-plan"),
    "deployment":     ("devops",    "deployment-plan"),
    "deploy":         ("devops",    "deployment-plan"),
}

# Patterns that signal export/report generation intent
_EXPORT_PATTERNS = [
    r"(?:generate|create|write|produce|export|make)\s+(?:a\s+|an\s+|the\s+)?(\w[\w\s\-]*?)\s+(?:doc(?:ument)?|spec|plan|report|summary)",
    r"export\s+(?:the\s+)?(\w[\w\s\-]*?)(?:\s+decisions?|\s+notes?)?$",
    r"(?:generate|create|write)\s+(?:a\s+)?(\w[\w\s\-]*?)$",
]

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
                            "constraint", "assumption", "stakeholder", "document",
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

# Patterns that signal a direct file-read request — served without any LLM calls
# Only triggers when the message contains a filename with an extension (e.g. config.py, sprint.md)
_FILE_READ_INTENT_RE = re.compile(
    r"\b(?:read|show|display|view|open|print|cat|get|fetch|see)\b",
    re.IGNORECASE,
)
_FILE_PATH_IN_MSG_RE = re.compile(
    r"(?:^|\s)[`'\"]?([\w./\\-]+\.\w{1,8})[`'\"]?(?:\s|$|\?)",
)
# Words that signal the user wants the FULL file (no truncation)
_FULL_FILE_RE = re.compile(
    r"\b(?:full|entire|complete|whole|all\s+of|everything\s+in)\b",
    re.IGNORECASE,
)

# Detects epic / story kickoff so a plan summary is saved to memory automatically
_EPIC_KICKOFF_RE = re.compile(
    r"\b(?:work\s+on|start|implement|begin|kick\s*off|tackle|do|complete|finish)\s+"
    r"(?:epic|story|e\d+|s\d+|sprint)",
    re.IGNORECASE,
)

# Patterns that signal the user wants to teach an agent a new skill
_TEACH_PATTERNS = [
    (r"(?:please\s+)?teach\s+(?:the\s+)?(\w+)(?:\s+team)?\s+(.+)", 1, 2),
    (r"(\w+)(?:\s+team)?\s+needs?\s+to\s+(?:learn|know|understand|use)\s+(.+)", 1, 2),
    (r"add\s+(.+?)\s+(?:skill|knowledge|expertise\s+)?to\s+(?:the\s+)?(\w+)(?:\s+team)?", 2, 1),
    (r"(\w+)(?:\s+team)?\s+should\s+(?:learn|know|understand|use)\s+(.+)", 1, 2),
]


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

        # Loaded external codebase (set by /load command)
        self.loaded_path: Path | None = None
        self.codebase_context: dict = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _scan_codebase(self, path: Path) -> dict:
        """Scan an external codebase — structure tree + key files."""
        KEY_FILES = [
            "README.md", "README.rst", "README.txt",
            "package.json", "requirements.txt", "setup.py", "pyproject.toml",
            "pom.xml", "build.gradle", "go.mod", "Cargo.toml",
            ".env.example", "Dockerfile", "docker-compose.yml",
            "tsconfig.json", ".eslintrc.js", ".eslintrc.json",
        ]
        ENTRY_POINTS = [
            "index.js", "index.ts", "main.js", "main.ts",
            "app.js", "app.ts", "src/index.js", "src/index.ts",
            "src/main.js", "src/main.ts", "src/app.js", "src/app.ts",
            "main.py", "app.py", "manage.py", "run.py",
            "src/main.py", "src/app.py",
        ]
        IGNORE = {
            ".git", "node_modules", "__pycache__", ".venv", "venv",
            "dist", "build", ".next", "target", ".gradle", ".idea", ".vscode",
        }

        def build_tree(p: Path, prefix: str = "", depth: int = 0) -> list[str]:
            if depth > 3:
                return []
            lines: list[str] = []
            try:
                items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
            except PermissionError:
                return []
            visible = [i for i in items if i.name not in IGNORE and not i.name.startswith(".")]
            for idx, item in enumerate(visible):
                connector = "└── " if idx == len(visible) - 1 else "├── "
                lines.append(f"{prefix}{connector}{item.name}{'/' if item.is_dir() else ''}")
                if item.is_dir() and depth < 3:
                    ext = "    " if idx == len(visible) - 1 else "│   "
                    lines.extend(build_tree(item, prefix + ext, depth + 1))
            return lines

        tree_lines = [f"{path.name}/"] + build_tree(path)
        structure_tree = "\n".join(tree_lines[:200])

        KEY_FILE_LIMIT = 4000   # chars — enough for most config/manifest files
        ENTRY_POINT_LIMIT = 3000  # chars — enough for a typical entry point

        key_file_contents: dict[str, str] = {}
        for fname in KEY_FILES:
            fpath = path / fname
            if fpath.exists() and fpath.is_file():
                try:
                    raw = fpath.read_text(encoding="utf-8", errors="replace")
                    if len(raw) > KEY_FILE_LIMIT:
                        key_file_contents[fname] = raw[:KEY_FILE_LIMIT] + f"\n\n[File truncated — {len(raw):,} chars total. Use READ_FILE:{fname} for the full content.]"
                    else:
                        key_file_contents[fname] = raw
                except Exception:
                    pass

        for ep in ENTRY_POINTS:
            ep_path = path / ep
            if ep_path.exists() and ep_path.is_file() and ep not in key_file_contents:
                try:
                    raw = ep_path.read_text(encoding="utf-8", errors="replace")
                    if len(raw) > ENTRY_POINT_LIMIT:
                        key_file_contents[ep] = raw[:ENTRY_POINT_LIMIT] + f"\n\n[File truncated — {len(raw):,} chars total. Use READ_FILE:{ep} for the full content.]"
                    else:
                        key_file_contents[ep] = raw
                except Exception:
                    pass
                break

        tech_stack: list[str] = []
        if (path / "package.json").exists():
            tech_stack.append("Node.js/JavaScript")
        if (path / "tsconfig.json").exists():
            tech_stack.append("TypeScript")
        if any((path / f).exists() for f in ["requirements.txt", "setup.py", "pyproject.toml"]):
            tech_stack.append("Python")
        if (path / "pom.xml").exists():
            tech_stack.append("Java/Maven")
        if (path / "build.gradle").exists():
            tech_stack.append("Java/Gradle")
        if (path / "go.mod").exists():
            tech_stack.append("Go")
        if (path / "Cargo.toml").exists():
            tech_stack.append("Rust")
        if (path / "Dockerfile").exists():
            tech_stack.append("Docker")

        IGNORE_COUNT = IGNORE | {".env"}
        total_files = sum(
            1 for f in path.rglob("*")
            if f.is_file() and not any(ig in f.parts for ig in IGNORE_COUNT)
        )

        return {
            "structure_tree": structure_tree,
            "key_files": key_file_contents,
            "tech_stack": tech_stack,
            "total_files": total_files,
        }

    def _strip_exec_for_display(self, text: str) -> str:
        """Replace EXEC block content with a compact placeholder for display.
        The full content is shown in the apply prompt — no need to print it twice."""
        def _file_placeholder(m):
            path = m.group(1).strip()
            lines = len(m.group(2).strip().splitlines())
            return f"\n[📄 `{path}` — {lines} lines · shown in apply prompt]\n"

        text = re.sub(
            r"EXEC:file:([^\n]+)\n```[^\n]*\n(.*?)```",
            _file_placeholder,
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        text = re.sub(
            r"EXEC:bash\s*\n```[^\n]*\n.*?```",
            "\n[🔧 shell command · shown in apply prompt]\n",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        return text.strip()

    def _format_history(self, limit: int = 6) -> str:
        if not self.messages:
            return ""
        lines = []
        for m in self.messages[-limit:]:
            label = "Customer" if m["role"] == "user" else "Team"
            content = m["content"][:600] + "…" if len(m["content"]) > 600 else m["content"]
            lines.append(f"[{label}]: {content}")
        return "\n".join(lines)

    def _routing_system_prompt(self) -> str:
        """
        Lightweight system prompt for Aria's routing call.
        Deliberately trimmed — routing is classification, not reasoning.
        Full context (memory, docs) is injected into specialist agents separately.
        """
        # Only pass a small slice of memory for routing context
        routing_mem_limit = self.config.get("max_routing_memory", 8)
        project_memory = self.memory.load_project_memory(limit=routing_mem_limit)

        # For docs: titles + one-line summaries only — not full content
        doc_index = self._routing_doc_index()

        team_lines = [
            f"- {role} ({self.config['agent_personas'].get(role, {}).get('name', role)}): "
            f"{ROLE_DESCRIPTIONS.get(role, '')}"
            for role in self.active_roster
        ]
        available = [
            r for r in self.config["team"]["available_agents"]
            if r not in self.active_roster
        ]

        # TDD mode context — injected into routing when active
        tdd_enabled, tdd_health_cmd = self.memory.load_tdd_mode()
        tdd_section = ""
        if tdd_enabled:
            tdd_section = (
                "## TDD MODE IS ACTIVE\n"
                "For ANY implementation task (writing code, adding features, fixing bugs, "
                "implementing epics/stories):\n"
                "- ALWAYS create TWO sequential phases:\n"
                "  Phase 1 — 'Write Tests': assign qa (Casey) to write failing tests FIRST\n"
                "  Phase 2 — 'Implement': assign developer (Sam) to implement until tests pass\n"
                "- Never collapse these into a single phase.\n"
                "- Casey's task must be: write the test file(s) for [feature] — no implementation yet.\n"
                "- Sam's task must reference Casey's tests: implement [feature] so Casey's tests pass.\n"
                "- For non-implementation tasks (questions, reviews, planning) use normal routing.\n\n"
            )

        return (
            f"You are Aria, the project coordinator for '{self.project_name}'. "
            "Your ONLY job here is to decide which agents to involve and what to ask each one.\n\n"
            f"## Active Team\n" + "\n".join(team_lines) + "\n\n"
            + (f"## Available to Add\n{', '.join(available)}\n\n" if available else "")
            + (f"## Recent Project Memory\n{project_memory}\n\n" if project_memory else "")
            + (f"## Existing Documents\n{doc_index}\n\n" if doc_index else "")
            + tdd_section
            + "## Routing Rules\n"
            "- Use sequential PHASES only when tasks genuinely depend on each other "
            "(requirements → implementation → QA → devops).\n"
            "- Use a SINGLE phase for questions, discussions, reviews, or anything "
            "that doesn't need hand-offs.\n"
            "- Agents within a phase run in parallel — assign each a specific task.\n"
            "- If docs already cover requirements, skip the requirements phase.\n"
            "- For greetings or simple clarifications, return an empty agents list.\n"
            "- If the customer asks about sprint details, epics, stories, requirements, or any "
            "document — route to ONE specialist only (bsa for requirements/stories/epics, "
            "pm for sprints/plans/roadmaps, lead for architecture). Never return empty agents "
            "for document questions, and never assign more than one agent to a simple read request.\n"
            "- 'Read', 'show', 'tell me about', 'what's in', 'summarise' = ONE agent. "
            "Only use multiple agents when the customer asks for analysis, implementation, "
            "or cross-domain work.\n"
            "- NEVER return empty agents for implementation, coding, file-reading, or epic/story "
            "work. These ALWAYS need at least developer or lead. Aria cannot read files or write "
            "code — only specialists can.\n\n"
            "Return ONLY valid JSON. No explanation, no markdown."
        )

    def _routing_doc_index(self) -> str:
        """Return a compact one-line-per-doc index for routing context."""
        from pathlib import Path
        docs_dir = self.base_dir / "projects" / self.project_name / "docs"
        if not docs_dir.exists():
            return ""
        files = sorted(docs_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            return ""
        lines = []
        for f in files[:5]:
            # Grab first non-empty line of the doc as the summary
            try:
                first_line = next(
                    (l.strip() for l in f.read_text(encoding="utf-8").splitlines()
                     if l.strip() and not l.startswith("#")),
                    ""
                )[:80]
            except Exception:
                first_line = ""
            lines.append(f"- {f.name}  {first_line}")
        return "\n".join(lines)

    def _synthesis_system_prompt(self) -> str:
        """System prompt for Aria's synthesis/direct-answer calls.
        Includes role memory, project documents, and CRITICAL CONSTRAINT so Aria
        never asks the customer to re-provide information that is already on disk."""
        role_memory = self.memory.load_role_memory("orchestrator")

        # Inject project docs — same slice agents get — so Aria can answer
        # document questions directly without routing to a specialist.
        cfg = self.config
        max_docs = cfg.get("max_project_docs", 1)
        max_doc_chars = cfg.get("max_doc_chars", 1500)
        docs_text = self.memory.load_project_docs(max_docs=max_docs, max_chars_each=max_doc_chars)
        docs_section = (
            f"\n\n## Project Documents\n{docs_text}"
            if docs_text else ""
        )

        # Also inject a small slice of project memory for context
        routing_mem_limit = cfg.get("max_routing_memory", 8)
        project_memory = self.memory.load_project_memory(limit=routing_mem_limit)
        memory_section = (
            f"\n\n## Project Memory (recent)\n{project_memory}"
            if project_memory else ""
        )

        constraint = (
            "\n\n## CRITICAL CONSTRAINT\n"
            "You are running as a TEXT-ONLY agent. "
            "You have NO access to Write, Edit, Read, Bash, or any file-system tools. "
            "Do NOT attempt to call any tools. "
            "Do NOT mention Claude Code, settings.json, .claude folders, or permission dialogs — "
            "none of that applies here.\n\n"
            "NEVER output READ_FILE: markers. You cannot read files — only specialist agents "
            "(Sam, Jordan, Morgan, etc.) can. If files need to be read, your job is to route "
            "to the appropriate specialist, not to read files yourself.\n\n"
            "IMPORTANT: Never ask the customer to provide a file path, paste content, or share a "
            "link to information that is already in your Project Documents section above. "
            "If a document is in context, use it directly.\n\n"
            "FILE ERROR RULE — READ THIS CAREFULLY:\n"
            "NEVER ask the customer whether the codebase is loaded. NEVER suggest they run /load. "
            "The system handles codebase loading automatically — it is not the customer's problem. "
            "If agents could not read files, simply say the files weren't available this turn and "
            "that the team will retry. Do NOT use the words 'sandbox', 'locked', 'session', "
            "'restricted', 'permission', 'working directory', 'Claude Code session', or "
            "'has the codebase been loaded'. Those concepts DO NOT EXIST here.\n\n"
            "When agents include EXEC: file or bash blocks in their responses, those are already "
            "queued for the customer's approval by the Python harness. "
            "In your synthesis, simply tell the customer what the team is proposing to write or run — "
            "do NOT re-explain the mechanism, do NOT ask them to approve anything special. "
            "Just say e.g. 'Sam and Jordan are ready to write config.py — "
            "you will be prompted to approve each file.'"
        )
        return f"{role_memory}{docs_section}{memory_section}{constraint}"

    def _synthesis_prompt(self, user_input: str, agent_responses: dict) -> str:
        parts = [
            f"The customer said:\n{user_input}\n\n"
            "The team has weighed in:\n"
        ]
        personas = self.config["agent_personas"]
        for role, response in agent_responses.items():
            name = personas.get(role, {}).get("name", role.upper())
            # Strip EXEC block content — Aria doesn't need to see 200-line files;
            # she just needs to know the agent is proposing writes.
            display_response = self._strip_exec_for_display(response)
            parts.append(f"[{name} — {role.upper()}]\n{display_response}\n")

        parts.append(
            "\nAs Aria, the coordinator, synthesize these into a clear, unified response "
            "for the customer. Be concise. Credit team members where relevant. "
            "If agents have file changes queued, tell the customer they will be prompted to approve them. "
            "If there are open questions for the customer, group them at the end.\n\n"
            "IMPORTANT: Always close your response with a brief **What would you like to do next?** "
            "section offering 2–3 concrete options tailored to where the project is now "
            "(e.g. move to implementation, refine requirements, write a test plan, review the code, deploy, etc.). "
            "Keep each option to one short line. This keeps the team moving forward without the customer "
            "having to guess what's possible."
        )
        return "\n".join(parts)

    def _save_epic_plan_memory(self, user_input: str, agent_responses: dict):
        """
        After an epic/story kickoff, ask haiku to extract a structured plan summary
        from agent responses and persist it to project memory under 'epic-plan'.
        Zero UI — runs silently in the background.
        """
        personas = self.config["agent_personas"]
        combined = "\n\n".join(
            f"[{personas.get(r, {}).get('name', r.upper())}]:\n{resp[:1500]}"
            for r, resp in agent_responses.items()
        )
        prompt = (
            f"The customer requested: {user_input}\n\n"
            f"The team responded:\n{combined}\n\n"
            "Extract a concise plan summary (5-8 bullet points max) covering:\n"
            "- Which epic/stories are being worked on\n"
            "- Key implementation steps planned\n"
            "- Files to be created or modified\n"
            "- Any dependencies or blockers noted\n"
            "- Expected outcomes\n\n"
            "Format: plain bullet points. No headings. No preamble."
        )
        try:
            summary = call_claude(
                prompt=prompt,
                system_prompt="You extract concise plan summaries from team conversations. Be specific and brief.",
                model="haiku",
            )
            if summary.strip():
                saved = self.memory.save_project_memory(
                    content=f"EPIC KICKOFF — {user_input.strip()}\n{summary.strip()}",
                    category="epic-plan",
                    source="aria",
                )
                if saved:
                    console.print("[dim green]  (📌 Epic plan saved to memory)[/dim green]")
        except Exception:
            pass  # non-critical — never block the main flow

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
                p.get("name", role.upper()), self._strip_exec_for_display(response),
                p.get("color", "white"), p.get("emoji", "")
            )
            actions = parse_actions(response, p.get("name", role.upper()))
            if actions:
                write_dir = self.loaded_path if self.loaded_path else project_dir
                prompt_and_execute(actions, write_dir)

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
                model=self.config.get("routing_model", "haiku"),
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
    # Direct file-serve shortcut (zero LLM calls for simple read requests)
    # ------------------------------------------------------------------

    def _try_serve_file_directly(self, user_input: str) -> bool:
        """
        Serve a file instantly from disk (zero LLM calls) when the message is a
        simple read request. Two matching strategies:

        1. Exact path match — message contains a filename with an extension
           e.g. 'show config.py', 'read sprint-plan-2026-05-20.md'

        2. Fuzzy doc match — message contains read intent + keywords that match
           a filename in the project docs folder, even without an extension
           e.g. 'read the sprint details' → matches sprint-plan-*.md
                'show epics and stories'  → matches epics-and-user-stories-*.md
        """
        if not _FILE_READ_INTENT_RE.search(user_input):
            return False

        want_full = bool(_FULL_FILE_RE.search(user_input))
        docs_dir = self.base_dir / "projects" / self.project_name / "docs"

        # Build search roots once — used by both strategies and the display block
        search_roots = []
        if docs_dir.exists():
            search_roots.append(docs_dir)
        if self.loaded_path:
            search_roots.append(self.loaded_path)

        resolved = None

        # ── Strategy 1: exact path/filename with extension ────────────
        path_match = _FILE_PATH_IN_MSG_RE.search(user_input)
        if path_match:
            candidate = path_match.group(1).strip().strip("`'\"")
            for root in search_roots:
                try:
                    fpath = (root / candidate).resolve()
                    root_str = str(root.resolve()).rstrip("\\/").lower()
                    if str(fpath).lower().startswith(root_str) and fpath.exists() and fpath.is_file():
                        resolved = fpath
                        break
                except Exception:
                    pass

        # ── Strategy 2: fuzzy keyword match against docs folder ───────
        if resolved is None and docs_dir.exists():
            # Extract meaningful words from the message (3+ chars, not stopwords)
            _STOPWORDS = {"the", "can", "you", "read", "show", "get", "give", "me",
                          "our", "and", "for", "with", "all", "any", "its", "tell",
                          "about", "details", "please", "just", "full", "entire"}
            words = [
                w.lower() for w in re.findall(r"[a-zA-Z]{3,}", user_input)
                if w.lower() not in _STOPWORDS
            ]
            if words:
                doc_files = sorted(
                    docs_dir.glob("*.md"),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )
                for doc_file in doc_files:
                    stem = doc_file.stem.lower()
                    # Match if ANY search word appears in the filename stem
                    if any(w in stem for w in words):
                        resolved = doc_file
                        break

        if resolved is None:
            return False  # fall through to normal LLM routing

        # Read content — full if user asked for it, else cap at 20 000 chars
        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return False

        DISPLAY_LIMIT = None if want_full else 20_000
        truncated = False
        if DISPLAY_LIMIT and len(content) > DISPLAY_LIMIT:
            content = content[:DISPLAY_LIMIT]
            truncated = True

        from rich.syntax import Syntax
        suffix = resolved.suffix.lstrip(".") or "text"
        rel = resolved.relative_to(search_roots[search_roots.index(
            next(r for r in search_roots if resolved.is_relative_to(r))
        )]) if any(resolved.is_relative_to(r) for r in search_roots) else resolved.name

        console.print(f"\n[dim]📄  {rel}[/dim]")
        console.print(Syntax(content, suffix, theme="monokai", line_numbers=True))
        if truncated:
            console.print(
                f"[dim yellow]  ⚠ Showing first {DISPLAY_LIMIT:,} chars of "
                f"{len(resolved.read_text(encoding='utf-8', errors='replace')):,}. "
                "Say 'show full <filename>' to see everything.[/dim yellow]"
            )
        console.print()

        # Persist to conversation so history stays coherent
        self.db.save_message(self.project_name, "user", user_input)
        self.db.save_message(
            self.project_name, "assistant",
            f"[Direct file read: {resolved.name} — {len(content):,} chars displayed]",
        )
        self.messages.append({"role": "user", "content": user_input})
        self.messages.append({
            "role": "assistant",
            "content": f"[Served {resolved.name} directly from disk]",
        })
        return True

    # ------------------------------------------------------------------
    # Main entry: process one user message
    # ------------------------------------------------------------------

    def process(self, user_input: str):
        # Short-circuit: direct file reads served instantly from disk (zero LLM calls).
        # _try_serve_file_directly also writes to db/messages, so return immediately.
        if self._try_serve_file_directly(user_input):
            return

        self.db.save_message(self.project_name, "user", user_input)
        self.messages.append({"role": "user", "content": user_input})

        # Detect export/report generation intent (before teaching detection — more specific)
        export_match = self._detect_export_intent(user_input)
        if export_match:
            agent_role, doc_type = export_match
            self.export_doc(doc_type, agent_role)
            self.db.save_message(self.project_name, "assistant", f"[Generated {doc_type}]")
            self.messages.append({"role": "assistant", "content": f"[Generated {doc_type}]"})
            console.print()
            return

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

        # Detect natural-language teaching intent — handle and return (no routing needed)
        for pattern, role_group, skill_group in _TEACH_PATTERNS:
            m = re.search(pattern, user_input, re.IGNORECASE)
            if m:
                identifier = m.group(role_group).strip()
                skill_desc = m.group(skill_group).strip().rstrip(".,!")
                role = self._resolve_role(identifier)
                if role and role != "orchestrator":
                    words = skill_desc.split()
                    skill_name = words[0].lower() if len(words) <= 2 else "-".join(w.lower() for w in words[:3])
                    self.add_skill(role, skill_name, skill_desc)
                    self.db.save_message(self.project_name, "assistant", f"[Skill added: {skill_name} → {role}]")
                    self.messages.append({"role": "assistant", "content": f"[Skill added: {skill_name} → {role}]"})
                    return  # teaching handled — skip routing entirely
                break

        # Zero-LLM shortcuts: natural-language equivalents of CLI commands
        _nl = user_input.strip().lower().rstrip("?.")
        if re.match(r"^(?:show|what(?:'s| is)(?: the)?|list|display) (?:the )?(?:team|roster|agents?)$", _nl):
            self.show_team()
            return
        if re.match(r"^(?:show|what(?:'s| is)(?: in| are)?|display|list|view) (?:the )?memory$", _nl):
            self.show_memory()
            return
        if re.match(r"^(?:show|what(?:'s| is)(?: the)?|display|get) (?:the )?(?:project )?status$", _nl):
            self.show_status()
            return

        # Pre-routing guard: if the task needs codebase access and nothing is loaded,
        # try to auto-reload the last used path silently — no prompt, no friction.
        # Only stop and ask the user if there is genuinely no saved path to reload.
        _CODEBASE_INTENT_RE = re.compile(
            r"\b(?:review|read|show|open|check|audit|inspect|analyse|analyze|"
            r"implement|write|fix|refactor|update|modify|change|edit|"
            r"work\s+on|look\s+at|go\s+through|epic|story|sprint|feature|"
            r"file|files|code|codebase|class|function|method|module|"
            r"endpoint|api|service|controller|model|schema)\b",
            re.IGNORECASE,
        )
        if not self.loaded_path and _CODEBASE_INTENT_RE.search(user_input):
            saved_cb = self.memory.load_loaded_path()
            if saved_cb:
                cb_path = Path(saved_cb)
                if cb_path.exists() and cb_path.is_dir():
                    # Auto-reload silently — just pick up where we left off
                    console.print(f"[dim]↺  Auto-reloading [cyan]{saved_cb}[/cyan]…[/dim]")
                    self.load_codebase(saved_cb)
                    # Fall through — codebase is now loaded, continue with the request
                else:
                    console.print(
                        f"\n[yellow]Saved codebase path no longer exists:[/yellow] [cyan]{saved_cb}[/cyan]\n"
                        "Run [bold cyan]/load <new-path>[/bold cyan] to point the team at your code.\n"
                    )
                    return
            # If no saved path exists this is a normal project with no external codebase
            # (e.g. a brand-new project being built from scratch). Fall through to routing.

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

        # TDD config for this process() call — read once, passed to all file writes
        _tdd_enabled, _tdd_health_cmd = self.memory.load_tdd_mode()
        _tdd_cwd = self.loaded_path if self.loaded_path else project_dir

        import threading
        # Shared file cache + lock — populated lazily per phase.
        # All agents in the same phase share this so each file is read from disk once.
        phase_file_cache: dict = {}
        phase_file_lock = threading.Lock()

        def _call_one(role: str, task: str, ctx: str) -> tuple[str, str]:
            """Run one agent and return (role, response). Thread-safe."""
            agent = self.agents.get(role)
            if not agent:
                return role, "(agent not found)"
            return role, agent.respond(
                task=task,
                context=ctx,
                history_text=self._format_history(limit=3),
                shared_file_cache=phase_file_cache,
                shared_file_lock=phase_file_lock,
            )

        for phase_idx, phase in enumerate(phases):
            phase_file_cache.clear()   # fresh cache per phase — don't share stale reads
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

                self.display.show_agent_response(name, self._strip_exec_for_display(response), color, emoji)

                # Permission-gated action execution
                actions = parse_actions(response, name)
                if actions:
                    write_dir = self.loaded_path if self.loaded_path else project_dir
                    outcomes = prompt_and_execute(
                        actions,
                        write_dir,
                        tdd_health_cmd=_tdd_health_cmd if _tdd_enabled else None,
                        tdd_cwd=_tdd_cwd,
                    )
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

        # ── Epic kickoff: auto-save plan summary to memory ────────────
        if _EPIC_KICKOFF_RE.search(user_input) and agent_responses:
            self._save_epic_plan_memory(user_input, agent_responses)

        # ── Auto-scaffold on first message of a new project ───────────
        # Skip when a codebase is loaded — the project already exists externally.
        if self.is_new_project and agent_responses and not self.loaded_path:
            self.is_new_project = False  # only once per project lifetime
            self._scaffold_project(user_input, agent_responses)
        elif self.is_new_project and self.loaded_path:
            self.is_new_project = False  # loaded project — never scaffold

        # Synthesize if multiple agents responded; otherwise Aria speaks directly.
        # Skip synthesis when every agent returned a file-not-found error — synthesizing
        # those messages produces "sandbox restriction" hallucinations from the LLM.
        _FILE_ERROR_RE = re.compile(
            r"^(?:I couldn't find|No codebase is currently loaded)",
            re.IGNORECASE,
        )
        all_file_errors = bool(agent_responses) and all(
            _FILE_ERROR_RE.match(resp.strip())
            for resp in agent_responses.values()
        )

        final_response = ""
        if len(agent_responses) > 1 and not all_file_errors:
            with console.status("[bright_cyan]🎯 Aria is synthesizing…[/bright_cyan]", spinner="dots"):
                synth_prompt = self._synthesis_prompt(user_input, agent_responses)
                try:
                    final_response = call_claude(
                        prompt=synth_prompt,
                        system_prompt=self._synthesis_system_prompt(),
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
                            "Respond as Aria, the project coordinator. "
                            "End with a brief 'What would you like to do next?' "
                            "offering 2–3 concrete next steps."
                        ),
                        system_prompt=self._synthesis_system_prompt(),
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
                    history_text=self._format_history(limit=3),
                )
        except KeyboardInterrupt:
            console.print("\n[yellow]⚡ Interrupted.[/yellow]")
            console.print()
            return

        self.display.show_agent_response(name, self._strip_exec_for_display(response), color, emoji)

        project_dir = self.base_dir / "projects" / self.project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        actions = parse_actions(response, name)
        if actions:
            write_dir = self.loaded_path if self.loaded_path else project_dir
            outcomes = prompt_and_execute(actions, write_dir)
            if outcomes:
                response += "\n\nACTIONS TAKEN:\n" + "\n".join(outcomes)

        self.memory.extract_and_save_memories(response, role)
        self.db.save_message(self.project_name, "assistant", response)
        self.messages.append({"role": "assistant", "content": response})
        console.print()

    # ------------------------------------------------------------------
    # Slash command handlers
    # ------------------------------------------------------------------

    def load_codebase(self, path_str: str):
        path = Path(path_str).expanduser().resolve()
        if not path.exists():
            console.print(f"[red]Path not found:[/red] {path}")
            return
        if not path.is_dir():
            console.print(f"[red]Not a directory:[/red] {path}")
            return

        with console.status(f"[dim]Scanning {path.name}…[/dim]", spinner="dots"):
            ctx = self._scan_codebase(path)

        self.loaded_path = path
        self.codebase_context = ctx

        # Persist the path so the next session can offer to reload it
        self.memory.save_loaded_path(str(path))

        self.memory.save_project_memory(
            content=(
                f"Codebase loaded: {path}\n"
                f"Tech stack: {', '.join(ctx['tech_stack']) or 'unknown'}\n"
                f"Files: {ctx['total_files']}"
            ),
            category="technical",
            source="load",
        )
        self.display.show_codebase_loaded(path, ctx)

    def unload_codebase(self):
        if not self.loaded_path:
            console.print("[dim]No codebase loaded.[/dim]")
            return
        path = self.loaded_path
        self.loaded_path = None
        self.codebase_context = {}
        self.memory.clear_loaded_path()
        console.print(f"[dim]Unloaded: {path}[/dim]\n")

    def _generate_skill_content(self, role: str, agent_name: str, skill_description: str) -> str:
        """Ask Claude to expand a raw skill description into proper agent instructions."""
        prompt = (
            f"Write a concise skill definition to add to {agent_name}'s ({role}) system prompt.\n"
            f"Skill to add: {skill_description}\n\n"
            "Write 4-6 bullet points of specific, actionable instructions. "
            "Start with a heading: ## Skill: <name>\n"
            "Cover: what they know, how they apply it, and key best practices."
        )
        try:
            return call_claude(
                prompt=prompt,
                system_prompt="You write concise agent skill definitions. Be specific and actionable.",
                model="haiku",  # formatting task — haiku is sufficient and ~3× faster
            )
        except Exception:
            return f"## Skill: {skill_description}\n\n- You have expertise in {skill_description}.\n- Apply best practices for {skill_description} in all relevant work."

    def add_skill(self, role_or_name: str, skill_name: str, description: str = "") -> bool:
        """Generate and save a skill for a role. Returns True on success."""
        role = self._resolve_role(role_or_name)
        if not role or role == "orchestrator":
            console.print(f"[red]Unknown role:[/red] {role_or_name}")
            return False
        persona = self.config["agent_personas"].get(role, {})
        agent_name = persona.get("name", role.upper())
        full_desc = f"{skill_name}: {description}" if description else skill_name
        with console.status(f"[dim]Generating skill definition for {agent_name}…[/dim]", spinner="dots"):
            content = self._generate_skill_content(role, agent_name, full_desc)
            self.memory.save_skill(role, skill_name, content)
        p = self.config["agent_personas"].get(role, {})
        console.print(
            f"\n[green]✓ Skill saved:[/green] [bold]{skill_name}[/bold] → "
            f"{p.get('emoji','')} {agent_name} ({role})\n"
            f"[dim]{agent_name} will apply this from the next response onwards.[/dim]\n"
        )
        return True

    def remove_skill(self, role_or_name: str, skill_name: str):
        role = self._resolve_role(role_or_name)
        if not role:
            console.print(f"[red]Unknown role:[/red] {role_or_name}")
            return
        persona = self.config["agent_personas"].get(role, {})
        agent_name = persona.get("name", role.upper())
        if self.memory.delete_skill(role, skill_name):
            console.print(f"[green]✓ Removed skill:[/green] [bold]{skill_name}[/bold] from {agent_name}")
        else:
            console.print(f"[yellow]Skill not found:[/yellow] {skill_name} on {agent_name}")

    def show_skills(self, role_filter: str | None = None):
        if role_filter:
            resolved = self._resolve_role(role_filter)
            if resolved:
                role_filter = resolved
        skills = self.memory.list_skills(role_filter)
        self.display.show_skills(skills, self.config["agent_personas"])

    def show_status(self):
        from utils.claude_client import get_session_stats
        info = self.db.get_project(self.project_name)
        project_dir = self.base_dir / "projects" / self.project_name
        # Collect real files (not .gitkeep)
        all_files = sorted(project_dir.rglob("*")) if project_dir.exists() else []
        real_files = [f for f in all_files if f.is_file() and f.name != ".gitkeep"]
        # Count docs
        docs_dir = project_dir / "docs"
        doc_files = list(docs_dir.glob("*.md")) if docs_dir.exists() else []
        # Memory entries by category
        entries = self.memory.list_memory_entries()
        category_counts: dict[str, int] = {}
        for e in entries:
            cat = e.get("category", "note")
            category_counts[cat] = category_counts.get(cat, 0) + 1
        # Skills
        skill_counts = {role: self.memory.skill_count(role) for role in self.active_roster}
        total_skills = sum(skill_counts.values())
        # Session stats
        stats = get_session_stats()
        tdd_enabled, tdd_health_cmd = self.memory.load_tdd_mode()
        self.display.show_status(
            project_name=self.project_name,
            info=info,
            active_roster=self.active_roster,
            model=self.model,
            real_files=real_files,
            doc_files=doc_files,
            memory_entries=entries,
            category_counts=category_counts,
            total_skills=total_skills,
            session_stats=stats,
            tdd_enabled=tdd_enabled,
            tdd_health_cmd=tdd_health_cmd,
        )

    def _detect_export_intent(self, user_input: str) -> tuple[str, str] | None:
        """
        Detect export/report generation intent.
        Returns (agent_role, doc_type) or None.
        """
        text = user_input.lower().strip()
        for pattern in _EXPORT_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                keyword = m.group(1).strip().lower().replace(" ", "-")
                # Try exact match first, then prefix match
                if keyword in EXPORT_TYPE_MAP:
                    return EXPORT_TYPE_MAP[keyword]
                for key, val in EXPORT_TYPE_MAP.items():
                    if keyword.startswith(key) or key.startswith(keyword):
                        return val
                # Unknown doc type — default to pm for general summary
                return ("pm", keyword.replace(" ", "-"))
        return None

    def export_doc(self, doc_type: str, agent_role: str | None = None):
        """
        Generate and save a document to projects/<name>/docs/.
        agent_role overrides the default mapping if provided.
        """
        from datetime import datetime

        personas = self.config["agent_personas"]

        # Resolve agent
        if agent_role:
            role = self._resolve_role(agent_role) or "pm"
        else:
            role, doc_type = EXPORT_TYPE_MAP.get(doc_type.lower(), ("pm", doc_type))

        # Ensure the role is available (fall back to any active agent)
        if role not in self.active_roster:
            role = self.active_roster[0]

        p = personas.get(role, {})
        agent_name = p.get("name", role.upper())

        # Build rich context
        memory_text = self.memory.load_project_memory() or "No project memory yet."
        history_text = self._format_history()
        project_dir = self.base_dir / "projects" / self.project_name
        file_list = []
        if project_dir.exists():
            file_list = [
                str(f.relative_to(project_dir))
                for f in sorted(project_dir.rglob("*"))
                if f.is_file() and f.name != ".gitkeep"
            ]

        export_prompt = (
            f"Project: {self.project_name}\n"
            f"Document to produce: {doc_type}\n\n"
            f"## Project Memory\n{memory_text}\n\n"
            f"## Recent Conversation\n{history_text or 'No history.'}\n\n"
            f"## Files Created So Far\n" + ("\n".join(file_list) if file_list else "None yet.") + "\n\n"
            f"Write a complete, well-structured {doc_type} in Markdown format. "
            f"Base it entirely on what has been discussed and decided. "
            f"Use proper headings, tables where appropriate, and be thorough. "
            f"Do NOT use EXEC: blocks — output only the document content."
        )

        console.print(
            f"\n[bold bright_cyan]📄 Generating {doc_type}…[/bold bright_cyan]"
            f"  [dim]{p.get('emoji','')} {agent_name} is writing[/dim]\n"
        )

        agent = self.agents.get(role)
        if not agent:
            console.print(f"[red]Agent {role} not available.[/red]")
            return

        try:
            with console.status(
                f"[{p.get('color','white')}]{p.get('emoji','')} {agent_name} writing {doc_type}…[/{p.get('color','white')}]",
                spinner="dots"
            ):
                content = agent.respond(
                    task=export_prompt,
                    context=f"Generating {doc_type} for project: {self.project_name}",
                    history_text="",
                )
        except KeyboardInterrupt:
            console.print("\n[yellow]⚡ Export interrupted.[/yellow]")
            return

        # Save to docs/
        docs_dir = project_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{doc_type}-{date_str}.md"
        out_path = docs_dir / filename
        out_path.write_text(content, encoding="utf-8")

        # Show a clean confirmation — no truncated preview spam.
        # The full doc is on disk; the user can 'show <filename>' to read it.
        _NEXT_HINTS = {
            "requirements":    "start sprint planning or implementation",
            "requirements-doc":"start sprint planning or implementation",
            "user-stories":    "start implementation or review the stories",
            "sprint-plan":     "work on epics, assign stories, or start implementation",
            "architecture":    "write a technical spec or start implementation",
            "architecture-doc":"write a technical spec or start implementation",
            "technical-spec":  "start implementation",
            "tech-spec":       "start implementation",
            "api-docs":        "start implementation or write a test plan",
            "test-plan":       "run tests or review test coverage",
            "deployment-plan": "deploy the application",
        }
        hint = _NEXT_HINTS.get(doc_type.lower(), "continue planning or start the next phase")
        console.print(
            f"\n[bold green]✓ Document created:[/bold green] "
            f"[cyan]projects/{self.project_name}/docs/{filename}[/cyan]  "
            f"[dim]{len(content.splitlines())} lines · {len(content):,} chars[/dim]"
        )
        console.print(f"[dim]  Read it: show {filename}[/dim]")
        console.print(f"[dim]  Next:    {hint}[/dim]\n")

        # Save a compact summary to memory so future sessions know what's defined
        try:
            summary_prompt = (
                f"This is a {doc_type} document. Extract the most important items as "
                f"4-8 bullet points (epics, user stories, key decisions, scope, tech choices — "
                f"whatever matters most). Each bullet max 90 chars. Start each with •\n\n"
                f"Document:\n{content[:5000]}"
            )
            summary = call_claude(
                prompt=summary_prompt,
                system_prompt="You write concise document summaries. Output bullet points only, no intro text.",
                model=self.model,
            )
            self.memory.save_project_memory(
                content=f"Document: {doc_type} ({filename})\n{summary}",
                category="document",
                source="export",
            )
        except Exception:
            # Summary is nice-to-have — don't fail the export if it errors
            self.memory.save_project_memory(
                content=f"Generated {doc_type} → docs/{filename}",
                category="document",
                source="export",
            )

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
        counts = {role: self.memory.skill_count(role) for role in self.active_roster}
        self.display.show_team(self.active_roster, self.config["agent_personas"], skill_counts=counts)

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
