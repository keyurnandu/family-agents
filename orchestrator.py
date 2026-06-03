from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console

from agents.agent import Agent
from utils.action_executor import parse_actions, prompt_and_execute
from utils.claude_client import call_claude, call_claude_json, set_analytics_context
from utils.db_manager import DBManager
from utils.display import Display, _ts
from utils.memory_manager import MemoryManager

console = Console()

# Auto-pilot iteration control:
# - Normal mode: pauses every CHECKPOINT_INTERVAL iterations for manual "continue"
# - /auto mode: Aria auto-resets at each checkpoint if no issues detected,
#   up to AUTO_HARD_CEILING total iterations (absolute safety net).
AUTO_CHECKPOINT_INTERVAL = 5
AUTO_HARD_CEILING = 50

# Directories to ignore when scanning project/codebase folder trees.
# Shared between _scan_codebase() and _update_project_state().
_SCAN_IGNORE = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "target", ".gradle", ".idea", ".vscode",
}

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
# Next-step hints for each export doc type — used by both export_doc display
# and the export path in process() to give auto-pilot rich context.
_EXPORT_NEXT_HINTS = {
    "requirements":     "start sprint planning or implementation",
    "requirements-doc": "start sprint planning or implementation",
    "user-stories":     "start implementation or review the stories",
    "sprint-plan":      "work on epics, assign stories, or start implementation",
    "architecture":     "write a technical spec or start implementation",
    "architecture-doc": "write a technical spec or start implementation",
    "technical-spec":   "start implementation",
    "tech-spec":        "start implementation",
    "api-docs":         "start implementation or write a test plan",
    "test-plan":        "run tests or review test coverage",
    "deployment-plan":  "deploy the application",
}

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
                        "description": "Roles to run in parallel during this phase. May include bench agents (researcher, qa, devops) when their specialty is clearly needed — they will be pulled in automatically for the phase.",
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
_CORRECTION_RE = re.compile(
    r"\b(?:stop|never|don'?t|do not|avoid|wrong|incorrect|"
    r"you should(?:'ve| have)?|next time|always|instead of|"
    r"that'?s (?:wrong|incorrect|not right)|"
    r"should(?:'ve| have) (?:used?|done?|run|written?))\b",
    re.IGNORECASE,
)

_CODE_REQUEST_RE = re.compile(
    r"\b(?:write|create|build|implement|generate|make)\s+"
    r"(?:a\s+|an\s+|the\s+)?(?:function|class|file|script|code|"
    r"module|api|endpoint|component|service)\b",
    re.IGNORECASE,
)

_CODEBASE_INTENT_RE = re.compile(
    r"\b(?:review|read|show|open|check|audit|inspect|analyse|analyze|"
    r"implement|write|fix|refactor|update|modify|change|edit|"
    r"work\s+on|look\s+at|go\s+through|epic|story|sprint|feature|"
    r"file|files|code|codebase|class|function|method|module|"
    r"endpoint|api|service|controller|model|schema)\b",
    re.IGNORECASE,
)

_FILE_ERROR_RE = re.compile(
    r"^(?:I couldn't find|No codebase is currently loaded)",
    re.IGNORECASE,
)

_EPIC_KICKOFF_RE = re.compile(
    r"\b(?:work\s+on|start|implement|begin|kick\s*off|tackle|do|complete|finish)\s+"
    r"(?:epic|story|e\d+|s\d+|sprint)",
    re.IGNORECASE,
)

# Pre-filter for the clarification gate — only triggers on substantial new-build requests
_LARGE_BUILD_RE = re.compile(
    r"\b(?:build|create|implement|develop|design|architect|make)\s+"
    r"(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:complete|full|entire|whole\s+)?"
    r"(?:app(?:lication)?|system|platform|service|website|product|solution|"
    r"backend|frontend|api|database|microservice|module|component)\b",
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
        config: Optional[dict] = None,
    ):
        self.project_name = project_name
        self.base_dir = base_dir
        self.db = db
        self.display = display

        if config is not None:
            self.config = config
        else:
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

        # Last user input — used by /redo to re-submit or edit after Ctrl+C
        self.last_user_input: str = ""
        self._interrupted: bool = False  # set True when Ctrl+C fires mid-process

        # ── Per-turn caches (reset at the start of every process() call) ──
        # Load docs/memory/TDD once per turn — shared across routing,
        # synthesis, and synthesis system prompt — instead of reloading
        # from disk 3+ times per user message.
        self._turn_docs: str = ""
        self._turn_memory: str = ""
        self._turn_tdd: tuple[bool, str] = (False, "")
        self._turn_auto: bool = False

        # Routing prompt cache — keyed by (roster, mem_count, tdd_state, state_mtime).
        # Rebuilt only when something actually changes, not on every message.
        self._routing_prompt_cache: str = ""
        self._routing_prompt_key: str = ""
        self._routing_doc_index_cache: str = ""
        self._routing_doc_index_key: str = ""

        # Per-turn project state (state.md) — loaded once, used in routing + synthesis
        self._turn_state: str = ""
        self._state_lock = threading.Lock()

        # Pending auto-pilot context — saved when autopilot stops prematurely
        # (cap reached, failure, duplicate loop) so user can type "continue" to resume.
        # Set to None when work is complete or user interrupts.
        self._pending_autopilot: dict | None = None

        # Cache key for project-dir auto-scan — avoids rescanning every turn
        # when no files have changed.  Stores a frozenset of (relpath, mtime).
        self._project_scan_key: frozenset | None = None

        # Skill consolidation — runs once per session on the first process() call.
        self._skills_consolidated: bool = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extra_normalize_dirs(self, project_dir: Path) -> list[Path] | None:
        """Build the list of extra directories to strip from EXEC:bash commands.

        When a codebase is /loaded at a short path (e.g. C:\\uishift\\backend2),
        the write_dir is that loaded path — but agents may still emit the long
        OneDrive-based project_dir or the family-agents base_dir in commands.
        Returns a list of those extra paths, or None when unnecessary.
        """
        extras: list[Path] = []
        if self.loaded_path and self.loaded_path != project_dir:
            extras.append(project_dir)
        # Always include base_dir — agents may reference family-agents root
        if self.base_dir != project_dir and (not self.loaded_path or self.base_dir != self.loaded_path):
            extras.append(self.base_dir)
        return extras or None

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
        IGNORE = _SCAN_IGNORE

        file_count = 0

        def build_tree(p: Path, prefix: str = "", depth: int = 0) -> list[str]:
            nonlocal file_count
            lines: list[str] = []
            try:
                items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
            except PermissionError:
                return []
            visible = [i for i in items if i.name not in IGNORE and not i.name.startswith(".")]
            for idx, item in enumerate(visible):
                if depth <= 3:
                    connector = "└── " if idx == len(visible) - 1 else "├── "
                    lines.append(f"{prefix}{connector}{item.name}{'/' if item.is_dir() else ''}")
                if item.is_file():
                    file_count += 1
                elif item.is_dir():
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

        return {
            "structure_tree": structure_tree,
            "key_files": key_file_contents,
            "tech_stack": tech_stack,
            "total_files": file_count,
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

        Cached: rebuilt only when roster, memory count, TDD state, or project state changes.
        """
        # Build cache key — include state mtime so it rebuilds when state.md is updated
        tdd_enabled, _ = self._turn_tdd
        state_file = self.base_dir / "projects" / self.project_name / "state.md"
        state_mtime = f"{state_file.stat().st_mtime:.0f}" if state_file.exists() else "0"
        cache_key = (
            f"{sorted(self.active_roster)}:{len(self.memory.list_memory_entries())}"
            f":{tdd_enabled}:{state_mtime}"
        )
        if self._routing_prompt_key == cache_key and self._routing_prompt_cache:
            return self._routing_prompt_cache

        # Use turn-level pre-loaded memory (already capped to routing limit)
        routing_mem_limit = self.config.get("max_routing_memory", 8)
        project_memory = self.memory.load_project_memory(limit=routing_mem_limit)

        # For docs: titles + one-line summaries only — not full content
        doc_index = self._routing_doc_index()

        team_lines = [
            f"- {role} ({self.config['agent_personas'].get(role, {}).get('name', role)}): "
            f"{ROLE_DESCRIPTIONS.get(role, '')}"
            for role in self.active_roster
        ]

        # Bench agents — available to pull in when clearly needed
        bench_roles = [
            r for r in self.config["team"]["available_agents"]
            if r not in self.active_roster
        ]
        bench_lines = [
            f"- {role} ({self.config['agent_personas'].get(role, {}).get('name', role)}): "
            f"{ROLE_DESCRIPTIONS.get(role, '')}"
            for role in bench_roles
        ]

        # TDD mode context — injected into routing only when active (not on every call)
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

        # Project state — inject a compact routing summary when available
        state_section = ""
        routing_state = self._routing_state_summary(self._turn_state)
        if routing_state:
            state_section = f"## Project State\n{routing_state[:700]}\n\n"

        prompt = (
            f"You are Aria, the project coordinator for '{self.project_name}'. "
            "Your ONLY job here is to decide which agents to involve and what to ask each one.\n\n"
            f"## Active Team\n" + "\n".join(team_lines) + "\n\n"
            + (
                "## Bench Agents (pull in when their specialty is clearly needed)\n"
                + "\n".join(bench_lines) + "\n"
                "Include a bench agent in a phase's agents list when their expertise is clearly "
                "required. Do NOT add them for simple tasks where active team can handle it.\n\n"
                if bench_lines else ""
            )
            + (f"## Recent Project Memory\n{project_memory}\n\n" if project_memory else "")
            + (f"## Existing Documents\n{doc_index}\n\n" if doc_index else "")
            + state_section
            + tdd_section
            + "## Routing Rules\n"
            "- Use sequential PHASES only when tasks genuinely depend on each other "
            "(requirements → implementation → QA → devops).\n"
            "- Use a SINGLE phase for questions, discussions, reviews, or anything "
            "that doesn't need hand-offs.\n"
            "- Agents within a phase run in parallel — assign each a DIFFERENT task. "
            "Never assign the same task (e.g. 'run tests', 'verify') to multiple agents "
            "in the same phase — pick the one best suited and give others distinct work.\n"
            "- If docs already cover requirements, skip the requirements phase.\n"
            "- If the Project State shows something is already complete, do not re-do it.\n"
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
        # Store in cache
        self._routing_prompt_cache = prompt
        self._routing_prompt_key = cache_key
        return prompt

    def _routing_doc_index(self) -> str:
        """Return a compact one-line-per-doc index for routing context."""
        docs_dirs = []
        if self.loaded_path:
            loaded_docs = self.loaded_path / "docs"
            if loaded_docs.exists():
                docs_dirs.append(loaded_docs)
        internal_docs = self.base_dir / "projects" / self.project_name / "docs"
        if internal_docs.exists():
            docs_dirs.append(internal_docs)
        if not docs_dirs:
            self._routing_doc_index_cache = ""
            self._routing_doc_index_key = ""
            return ""

        seen_names: set[str] = set()
        files = []
        for docs_dir in docs_dirs:
            for f in sorted(docs_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True):
                if f.name in seen_names:
                    continue
                seen_names.add(f.name)
                files.append(f)
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            self._routing_doc_index_cache = ""
            self._routing_doc_index_key = ""
            return ""

        indexed = files[:5]
        cache_key = "|".join(
            f"{f}:{f.stat().st_mtime_ns}:{f.stat().st_size}" for f in indexed
        )
        if cache_key == self._routing_doc_index_key:
            return self._routing_doc_index_cache

        lines = []
        for f in indexed:
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
        result = "\n".join(lines)
        self._routing_doc_index_cache = result
        self._routing_doc_index_key = cache_key
        return result

    @staticmethod
    def _routing_state_summary(state_text: str) -> str:
        """Return the small state slice needed by routing.

        Prefer the explicit ``## Routing Summary`` section. Older state.md files
        do not have it, so fall back to the first few non-heading lines.
        """
        if not state_text or not state_text.strip():
            return ""

        match = re.search(
            r"^## Routing Summary\s*\n(.*?)(?=^##\s+|\Z)",
            state_text,
            flags=re.MULTILINE | re.DOTALL,
        )
        if match and match.group(1).strip():
            return "## Routing Summary\n" + match.group(1).strip()

        lines = [
            line.strip()
            for line in state_text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        return "\n".join(lines[:8])

    def _synthesis_system_prompt(self) -> str:
        """System prompt for Aria's synthesis/direct-answer calls.
        Includes role memory, project documents, and CRITICAL CONSTRAINT so Aria
        never asks the customer to re-provide information that is already on disk.

        Uses turn-level cached docs/memory — no extra disk reads per synthesis call.
        """
        role_memory = self.memory.load_role_memory("orchestrator")

        # Re-use docs and memory already loaded at the start of this turn.
        # Avoids duplicate disk reads — agents already loaded these same slices.
        docs_section = (
            f"\n\n## Project Documents\n{self._turn_docs}"
            if self._turn_docs else ""
        )
        memory_section = (
            f"\n\n## Project Memory (recent)\n{self._turn_memory}"
            if self._turn_memory else ""
        )

        constraint = (
            "\n\n## CRITICAL CONSTRAINT\n"
            "You are text-only: do not call tools, output READ_FILE markers, or mention "
            "Claude Code internals, .claude folders, settings.json, permission dialogs, "
            "allow lists, permission walls, or work directories. "
            "Do not mention sandbox, locked sessions, or restricted filesystem access. "
            "NEVER tell the customer to 'approve a write' or 'approve permissions' — "
            "the harness handles all permissions automatically. "
            "NEVER say 'can't verify remotely', 'working directory is wrong', 'paste the output', "
            "'run this in your terminal', or any variant — the team CAN run commands via EXEC:bash. "
            "If a command failed, diagnose and fix the command — do not ask the customer to run it manually. "
            "Use project documents already in context instead of asking the customer to paste them. "
            "If specialists could not read a file, say it was not available this turn and the team will retry. "
            "If agents proposed EXEC file/bash blocks, summarize the proposed write/run briefly; "
            "the harness already handles approval."
        )
        return f"{role_memory}{docs_section}{memory_section}{constraint}"

    @staticmethod
    def _trim_for_synthesis(response: str) -> str:
        """
        Prepare an agent response for Aria's synthesis prompt.
        - Strip EXEC file/bash blocks (Aria doesn't need 200-line files)
        - Condense large OUTPUT sections in ACTIONS TAKEN to a one-line summary
          (e.g. "25 passed in 3.42s") — Aria needs the outcome, not the full log
        """
        # Strip EXEC blocks
        text = re.sub(
            r"EXEC:file:([^\n]+)\n```[^\n]*\n(.*?)```",
            lambda m: f"\n[📄 `{m.group(1).strip()}` — {len(m.group(2).strip().splitlines())} lines · shown in apply prompt]\n",
            response,
            flags=re.DOTALL | re.IGNORECASE,
        )
        text = re.sub(
            r"EXEC:bash\s*\n```[^\n]*\n.*?```",
            "\n[🔧 shell command · shown in apply prompt]\n",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Condense large OUTPUT blocks — keep only the last 3 lines (summary line)
        def _trim_output(m):
            header = m.group(1)   # e.g. "BASH OK: pytest"
            output = m.group(2).strip()
            lines = output.splitlines()
            if len(lines) <= 3:
                return f"{header}\nOUTPUT:\n{output}"
            summary = "\n".join(lines[-3:])  # last 3 lines = pytest summary
            return f"{header}\nOUTPUT (last 3 lines):\n{summary}"
        text = re.sub(
            r"((?:BASH OK|BASH FAILED[^\n]*):.*?)\nOUTPUT:\n(.*?)(?=\n(?:BASH|FILE|HEALTH|$)|\Z)",
            _trim_output,
            text,
            flags=re.DOTALL,
        )
        return text.strip()

    _SYNTHESIS_PER_AGENT_CAP = 1600

    @staticmethod
    def _should_synthesize(agent_responses: dict, all_file_errors: bool) -> bool:
        """Return True when an extra Aria synthesis call is worth the tokens."""
        if all_file_errors or len(agent_responses) <= 1:
            return False

        low_value_replies = {
            "ok", "okay", "looks good", "looks good.", "no concerns",
            "nothing to add", "nothing to add.", "agreed", "agree",
        }

        substantive = 0
        for response in agent_responses.values():
            text = (response or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in low_value_replies:
                continue
            if "ACTIONS TAKEN:" in text or "EXEC:file:" in text or "EXEC:bash" in text:
                substantive += 1
                continue
            if len(text) >= 40:
                substantive += 1

        return substantive > 1

    def _synthesis_prompt(self, user_input: str, agent_responses: dict) -> str:
        parts = [
            f"The customer said:\n{user_input}\n\n"
            "The team has weighed in:\n"
        ]
        personas = self.config["agent_personas"]
        cap = self._SYNTHESIS_PER_AGENT_CAP
        for role, response in agent_responses.items():
            name = personas.get(role, {}).get("name", role.upper())
            display_response = self._trim_for_synthesis(response)
            if len(display_response) > cap:
                display_response = display_response[:cap] + "\n[truncated]"
            parts.append(f"[{name} — {role.upper()}]\n{display_response}\n")

        state_hint = ""
        if self._turn_state:
            state_hint = (
                f"\n\n## Current Project State (use this for context-aware next-step suggestions)\n"
                f"{self._turn_state[:600]}"
            )

        synth_instruction = (
            "\nAs Aria, the coordinator, synthesize these into a clear, unified response "
            "for the customer. Be concise. Credit team members where relevant. "
            "If agents have file changes queued, state what will be written — do NOT tell the customer to approve or that they will be prompted. "
            "If there are open questions for the customer, group them at the end."
            + state_hint
            + "\n\nEnd with a concise status summary of what was accomplished. "
            "If there is clear follow-up work, briefly state what the team will do next. "
            "Do NOT ask 'What would you like to do next?' or list numbered options — "
            "the system will automatically continue if there is actionable work remaining."
        )
        parts.append(synth_instruction)
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Skill consolidation — merge redundant lessons when files get large
    # ------------------------------------------------------------------

    # Consolidation fires when an auto-learned.md exceeds this many chars.
    _CONSOLIDATION_THRESHOLD = 1800
    _CONSOLIDATION_MIN_LESSONS = 6
    # Minimum days between consolidation runs (checked via .bak mtime).
    _CONSOLIDATION_COOLDOWN_DAYS = 7

    def _consolidate_skills_if_needed(self) -> None:
        """Check every active agent's auto-learned file; consolidate if large.

        Runs at most once per ``_CONSOLIDATION_COOLDOWN_DAYS`` (checked via
        the ``.bak`` file's mtime).  Within a session, guarded by
        ``_skills_consolidated`` so the check is a single stat() call on
        subsequent ``process()`` calls.

        Uses Haiku to merge redundant lessons, remove stale ones, and
        compress — keeping the file concise and token-efficient.
        Backs up the original to ``.bak`` before overwriting.
        """
        if self._skills_consolidated:
            return
        self._skills_consolidated = True

        import time
        from agents.agent import Agent

        skills_dir = self.memory._skills_dir
        if not skills_dir.exists():
            return

        cooldown_seconds = self._CONSOLIDATION_COOLDOWN_DAYS * 86400

        for role in list(self.agents.keys()):
            learned_path = skills_dir / role / "auto-learned.md"
            if not learned_path.exists():
                continue

            # Cooldown check — skip if last consolidation was recent
            backup_path = learned_path.with_suffix(".md.bak")
            if backup_path.exists():
                age = time.time() - backup_path.stat().st_mtime
                if age < cooldown_seconds:
                    continue

            content = learned_path.read_text(encoding="utf-8")
            if len(content) < self._CONSOLIDATION_THRESHOLD:
                continue

            # Count lessons (### headers)
            lesson_count = content.count("\n### ")
            if lesson_count < self._CONSOLIDATION_MIN_LESSONS:
                continue

            persona = self.config["agent_personas"].get(role, {})
            name = persona.get("name", role.upper())

            try:
                consolidated = call_claude(
                    prompt=(
                        f"Below are {lesson_count} lessons auto-learned by {name} ({role}).\n"
                        "Many are redundant, stale, or overly verbose.\n\n"
                        "CONSOLIDATE them into a concise, non-redundant set:\n"
                        "- Merge duplicates into one crisp rule\n"
                        "- Drop lessons that contradict each other (keep the latest)\n"
                        "- Drop lessons that are too vague or not actionable\n"
                        "- Keep the '### [date] via trigger' format for each lesson\n"
                        "  (use the most recent date when merging duplicates)\n"
                        "- Start the file with the same header line\n"
                        "- Aim for ≤30% of the original lesson count\n\n"
                        "Return ONLY the consolidated markdown file content, "
                        "nothing else.\n\n"
                        "---\n\n"
                        f"{content}"
                    ),
                    system_prompt=(
                        "You consolidate auto-learned lessons for an AI agent. "
                        "Be ruthless about deduplication — if 10 lessons say "
                        "'verify imports before running pytest', keep ONE that "
                        "captures the best version. Preserve actionable specifics. "
                        "Output only the consolidated markdown."
                    ),
                    model="haiku",
                )
            except Exception as exc:
                console.print(
                    f"[dim yellow]  ⚠ Skill consolidation failed for {name}: {exc}[/dim yellow]"
                )
                continue

            if not consolidated or len(consolidated.strip()) < 100:
                continue  # sanity check — don't overwrite with empty/tiny result

            # Back up original with timestamped name, then write consolidated.
            # The plain .bak is also written — its mtime drives the cooldown.
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d")
            versioned_bak = learned_path.with_suffix(f".{ts}.bak")
            if not versioned_bak.exists():
                versioned_bak.write_text(content, encoding="utf-8")
            # Plain .bak — used for cooldown mtime check
            backup_path = learned_path.with_suffix(".md.bak")
            backup_path.write_text(content, encoding="utf-8")
            learned_path.write_text(consolidated.strip() + "\n", encoding="utf-8")

            # Evict cached prompts for this role
            Agent._prompt_cache = {
                k: v for k, v in Agent._prompt_cache.items()
                if k[0] != role
            }

            new_count = consolidated.count("\n### ")
            console.print(
                f"[dim green]  🧹 {persona.get('emoji', '')} {name}: "
                f"consolidated {lesson_count} → {new_count} lessons "
                f"({len(content):,} → {len(consolidated):,} chars)[/dim green]"
            )

    # ------------------------------------------------------------------
    # Feedback loop — auto-learning from failures, corrections, retrospectives
    # ------------------------------------------------------------------

    def _apply_lesson(self, role: str, lesson: str) -> None:
        """
        Persist a lesson and make it active immediately:
        1. Save to auto-learned.md (persists across sessions)
        2. Evict the agent's cached system prompt so next call rebuilds
           with the lesson included — not just on the next session start
        3. Inject a visible note into conversation history so the lesson
           appears in context (the agent reads history, not just system prompt)
        """
        from agents.agent import Agent
        p = self.config["agent_personas"].get(role, {})
        name = p.get("name", role.upper())

        self.memory.save_auto_skill(role, lesson, "lesson")

        # Force-evict ALL cached prompts for this role so next call rebuilds
        Agent._prompt_cache = {
            k: v for k, v in Agent._prompt_cache.items()
            if k[0] != role
        }

        # Inject into conversation history so the agent sees it in context,
        # not just buried in the system prompt — history has stronger influence
        note = f"[LESSON LEARNED by {name}]: {lesson}"
        self.messages.append({"role": "assistant", "content": note})

        console.print(
            f"[dim green]  📚 {p.get('emoji', '')} {name} learned: "
            f"{lesson[:80]}{'…' if len(lesson) > 80 else ''}[/dim green]"
        )

    def _extract_lesson(self, role: str, failure_context: str, trigger: str) -> None:
        """
        Call haiku to distill a concise, actionable lesson from a failure
        and immediately apply it via _apply_lesson.
        """
        persona = self.config["agent_personas"].get(role, {})
        name = persona.get("name", role.upper())
        prompt = (
            f"You are {name}, a {role} on a software development team.\n\n"
            f"Something just went wrong:\n{failure_context}\n\n"
            "Write ONE concise, actionable lesson you will apply next time. "
            "Start with 'Always', 'Never', or 'Before'. "
            "Be specific — reference the exact command, tool, or pattern involved. "
            "Maximum 2 sentences. No preamble, no explanation."
        )
        try:
            set_analytics_context(call_type="lesson", agent_role=role)
            lesson = call_claude(
                prompt=prompt,
                system_prompt="You extract precise, actionable lessons from failures. Be specific, not generic.",
                model="haiku",
            )
            if lesson.strip():
                self._apply_lesson(role, lesson.strip())
        except Exception:
            pass  # non-critical — never block

    def _check_outcomes_for_lessons(self, role: str, outcomes: list[str]) -> None:
        """After an agent's actions, batch all failures into ONE haiku call.
        Previously called _extract_lesson once per failure — now collects all
        failures and makes a single call, saving N-1 LLM calls per multi-failure turn.
        """
        failures: list[str] = []
        for outcome in outcomes:
            if outcome.startswith("BASH FAILED"):
                failures.append(f"Bash command failed:\n{outcome}")
            elif outcome.startswith("HEALTH_CHECK: FAILED"):
                snippet = outcome.replace("HEALTH_CHECK: FAILED", "").strip()
                failures.append(f"Health check failed after writing files:\n{snippet}")

        if not failures:
            return

        if len(failures) == 1:
            # Single failure — use existing single-lesson path
            self._extract_lesson(role, failures[0], trigger="bash-failure")
            return

        # Multiple failures — one batched haiku call for all of them
        persona = self.config["agent_personas"].get(role, {})
        name = persona.get("name", role.upper())
        failures_text = "\n\n---\n\n".join(
            f"Failure {i+1}:\n{f}" for i, f in enumerate(failures)
        )
        prompt = (
            f"You are {name}, a {role} on a software development team.\n\n"
            f"Multiple things went wrong in this turn:\n\n{failures_text}\n\n"
            f"Write {len(failures)} concise, actionable lessons — one per failure. "
            "Number them 1., 2., etc. "
            "Each lesson must start with 'Always', 'Never', or 'Before'. "
            "Be specific — reference the exact command, tool, or pattern. "
            "One sentence each. No preamble."
        )
        try:
            response = call_claude(
                prompt=prompt,
                system_prompt="You extract precise, actionable lessons from failures. Be specific, not generic.",
                model="haiku",
            )
            # Parse numbered lessons and save each one
            lesson_lines = [
                line.lstrip("0123456789. ").strip()
                for line in response.splitlines()
                if line.strip() and line.strip()[0].isdigit()
            ]
            if not lesson_lines:
                lesson_lines = [response.strip()]
            for lesson in lesson_lines:
                if lesson:
                    self._apply_lesson(role, lesson)
        except Exception:
            pass  # non-critical — never block

    def _detect_and_save_correction(self, user_input: str) -> bool:
        """
        Detect when the user is correcting an agent and save the lesson
        as a skill for the relevant agent. Returns True if a correction was saved.
        """
        if not _CORRECTION_RE.search(user_input):
            return False

        # Find which agent the correction is about
        target_role = None
        for role, persona in self.config["agent_personas"].items():
            name = persona.get("name", "").lower()
            if name and name in user_input.lower():
                target_role = role
                break
            if role != "orchestrator" and role in user_input.lower():
                target_role = role
                break

        # If no explicit mention, apply to the last agent who acted
        if not target_role and self.messages:
            # Look at recent assistant messages to infer who was last active
            for msg in reversed(self.messages[-6:]):
                if msg["role"] == "assistant":
                    for role in self.active_roster:
                        name = self.config["agent_personas"].get(role, {}).get("name", "").lower()
                        if name and f"[{name}" in msg["content"].lower():
                            target_role = role
                            break
                    if target_role:
                        break

        if not target_role:
            return False

        self._extract_lesson(
            target_role,
            f"User correction: {user_input.strip()}",
            trigger="user-correction",
        )
        return True

    def run_retrospective(self) -> None:
        """
        Ask each active agent to reflect on the session and extract one
        actionable lesson. Lessons are saved to their auto-learned skill file.
        """
        console.print(
            "\n[bold bright_cyan]🔄 Session Retrospective[/bold bright_cyan]  "
            "[dim]Each agent reflects on what they'd do differently…[/dim]\n"
        )

        history_text = self._format_history(limit=10)
        if not history_text:
            console.print("[dim]No session history to reflect on yet.[/dim]\n")
            return

        roles_to_reflect = [r for r in self.active_roster if r != "orchestrator"]

        for role in roles_to_reflect:
            persona = self.config["agent_personas"].get(role, {})
            name = persona.get("name", role.upper())
            color = persona.get("color", "white")
            emoji = persona.get("emoji", "")

            prompt = (
                f"You are {name}, a {role} on a software development team.\n\n"
                f"Here is what happened in this session:\n{history_text}\n\n"
                "Based on this session, identify ONE specific, actionable lesson "
                "you would apply differently next time. Focus on any mistakes, "
                "inefficiencies, or better approaches you notice in your own work. "
                "If you performed well this session, identify a habit worth reinforcing.\n\n"
                "Format: a single bullet point starting with 'Always', 'Never', or 'Before'. "
                "Be concrete and specific — reference actual tools, commands, or patterns "
                "from this session. Maximum 2 sentences."
            )

            try:
                with console.status(
                    f"[{color}]{emoji} {name} reflecting…[/{color}]", spinner="dots"
                ):
                    lesson = call_claude(
                        prompt=prompt,
                        system_prompt=(
                            f"You are {name} ({role}). Extract a precise, actionable lesson "
                            "from your own performance this session. Be self-critical and specific."
                        ),
                        model="haiku",
                    )

                if lesson.strip():
                    self._apply_lesson(role, lesson.strip())
                    console.print(
                        f"[{color}]{emoji} {name}[/{color}]  "
                        f"[dim]{lesson.strip()}[/dim]"
                    )
                    console.print(f"  [dim green]✓ Saved to {name}'s skills[/dim green]\n")
            except Exception as e:
                console.print(f"[dim yellow]  {name} reflection failed: {e}[/dim yellow]\n")

        console.print("[dim]Retrospective complete. Lessons saved and active immediately.[/dim]\n")

    def add_feedback(self, role_identifier: str, lesson: str) -> None:
        """Save a direct user-provided lesson as a skill for the named agent."""
        role = self._resolve_role(role_identifier)
        if not role or role == "orchestrator":
            console.print(
                f"[yellow]Unknown agent:[/yellow] {role_identifier}  "
                "[dim]Use @name or role key (sam, jordan, casey, etc.)[/dim]"
            )
            return
        self._apply_lesson(role, lesson.strip())
        persona = self.config["agent_personas"].get(role, {})
        name = persona.get("name", role.upper())
        console.print(
            f"\n[green]✓ Feedback saved to {name}'s skills and active immediately:[/green]  [dim]{lesson.strip()}[/dim]\n"
        )

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
            "- Do NOT ask for permission or confirmation — output all EXEC: blocks now.\n\n"
            "Virtual environment (Python projects only):\n"
            "- If the project is Python-based, add a FINAL EXEC:bash block after all files that:\n"
            "  1. Creates the venv:   python -m venv venv\n"
            "  2. Installs deps:      venv\\Scripts\\python.exe -m pip install -r requirements.txt\n"
            "- Use a single EXEC:bash block for both commands chained with &&.\n"
            "- Skip this entirely for non-Python projects (Node, Go, Rust, Java, etc.)."
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
                scaffold_outcomes = prompt_and_execute(actions, write_dir, normalize_dirs=self._extra_normalize_dirs(project_dir), auto_mode=self._turn_auto)
                if scaffold_outcomes:
                    self._log_failures_from_outcomes(scaffold_outcomes, p.get("name", role.upper()), "scaffold")

            self.memory.extract_and_save_memories(response, role)

        console.print(
            "\n[dim]🏗️  Scaffold complete — "
            "project structure is ready in [cyan]projects/"
            + self.project_name
            + "/[/cyan][/dim]\n"
        )

    # ------------------------------------------------------------------
    # Project state — structured awareness of what exists and what's next
    # ------------------------------------------------------------------

    def _load_project_state(self) -> str:
        """Read state.md if it exists. Returns empty string when not yet created."""
        state_file = self.base_dir / "projects" / self.project_name / "state.md"
        if not state_file.exists():
            return ""
        try:
            return state_file.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _update_project_state(
        self, user_input: str, agent_responses: dict, final_response: str
    ) -> None:
        """
        After each exchange, ask Haiku to update state.md with a structured snapshot
        of what exists, what's in progress, open decisions, and logical next steps.

        Runs in a daemon background thread — never blocks the main flow.
        The updated state is used on the NEXT turn by routing and synthesis.
        """
        def _update() -> None:
            with self._state_lock:
                try:
                    current_state = self._load_project_state()
                    project_dir = self.base_dir / "projects" / self.project_name

                    # Collect real files (skip .gitkeep, state.md, docs/, venv, node_modules)
                    file_list: list[str] = []
                    if project_dir.exists():
                        file_list = [
                            str(f.relative_to(project_dir))
                            for f in sorted(project_dir.rglob("*"))
                            if f.is_file()
                            and f.name not in (".gitkeep", "state.md")
                            and not str(f.relative_to(project_dir)).startswith("docs")
                            and not any(part in _SCAN_IGNORE for part in f.relative_to(project_dir).parts)
                        ][:20]

                    # Compact summary of agent responses for the prompt
                    personas = self.config["agent_personas"]
                    agent_summary = "\n".join(
                        f"[{personas.get(r, {}).get('name', r)}]: {resp[:500]}"
                        for r, resp in agent_responses.items()
                    )

                    prompt = (
                        f"Project: {self.project_name}\n\n"
                        f"Customer just asked: {user_input}\n\n"
                        f"Team responses:\n{agent_summary[:2000]}\n\n"
                        f"Files on disk: {', '.join(file_list) or 'none yet'}\n\n"
                        + (f"Previous state.md:\n{current_state}\n\n" if current_state else "")
                        + "Output a COMPLETE replacement state.md in this EXACT format "
                        "(keep each section to max 5 bullets, be factual and specific):\n\n"
                        "# Project State\n\n"
                        "## Routing Summary\n"
                        "(3-5 terse bullets with only facts Aria needs for routing next turn)\n\n"
                        "## What exists\n"
                        "(files/components that are complete)\n\n"
                        "## In progress\n"
                        "(what's being built but not done yet)\n\n"
                        "## Open decisions\n"
                        "(key tech/design choices made — with date if known)\n\n"
                        "## Next logical steps\n"
                        "(2-3 concrete things that logically follow from current state)\n\n"
                        "Use actual names/paths from context. Do NOT invent things not mentioned."
                    )

                    updated = call_claude(
                        prompt=prompt,
                        system_prompt=(
                            "You maintain a concise, factual project state document. "
                            "Only include things that actually exist or have actually been decided. "
                            "Be specific — use real file names, component names, tech choices."
                        ),
                        model="haiku",
                    )
                    if updated.strip():
                        project_dir.mkdir(parents=True, exist_ok=True)
                        (project_dir / "state.md").write_text(updated.strip(), encoding="utf-8")
                        self._turn_state = updated.strip()
                        self._routing_prompt_key = ""
                except Exception:
                    pass  # background task — never block the main flow

        threading.Thread(target=_update, daemon=True).start()

    # ------------------------------------------------------------------
    # Auto-pilot — decide whether to continue without user input
    # ------------------------------------------------------------------

    @staticmethod
    def _build_auto_pilot_context(
        final_response: str, agent_responses: dict
    ) -> str:
        """Build context string for auto-pilot decision.

        When synthesis ran (multi-agent), final_response has Aria's summary.
        When synthesis was skipped (single-agent), final_response is "" —
        fall back to the raw agent response so auto-pilot has context to
        decide whether to continue.
        """
        if final_response.strip():
            return final_response
        if agent_responses:
            return "\n\n".join(
                f"[{r}]: {resp}" for r, resp in agent_responses.items()
            )
        return ""

    @staticmethod
    def _augment_pilot_context_for_export(
        pilot_context: str, original_request: str
    ) -> str:
        """When the last auto-pilot iteration was a doc export, augment the
        context so Haiku understands it was an intermediate step and checks
        for remaining work against the original request.

        Non-export responses pass through unchanged.
        """
        if not pilot_context.startswith("[Generated"):
            return pilot_context
        return (
            f"{pilot_context}\n\n"
            f"The document above was generated as part of fulfilling: {original_request}\n"
            f"This was an intermediate sub-step. Check if there is remaining "
            f"implementation, testing, or concrete work still needed to complete "
            f"the original request."
        )

    @staticmethod
    def _has_actionable_work(agent_responses: dict, phases: list[dict]) -> bool:
        """Return True when the turn produced actionable work worth auto-continuing.

        Triggers on:
        - Multi-phase routing (requirements → implementation → QA = substantial task)
        - Any agent response containing ACTIONS TAKEN (files written, bash executed)
        """
        if len(phases) > 1:
            return True
        combined = "\n".join(agent_responses.values())
        return "ACTIONS TAKEN:" in combined

    @staticmethod
    def _message_similarity(a: str, b: str) -> float:
        """Return 0.0–1.0 similarity ratio between two strings (normalized lowercase)."""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()

    # Phrases (or phrase prefixes) that resume a paused auto-pilot.
    # Matched case-insensitively.  A user input triggers resume if its
    # full text is in this set OR if it *starts with* one of these tokens
    # (so "resume work", "continue working", "go ahead" all resume).
    _CONTINUE_PHRASES = frozenset({
        "continue", "/continue", "go", "go on", "keep going",
        "resume", "proceed", "carry on", "keep working",
    })

    def _run_autopilot_loop(self, user_input: str, pilot_context: str) -> None:
        """Run the auto-pilot continuation loop.

        In normal mode: pauses every AUTO_CHECKPOINT_INTERVAL iterations for
        manual 'continue'.  In /auto mode: Aria auto-resets at each checkpoint
        if no issues (failures, duplicates), up to AUTO_HARD_CEILING total
        iterations as an absolute safety net.

        Tracks WHY the loop stopped:
        - "complete": Haiku decided all work is done → clears _pending_autopilot
        - "cap_reached" / "failure_no_progress" / "duplicate_loop": premature stop
          → saves _pending_autopilot so user can type 'continue' to resume
        - "interrupted": user pressed Ctrl+C → does NOT save pending (respect the interrupt)
        """
        from utils.claude_client import get_session_stats

        self._auto_pilot_active = True
        iteration = 0
        auto_previous_messages: list[str] = []
        pre_auto_tokens = get_session_stats().get("estimated_tokens", 0)
        _pilot_context = pilot_context
        _stop_reason = "complete"

        # In /auto mode the hard ceiling is much higher — Aria auto-resets at
        # each checkpoint interval.  In normal mode we pause at each checkpoint.
        hard_cap = AUTO_HARD_CEILING if self._turn_auto else AUTO_CHECKPOINT_INTERVAL

        while iteration < hard_cap:
            # ── Checkpoint gate ─────────────────────────────────────────
            # Every AUTO_CHECKPOINT_INTERVAL iterations, pause or auto-reset.
            if iteration > 0 and iteration % AUTO_CHECKPOINT_INTERVAL == 0:
                if self._turn_auto:
                    # /auto mode: log checkpoint and keep going
                    console.print(
                        f"\n[bold bright_cyan]🔄 Checkpoint[/bold bright_cyan]  "
                        f"[dim]{_ts()}  {iteration} iterations completed — "
                        f"no issues detected, continuing…[/dim]"
                    )
                else:
                    # Normal mode: pause for manual resume
                    _stop_reason = "cap_reached"
                    break

            try:
                decision = self._auto_pilot_decide(
                    user_input=user_input,
                    final_response=_pilot_context,
                    iteration=iteration,
                    previous_messages=auto_previous_messages,
                )
            except KeyboardInterrupt:
                console.print(
                    "\n[yellow]⚡ Auto-pilot interrupted.[/yellow]  "
                    "[dim]Returning to manual mode for this turn.[/dim]"
                )
                _stop_reason = "interrupted"
                break

            if not decision.get("continue", False):
                if decision.get("premature"):
                    _stop_reason = decision.get("reason", "premature")
                else:
                    if iteration > 0:
                        console.print(
                            "[dim]  ✓ Auto-pilot completed — no further steps needed.[/dim]"
                        )
                break

            next_msg = decision.get("next_message", "").strip()
            if not next_msg:
                break

            auto_previous_messages.append(next_msg)
            iteration += 1

            # Cost warning + token budget guard
            current_tokens = get_session_stats().get("estimated_tokens", 0)
            tokens_burned = current_tokens - pre_auto_tokens
            cost_hint = f"  [dim]~{tokens_burned:,} tokens burned in auto-pilot[/dim]" if tokens_burned > 0 else ""

            # Token budget: stop if auto-pilot has burned too many tokens
            # Default 200k — prevents runaway loops from consuming entire context
            token_budget = self.config.get("auto_pilot_token_budget", 200_000)
            if tokens_burned > token_budget:
                console.print(
                    f"\n[yellow]⚠ Auto-pilot token budget exceeded "
                    f"({tokens_burned:,} > {token_budget:,})[/yellow]"
                )
                _stop_reason = "token_budget"
                break

            console.print(
                f"\n[bold bright_cyan]🤖 Auto-pilot[/bold bright_cyan]  "
                f"[dim]{_ts()}  iteration {iteration}/{hard_cap}[/dim]  "
                f"[white]{next_msg[:100]}{'…' if len(next_msg) > 100 else ''}[/white]"
                f"{cost_hint}"
            )

            # Re-process with the auto-generated message.
            # _auto_pilot_active flag prevents the inner process() call
            # from starting its own nested auto-pilot loop.
            try:
                self.process(next_msg)
            except KeyboardInterrupt:
                console.print(
                    "\n[yellow]⚡ Auto-pilot interrupted.[/yellow]  "
                    "[dim]Returning to manual mode.[/dim]"
                )
                _stop_reason = "interrupted"
                break

            # If the inner process() caught KeyboardInterrupt (sets _interrupted=True
            # and returns normally), stop the loop — no second Ctrl+C needed.
            if self._interrupted:
                console.print(
                    "[yellow]⚡ Auto-pilot stopping — interrupted during processing.[/yellow]"
                )
                _stop_reason = "interrupted"
                break

            # Update pilot context for next iteration's decision
            if self.messages and self.messages[-1]["role"] == "assistant":
                _pilot_context = self.messages[-1]["content"]
                _pilot_context = self._augment_pilot_context_for_export(
                    _pilot_context, user_input
                )
        else:
            # while loop exhausted — iteration reached hard cap
            _stop_reason = "cap_reached"

        self._auto_pilot_active = False

        if _stop_reason == "cap_reached":
            console.print(
                f"\n[yellow]⚠ Auto-pilot reached {iteration} iterations — "
                "pausing for your input.[/yellow]"
            )

        # Save or clear pending context based on stop reason
        if _stop_reason not in ("complete", "interrupted"):
            # Strip stale BASH FAILED / HEALTH_CHECK: FAILED markers before
            # saving — they caused THIS stop and must not cause an immediate
            # stop again when the user resumes (Guard 3 in _auto_pilot_decide
            # would fire on iteration 0 and the loop would be unresumable).
            # Replace with a neutral note so Haiku still knows there was an
            # issue and can decide the right recovery step.
            _clean_ctx = re.sub(
                r"BASH FAILED[^\n]*\n?",
                "Previous command failed — recovery was attempted.\n",
                _pilot_context,
            )
            _clean_ctx = re.sub(
                r"HEALTH_CHECK: FAILED[^\n]*\n?",
                "Previous health check failed — recovery was attempted.\n",
                _clean_ctx,
            )
            self._pending_autopilot = {
                "original_request": user_input,
                "last_context": _clean_ctx,
                "reason": _stop_reason,
            }
            self._log_autopilot_stop(_stop_reason, user_input)
            console.print(
                "[dim]  💡 Work may be incomplete. "
                "Type [bold]continue[/bold] to resume auto-pilot.[/dim]"
            )
        else:
            self._pending_autopilot = None

    # ------------------------------------------------------------------
    # Failure logging — passive Level 1 (append-only, no agent feedback)
    # ------------------------------------------------------------------

    # Regex patterns to extract structured info from outcome strings
    _RE_BASH_FAILED = re.compile(
        r"BASH FAILED \(exit (\d+)\): (.+?)(?:\nOUTPUT:\n(.*))?$", re.DOTALL
    )
    _RE_BASH_TIMEOUT = re.compile(
        r"BASH FAILED \(timed out after \d+s\): (.+)"
    )
    _RE_BASH_BLOCKED = re.compile(r"BASH BLOCKED: (.+)")
    _RE_FILE_BLOCKED = re.compile(r"FILE BLOCKED: (.+)")
    _RE_HEALTH_FAIL = re.compile(r"HEALTH_CHECK: FAILED\n?(.*)", re.DOTALL)

    def _log_failures_from_outcomes(
        self,
        outcomes: list[str],
        agent_name: str,
        user_request: str,
    ):
        """Parse outcome strings and log any failures to the DB."""
        for outcome in outcomes:
            m = self._RE_BASH_FAILED.match(outcome)
            if m:
                self.db.log_failure(
                    self.project_name, agent_name, "bash_error", "bash",
                    m.group(2).strip(), int(m.group(1)),
                    (m.group(3) or "").strip()[:2000], user_request,
                )
                continue

            m = self._RE_BASH_TIMEOUT.match(outcome)
            if m:
                self.db.log_failure(
                    self.project_name, agent_name, "bash_timeout", "bash",
                    m.group(1).strip(), None, "timed out", user_request,
                )
                continue

            m = self._RE_BASH_BLOCKED.match(outcome)
            if m:
                self.db.log_failure(
                    self.project_name, agent_name, "bash_blocked", "bash",
                    m.group(1).strip(), None, "blocked by sandbox", user_request,
                )
                continue

            m = self._RE_FILE_BLOCKED.match(outcome)
            if m:
                self.db.log_failure(
                    self.project_name, agent_name, "file_blocked", "file",
                    m.group(1).strip(), None, "blocked by sandbox", user_request,
                )
                continue

            m = self._RE_HEALTH_FAIL.match(outcome)
            if m:
                self.db.log_failure(
                    self.project_name, agent_name, "health_check_fail", "file",
                    "", None, (m.group(1) or "").strip()[:2000], user_request,
                )
                continue

    def _log_autopilot_stop(self, reason: str, user_request: str):
        """Log an autopilot premature stop as a failure."""
        self.db.log_failure(
            self.project_name, "autopilot", f"autopilot_{reason}", "autopilot",
            "", None, f"Auto-pilot stopped: {reason}", user_request,
        )

    # Failure markers that signal auto-pilot should stop (unless retried successfully)
    _FAILURE_MARKERS = ("BASH FAILED", "HEALTH_CHECK: FAILED")

    def _auto_pilot_decide(
        self,
        user_input: str,
        final_response: str,
        iteration: int = 0,
        previous_messages: list[str] | None = None,
    ) -> dict:
        """
        Ask Haiku whether there is a clear, actionable next step that should
        proceed automatically. Returns {"continue": bool, "next_message": str}.

        Safety guards (checked BEFORE the Haiku call — zero-cost):
        1. Hard cap: iteration >= hard ceiling → stop
        2. User-input-needed: if final_response contains phrases like
           "could you confirm", "please provide", "waiting for your" →
           stop (team is blocked on user input)
        3. Failure exit: if final_response contains BASH FAILED or
           HEALTH_CHECK: FAILED → stop UNLESS RETRY OUTCOMES shows the
           agent already self-healed (all retry entries are OK/PASSED)
        4. Duplicate detection: if Haiku's next_message is >70% similar to
           any previous_messages entry → stop (it's a loop)
        """
        _STOP = {"continue": False, "next_message": ""}

        # Guard 1: hard iteration cap
        _hard_cap = AUTO_HARD_CEILING if self._turn_auto else AUTO_CHECKPOINT_INTERVAL
        if iteration >= _hard_cap:
            return _STOP

        # Guard 2: user-input-needed — stop if the team is asking the user
        # a question or is blocked waiting for information.  These phrases
        # indicate the team cannot proceed without user input.
        _USER_INPUT_PHRASES = (
            "could you confirm",
            "could you provide",
            "can you confirm",
            "can you provide",
            "can you share",
            "please confirm",
            "please provide",
            "please share",
            "let us know",
            "let me know",
            "we need you to",
            "waiting for your",
            "need your input",
            "please approve",
            "approve the write",
            "approve the file",
            "once you approve",
            "what would you like",
            "what do you prefer",
            "which option",
            "which approach",
        )
        _lower_response = final_response.lower()
        if any(phrase in _lower_response for phrase in _USER_INPUT_PHRASES):
            console.print(
                "[yellow]  ⚠ Auto-pilot stopping — "
                "team is asking for your input[/yellow]"
            )
            return {"continue": False, "next_message": "", "premature": True, "reason": "user_input_needed"}

        # Guard 3: failure exit — stop if the last iteration had unresolved
        # failures with NO evidence of progress.  The agent is "making
        # progress" when the response also contains successful outcomes
        # (FILE WRITTEN, BASH OK, HEALTH_CHECK: PASSED) — either in the
        # primary ACTIONS TAKEN or in RETRY OUTCOMES.  In that case the
        # agent is actively fixing things and auto-pilot should let it
        # continue (Haiku decides the next step).
        has_failure = any(m in final_response for m in self._FAILURE_MARKERS)
        if has_failure:
            _SUCCESS_MARKERS = ("BASH OK", "HEALTH_CHECK: PASSED", "FILE WRITTEN")
            has_progress = any(m in final_response for m in _SUCCESS_MARKERS)
            if not has_progress:
                console.print(
                    "[yellow]  ⚠ Auto-pilot stopping — "
                    "failure detected with no progress[/yellow]"
                )
                return {"continue": False, "next_message": "", "premature": True, "reason": "failure_no_progress"}

        state_context = self._turn_state[:600] if self._turn_state else ""

        try:
            set_analytics_context(call_type="auto-pilot", agent_role="orchestrator")
            result = call_claude_json(
                prompt=(
                    f"Original customer request: {user_input}\n\n"
                    f"Latest team output:\n{final_response[:1500]}\n\n"
                    + (f"Project state:\n{state_context}\n\n" if state_context else "")
                    + f"Iteration {iteration + 1} of {_hard_cap}.\n\n"
                    "Is there a clear, concrete next step the team should do RIGHT NOW "
                    "to fulfil the original request? Continue if there is actionable work "
                    "remaining — implementation, testing, documentation, planning, or "
                    "any concrete task the team can execute without user input.\n\n"
                    "IMPORTANT: If the team is asking a procedural or best-practice "
                    "question (e.g. 'should we split this commit?', 'should we add "
                    "tests?', 'which approach is better?'), answer it yourself using "
                    "engineering best practices and continue. Only stop for genuinely "
                    "ambiguous decisions that require domain knowledge the team cannot "
                    "infer — like business priorities, product direction, or user "
                    "preferences. Bias strongly toward continuing.\n\n"
                    "Stop only if ALL requested work is complete or the user MUST "
                    "provide information the team truly cannot decide on its own.\n\n"
                    "Return JSON: {continue: bool, next_message: string}"
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "continue": {"type": "boolean"},
                        "next_message": {
                            "type": "string",
                            "description": "The concrete message to send as the next user input, e.g. 'Now implement the login page with JWT auth'",
                        },
                    },
                    "required": ["continue"],
                },
                system_prompt=(
                    "You decide whether an auto-pilot dev team should continue to the next step "
                    "or pause for user input. Bias STRONGLY toward continuing — the user wants "
                    "maximum autonomy. If the team asks a procedural question with an obvious "
                    "best-practice answer, provide that answer as the next_message and continue. "
                    "Only stop when the original request is fully complete or when the decision "
                    "genuinely requires the user's personal preference or domain knowledge."
                ),
                model="haiku",
            )
        except Exception as exc:
            console.print(
                f"[yellow]  ⚠ Auto-pilot stopping — decision call failed: {exc}[/yellow]"
            )
            return _STOP

        # Guard 3: duplicate detection — catch loops where Haiku keeps
        # generating the same (or very similar) next step
        if result.get("continue") and previous_messages:
            next_msg = result.get("next_message", "").strip()
            if next_msg:
                for prev in previous_messages:
                    if self._message_similarity(next_msg, prev) > 0.70:
                        console.print(
                            "[yellow]  ⚠ Auto-pilot stopping — "
                            "repeated task detected (loop)[/yellow]"
                        )
                        return {"continue": False, "next_message": "", "premature": True, "reason": "duplicate_loop"}

        return result

    # ------------------------------------------------------------------
    # Auto-retry after lesson — agent fixes its own failure immediately
    # ------------------------------------------------------------------

    def _retry_after_lesson(
        self,
        role: str,
        failures: list[str],
        write_dir: Path,
        tdd_health_cmd: str | None,
        tdd_cwd: Path | None,
        normalize_dirs: list[Path] | None = None,
    ) -> list[str]:
        """
        Immediately re-invoke the agent after it learned from a failure.
        The lesson is already in context (injected by _apply_lesson) — this
        just tells the agent "apply what you just learned and fix it now."

        Called at most once per role per phase to prevent infinite loops.
        Returns the new outcome strings from the retry attempt.
        """
        agent = self.agents.get(role)
        if not agent:
            return []

        p = self.config["agent_personas"].get(role, {})
        name = p.get("name", role.upper())
        color = p.get("color", "white")
        emoji = p.get("emoji", "")

        failure_summary = "\n\n".join(failures[:2])  # cap at 2 failures

        console.print(
            f"\n[{color}]{emoji} {name} retrying after lesson…[/{color}]  "
            "[dim](applying what was just learned)[/dim]"
        )

        retry_task = (
            "Your previous attempt just failed and you immediately learned a lesson from it. "
            "That lesson is now in your context. Apply it and fix the problem now.\n\n"
            f"What failed:\n{failure_summary[:1200]}\n\n"
            "Produce the corrected file(s) or command using EXEC: blocks. "
            "Do not explain — just fix it."
        )

        try:
            with console.status(
                f"[{color}]{emoji} {name} fixing…[/{color}]", spinner="dots"
            ):
                response = agent.respond(
                    task=retry_task,
                    context="Auto-retry after lesson — apply the lesson and correct the failure.",
                    history_text=self._format_history(limit=4),
                )
        except KeyboardInterrupt:
            console.print("\n[yellow]⚡ Retry interrupted.[/yellow]")
            return []
        except Exception as e:
            console.print(f"[dim yellow]  Retry error: {e}[/dim yellow]")
            return []

        self.display.show_agent_response(
            name, self._strip_exec_for_display(response), color, emoji
        )

        retry_outcomes: list[str] = []
        retry_actions = parse_actions(response, name)
        if retry_actions:
            retry_outcomes = prompt_and_execute(
                retry_actions,
                write_dir,
                tdd_health_cmd=tdd_health_cmd,
                tdd_cwd=tdd_cwd,
                normalize_dirs=normalize_dirs,
                auto_mode=self._turn_auto,
            )
            if retry_outcomes:
                self._log_failures_from_outcomes(retry_outcomes, name, self.last_user_input)
        elif not retry_actions:
            # Agent gave a text-only response — still useful, treat as an outcome note
            retry_outcomes = [f"RETRY NOTE from {name}: {response[:400]}"]

        return retry_outcomes

    # ------------------------------------------------------------------
    # Clarification gate — ask one question before routing big vague tasks
    # ------------------------------------------------------------------

    def _check_needs_clarification(self, user_input: str) -> str | None:
        """
        Check whether a large/vague new-build request needs one clarifying question
        before the team starts work. Returns the question string, or None if clear.

        Pre-filter conditions (all must pass to trigger the Haiku call):
        - Message matches a large-build pattern (app, system, platform, etc.)
        - Message is > 8 words
        - Project has < 3 memory entries (little existing context)
        - No requirements document exists yet
        - This is the first or second user message (early in the conversation)
        """
        if len(user_input.split()) <= 8:
            return None
        if not _LARGE_BUILD_RE.search(user_input):
            return None

        # Skip if project already has good context
        if len(self.memory.list_memory_entries()) >= 3:
            return None

        # Skip if a requirements doc already exists
        docs_dir = self.base_dir / "projects" / self.project_name / "docs"
        if docs_dir.exists() and any(docs_dir.glob("*requirement*.md")):
            return None

        # Only fire early in the conversation
        user_messages = [m for m in self.messages if m["role"] == "user"]
        if len(user_messages) > 2:
            return None

        try:
            result = call_claude_json(
                prompt=(
                    f"A customer wants to build something:\n{user_input}\n\n"
                    "Decide if ONE focused clarifying question would meaningfully improve "
                    "the team's output. Ask only when something critical is genuinely ambiguous "
                    "(tech stack, scale, primary user type, or core feature scope). "
                    "Do NOT ask if the request is already clear enough to start."
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "needs_clarification": {"type": "boolean"},
                        "question": {"type": "string"},
                    },
                    "required": ["needs_clarification"],
                },
                system_prompt=(
                    "You decide if a build request needs one clarifying question before a dev team "
                    "starts work. Be conservative — only recommend asking when it would genuinely "
                    "change what the team builds."
                ),
                model="haiku",
            )
            if result.get("needs_clarification") and result.get("question", "").strip():
                return result["question"].strip()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Intent verification — surface mismatches between request and output
    # ------------------------------------------------------------------

    def _verify_intent_coverage(
        self, user_input: str, agent_responses: dict
    ) -> str | None:
        """
        Heuristic check: did the agents produce what was actually requested?
        Returns a warning string or None. No LLM call — pure pattern matching.

        Currently detects: user asked for code/files but team only gave prose.
        """
        if not _CODE_REQUEST_RE.search(user_input):
            return None

        combined = "\n".join(agent_responses.values())
        has_exec = "EXEC:file:" in combined or "EXEC:bash" in combined
        has_code_fence = "```" in combined

        if not has_exec and not has_code_fence:
            return (
                "⚠  The team gave advice but didn't write any code. "
                "Try: '@sam write the code directly' — or the team may need "
                "more requirements before implementing."
            )
        return None

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
        routing_model = self.config.get("routing_model", "haiku")
        system_prompt = self._routing_system_prompt()

        try:
            set_analytics_context(call_type="routing", agent_role="orchestrator")
            result = call_claude_json(
                prompt=prompt,
                schema=ROUTING_SCHEMA,
                system_prompt=system_prompt,
                model=routing_model,
            )
        except Exception as e:
            console.print(f"[dim yellow]Routing fallback (JSON parse error): {e}[/dim yellow]")
            return {
                "phases": [
                    {
                        "name": "General",
                        "agents": list(self.active_roster),
                        "tasks": {r: user_input for r in self.active_roster},
                    }
                ]
            }

        # ── Confidence escalation ────────────────────────────────────────
        # If Haiku produced a thin plan for a complex message, re-run with Sonnet.
        # Thin = single agent with a very short/vague task on a long user message.
        # This fires rarely (only when the routing looks suspicious) so the extra
        # call happens maybe once in 20 messages on a typical session.
        if routing_model == "haiku" and len(user_input.split()) > 12:
            phases = result.get("phases", [])
            total_agents = sum(len(p.get("agents", [])) for p in phases)
            total_task_chars = sum(
                len(t) for p in phases for t in p.get("tasks", {}).values()
            )
            is_thin = phases and total_agents <= 1 and total_task_chars < 60
            if is_thin:
                try:
                    result = call_claude_json(
                        prompt=prompt,
                        schema=ROUTING_SCHEMA,
                        system_prompt=system_prompt,
                        model="sonnet",
                    )
                    console.print(
                        "[dim]↑ Routing escalated to Sonnet (complex task detected)[/dim]"
                    )
                except Exception:
                    pass  # fall back to the haiku result

        return result

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
        # Track last input so /redo can re-submit or edit after Ctrl+C
        self.last_user_input = user_input
        self._interrupted = False

        # ── Once-per-session skill consolidation ─────────────────────────
        # Merges redundant auto-learned lessons when files get large.
        # Runs on the very first process() call only (guarded internally).
        if not self._skills_consolidated:
            try:
                self._consolidate_skills_if_needed()
            except Exception:
                self._skills_consolidated = True  # don't retry on failure

        # ── Populate per-turn caches (one disk read each, shared across all
        #    routing / agent / synthesis calls in this turn) ────────────────
        cfg = self.config
        self._turn_tdd = self.memory.load_tdd_mode()
        self._turn_auto = self.memory.load_auto_mode()
        self._turn_memory = self.memory.load_project_memory(
            limit=cfg.get("max_routing_memory", 8)
        )
        self._turn_docs = self.memory.load_project_docs(
            max_docs=cfg.get("max_project_docs", 1),
            max_chars_each=cfg.get("max_doc_chars", 900),
        )
        # Project state — load once, used by routing + synthesis
        self._turn_state = self._load_project_state()

        # ── Auto-scan project directory when no /loaded codebase exists ──
        # Without this, agents created within family-agents (not /loaded)
        # have ZERO visibility into project files — no folder tree, no
        # READ_FILE, nothing.  Rescans only when the file set changes
        # (content-hash cache avoids redundant scans during auto-pilot).
        if not self.loaded_path or self.loaded_path == self.base_dir / "projects" / self.project_name:
            project_dir = self.base_dir / "projects" / self.project_name
            if project_dir.exists():
                try:
                    scan_key = frozenset(
                        (str(f.relative_to(project_dir)), f.stat().st_mtime_ns)
                        for f in project_dir.rglob("*")
                        if f.is_file()
                        and not any(part in _SCAN_IGNORE for part in f.relative_to(project_dir).parts)
                    )
                except (OSError, ValueError):
                    scan_key = None
                if scan_key and scan_key != self._project_scan_key:
                    self.loaded_path = project_dir
                    self.codebase_context = self._scan_codebase(project_dir)
                    self._project_scan_key = scan_key

        # ── Resume paused auto-pilot ─────────────────────────────────────
        # If auto-pilot was paused (cap, failure, duplicate) and the user
        # types "continue" / "resume" / etc., pick up where we left off
        # instead of routing through Aria.
        # Matching: exact match OR starts-with, so "resume work",
        # "continue working", "go ahead" all trigger resume correctly.
        _user_lower = user_input.strip().lower()
        _is_continue = (
            _user_lower in self._CONTINUE_PHRASES
            or any(_user_lower.startswith(phrase) for phrase in self._CONTINUE_PHRASES)
        )
        if (_is_continue
                and self._pending_autopilot
                and not getattr(self, "_auto_pilot_active", False)):
            pending = self._pending_autopilot
            self._pending_autopilot = None  # cleared; loop will re-set if needed
            console.print(
                f"\n[bold bright_cyan]🤖 Auto-pilot resuming[/bold bright_cyan]  "
                f"[dim]{_ts()}  original: {pending['original_request'][:80]}"
                f"{'…' if len(pending['original_request']) > 80 else ''}[/dim]"
            )
            self._run_autopilot_loop(pending["original_request"], pending["last_context"])
            return

        # Short-circuit: direct file reads served instantly from disk (zero LLM calls).
        # Skip during auto-pilot — those messages are agent instructions, not user
        # file-read requests. Words like "GET" and filenames in the task description
        # would false-positive match the file-read intent regex.
        if not getattr(self, "_auto_pilot_active", False) and self._try_serve_file_directly(user_input):
            return

        self.db.save_message(self.project_name, "user", user_input)
        self.messages.append({"role": "user", "content": user_input})

        # Detect user corrections and auto-save as agent skills (silent)
        self._detect_and_save_correction(user_input)

        # Detect export/report generation intent (before teaching detection — more specific)
        export_match = self._detect_export_intent(user_input)
        if export_match:
            agent_role, doc_type = export_match
            self.export_doc(doc_type, agent_role)
            # Rich message so auto-pilot has enough context to decide next step
            hint = _EXPORT_NEXT_HINTS.get(
                doc_type.lower(), "continue planning or start the next phase"
            )
            export_msg = (
                f"[Generated {doc_type}] — Document saved. "
                f"Next the team should {hint}."
            )
            self.db.save_message(self.project_name, "assistant", export_msg)
            self.messages.append({"role": "assistant", "content": export_msg})
            # Keep state.md current so auto-pilot's next iteration has fresh context
            if self.project_name != "_general":
                self._update_project_state(
                    user_input,
                    {agent_role or "pm": f"Generated {doc_type} document."},
                    export_msg,
                )
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

        # ── Clarification gate ───────────────────────────────────────────
        # For large/vague new-build requests with little project context,
        # Aria asks ONE focused question before routing. This prevents wasting
        # a whole phase on the wrong interpretation of an ambiguous requirement.
        # The gate is conservative — it only fires for the first 1-2 messages
        # of a new project that looks underspecified.
        if self.project_name != "_general":
            clarifying_q = self._check_needs_clarification(user_input)
            if clarifying_q:
                console.print()
                console.rule(
                    "[bold bright_cyan]🎯 Aria (Coordinator)[/bold bright_cyan]",
                    style="bright_cyan",
                )
                console.print(
                    f"Before the team dives in — {clarifying_q}\n"
                    "[dim](Answer this, then I'll route to the team.)[/dim]"
                )
                console.print()
                # Save the user's original message — they'll continue from here
                self.db.save_message(self.project_name, "assistant", f"[Aria asked]: {clarifying_q}")
                self.messages.append({"role": "assistant", "content": f"[Aria asked]: {clarifying_q}"})
                return

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
            # Allow bench agents pulled in by Aria — not just active_roster
            agents_in_phase = phase.get("agents", [])
            agents_to_call = [r for r in agents_in_phase if r in self.agents]
            if not agents_to_call:
                continue
            # Announce any bench agents being temporarily pulled in
            bench_pulled = [r for r in agents_to_call if r not in self.active_roster]
            for br in bench_pulled:
                bp = personas.get(br, {})
                console.print(
                    f"[dim cyan]  ↓ {bp.get('emoji','')} {bp.get('name', br)} pulled in from bench "
                    f"for {phase_name}[/dim cyan]"
                )

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
                self._interrupted = True
                # Roll back the user message we already appended so /redo can cleanly re-submit
                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                console.print(
                    "\n[yellow]⚡ Interrupted.[/yellow]  "
                    "Type [bold cyan]/redo[/bold cyan] to edit & re-send your last message, "
                    "or just type a new one."
                )
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
                    _norm_dirs = self._extra_normalize_dirs(project_dir)
                    outcomes = prompt_and_execute(
                        actions,
                        write_dir,
                        tdd_health_cmd=_tdd_health_cmd if _tdd_enabled else None,
                        tdd_cwd=_tdd_cwd,
                        normalize_dirs=_norm_dirs,
                        auto_mode=self._turn_auto,
                    )
                    if outcomes:
                        phase_responses[role] += "\n\nACTIONS TAKEN:\n" + "\n".join(outcomes)
                        # Log failures for later analysis
                        self._log_failures_from_outcomes(outcomes, name, user_input)
                        # Auto-extract lessons from failures
                        self._check_outcomes_for_lessons(role, outcomes)

                        # ── Auto-retry after lesson ──────────────────────
                        # If any action failed AND a lesson was just learned,
                        # the agent already has the lesson in context — re-invoke
                        # it immediately so it applies the fix in the same turn.
                        # Capped at 1 retry per role per phase (no infinite loops).
                        fixable_failures = [
                            o for o in outcomes
                            if o.startswith("BASH FAILED")
                            or o.startswith("HEALTH_CHECK: FAILED")
                            or o.startswith("FILE REJECTED")
                        ]
                        if fixable_failures:
                            retry_outcomes = self._retry_after_lesson(
                                role=role,
                                failures=fixable_failures,
                                write_dir=write_dir,
                                tdd_health_cmd=_tdd_health_cmd if _tdd_enabled else None,
                                tdd_cwd=_tdd_cwd,
                                normalize_dirs=_norm_dirs,
                            )
                            if retry_outcomes:
                                phase_responses[role] += "\n\nRETRY OUTCOMES:\n" + "\n".join(retry_outcomes)
                        # ─────────────────────────────────────────────────

                # Auto-extract REMEMBER: markers
                saved_count = self.memory.extract_and_save_memories(response, role)
                if saved_count:
                    console.print(
                        f"[dim green]  (💾 {saved_count} memory item(s) from {name})[/dim green]"
                    )

            all_agent_responses.update(phase_responses)

            # Build context summary for the next phase from this phase's output.
            # Split the response from the ACTIONS TAKEN block so we can prioritise
            # keeping the action outcomes (test results, bash output) visible — they
            # are appended at the END and would be silently truncated at 1200 chars
            # if the agent wrote a long response first, causing the next phase agent
            # (e.g. Aria synthesizing TDD results) to miss "25 passed" entirely.
            phase_summary_parts = []
            for role, resp in phase_responses.items():
                agent_name = personas.get(role, {}).get("name", role.upper())
                if "\n\nACTIONS TAKEN:\n" in resp:
                    narrative, actions_block = resp.split("\n\nACTIONS TAKEN:\n", 1)
                    # Keep up to 800 chars of narrative + full actions block (cap 1500)
                    narrative_snippet = narrative[:800]
                    actions_snippet = actions_block[:1500]
                    summary = f"{narrative_snippet}\n\nACTIONS TAKEN:\n{actions_snippet}"
                else:
                    summary = resp[:1200]
                phase_summary_parts.append(f"[{agent_name}]:\n{summary}")
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
        all_file_errors = bool(agent_responses) and all(
            _FILE_ERROR_RE.match(resp.strip())
            for resp in agent_responses.values()
        )

        final_response = ""
        if self._should_synthesize(agent_responses, all_file_errors):
            with console.status("[bright_cyan]🎯 Aria is synthesizing…[/bright_cyan]", spinner="dots"):
                synth_prompt = self._synthesis_prompt(user_input, agent_responses)
                try:
                    set_analytics_context(call_type="synthesis", agent_role="orchestrator")
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
                            "Be concise. If there is a natural next step, "
                            "briefly state what the team can do next."
                        ),
                        system_prompt=self._synthesis_system_prompt(),
                        model=self.model,
                    )
                except Exception as e:
                    final_response = f"(error: {e})"

        if final_response.strip():
            self.display.show_orchestrator_response(final_response)

        # ── Intent verification — surface mismatch between request and output ──
        if agent_responses:
            mismatch_warn = self._verify_intent_coverage(user_input, agent_responses)
            if mismatch_warn:
                console.print(f"\n[yellow]{mismatch_warn}[/yellow]")

        # Persist to DB and in-memory log
        combined = final_response or "\n\n".join(
            f"[{r}]: {resp}" for r, resp in agent_responses.items()
        )
        if combined:
            self.db.save_message(self.project_name, "assistant", combined)
            self.messages.append({"role": "assistant", "content": combined})
        else:
            console.print("[dim yellow]No response generated. Try rephrasing your message.[/dim yellow]")

        # ── Update project state in background ──────────────────────────
        # Builds/refreshes state.md after every exchange so Aria has a
        # structured snapshot on the next turn. Runs in a daemon thread —
        # never adds latency to the current turn.
        if agent_responses and self.project_name != "_general":
            self._update_project_state(user_input, agent_responses, final_response)

        console.print()

        # ── Auto-pilot continuation loop ─────────────────────────────────
        # Aria always decides whether to continue to the next logical step
        # when the turn produced actionable work (multi-phase routing or
        # EXEC blocks executed). Not gated by /auto — that only controls
        # auto-approve for file writes and safe bash.
        # Capped at AUTO_HARD_CEILING (/auto) or AUTO_CHECKPOINT_INTERVAL (normal). Ctrl+C breaks out.
        _actionable = self._has_actionable_work(agent_responses, phases)
        if _actionable and agent_responses and self.project_name != "_general" \
                and not getattr(self, "_auto_pilot_active", False):
            _pilot_context = self._build_auto_pilot_context(
                final_response, agent_responses
            )
            self._run_autopilot_loop(user_input, _pilot_context)

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
        # Reload auto-approve from disk (process() does this in its cache block,
        # but direct_message bypasses process entirely)
        self._turn_auto = self.memory.load_auto_mode()

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
            _norm_dirs = self._extra_normalize_dirs(project_dir)
            outcomes = prompt_and_execute(actions, write_dir, normalize_dirs=_norm_dirs, auto_mode=self._turn_auto)
            if outcomes:
                response += "\n\nACTIONS TAKEN:\n" + "\n".join(outcomes)
                self._log_failures_from_outcomes(outcomes, name, self.last_user_input)
                self._check_outcomes_for_lessons(role, outcomes)
                # Auto-retry on failure (same as phase loop)
                fixable_failures = [
                    o for o in outcomes
                    if o.startswith("BASH FAILED")
                    or o.startswith("HEALTH_CHECK: FAILED")
                    or o.startswith("FILE REJECTED")
                ]
                if fixable_failures:
                    retry_outcomes = self._retry_after_lesson(
                        role=role,
                        failures=fixable_failures,
                        write_dir=write_dir,
                        tdd_health_cmd=None,
                        tdd_cwd=None,
                        normalize_dirs=_norm_dirs,
                    )
                    if retry_outcomes:
                        response += "\n\nRETRY OUTCOMES:\n" + "\n".join(retry_outcomes)

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
        auto_enabled = self.memory.load_auto_mode()
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
            auto_enabled=auto_enabled,
            safe_context=self.config.get("safe_context_tokens", 200_000),
            project_state=self._load_project_state(),
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
        # When a codebase is /loaded, docs and file list come from that path
        root_dir = self.loaded_path if self.loaded_path else project_dir
        file_list = []
        if root_dir.exists():
            IGNORE = {
                ".git", "node_modules", "__pycache__", ".venv", "venv",
                "dist", "build", ".next", "target", ".gradle", ".idea", ".vscode",
            }
            file_list = [
                str(f.relative_to(root_dir))
                for f in sorted(root_dir.rglob("*"))
                if f.is_file() and f.name != ".gitkeep"
                and not any(part in IGNORE for part in f.relative_to(root_dir).parts)
            ]

        # ── Check for an existing doc of the same type ──────────────
        docs_dir = root_dir / "docs"
        existing_doc_path: Path | None = None
        existing_doc_content: str = ""
        if docs_dir.exists():
            candidates = sorted(
                docs_dir.glob(f"{doc_type}*.md"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                existing_doc_path = candidates[0]
                try:
                    existing_doc_content = existing_doc_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                except Exception:
                    existing_doc_content = ""

        # ── Build the export prompt ─────────────────────────────────
        existing_section = ""
        if existing_doc_path and existing_doc_content:
            existing_section = (
                f"## Existing Document: {existing_doc_path.name}\n"
                f"A previous version of this document already exists. "
                f"Update and enhance it — do not start from scratch. "
                f"Preserve any content that is still accurate, add new information from "
                f"recent conversations and memory, and remove anything outdated.\n\n"
                f"{existing_doc_content}\n\n"
            )

        export_prompt = (
            f"Project: {self.project_name}\n"
            f"Document to produce: {doc_type}\n\n"
            f"## Project Memory\n{memory_text}\n\n"
            f"## Recent Conversation\n{history_text or 'No history.'}\n\n"
            + (existing_section if existing_section else "")
            + f"## Files Created So Far\n" + ("\n".join(file_list) if file_list else "None yet.") + "\n\n"
            f"Write the COMPLETE, full-length {doc_type} in Markdown format. "
            f"This is a document generation task — ignore any brevity rules. "
            f"Output the entire document with no truncation, no matter how long. "
            f"Base it on what has been discussed, decided, and documented. "
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

        # Save to docs/ — overwrite existing doc of the same type if found
        docs_dir.mkdir(parents=True, exist_ok=True)
        if existing_doc_path:
            out_path = existing_doc_path  # overwrite in place
            filename = existing_doc_path.name
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f"{doc_type}-{date_str}.md"
            out_path = docs_dir / filename
        out_path.write_text(content, encoding="utf-8")

        # Show a clean confirmation — no truncated preview spam.
        # The full doc is on disk; the user can 'show <filename>' to read it.
        hint = _EXPORT_NEXT_HINTS.get(doc_type.lower(), "continue planning or start the next phase")
        display_path = str(out_path) if self.loaded_path else f"projects/{self.project_name}/docs/{filename}"
        verb = "updated" if existing_doc_path else "created"
        console.print(
            f"\n[bold green]✓ Document {verb}:[/bold green] "
            f"[cyan]{display_path}[/cyan]  "
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
                f"Document:\n{content[:10000]}"
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

    def show_failures(self, category: str | None = None, limit: int = 20):
        """Display recent failures from the failure log."""
        rows = self.db.get_failures(self.project_name, limit=limit, category=category)
        if not rows:
            msg = "[dim]No failures logged"
            if category:
                msg += f" for category '{category}'"
            msg += ".[/dim]"
            console.print(f"\n{msg}\n")
            return

        from rich.table import Table
        table = Table(
            title="Recent Failures",
            show_lines=False,
            padding=(0, 1),
        )
        table.add_column("Time", style="dim", no_wrap=True)
        table.add_column("Agent", style="bold yellow", no_wrap=True)
        table.add_column("Category", style="cyan", no_wrap=True)
        table.add_column("Command / File", max_width=40)
        table.add_column("Error", style="red", max_width=50)

        for row in rows:
            ts = row["timestamp"]
            # Shorten timestamp to just date + time
            if ts and len(ts) > 16:
                ts = ts[:16]
            error = (row["error_snippet"] or "")[:80]
            cmd = (row["command_or_file"] or "")[:40]
            table.add_row(ts, row["agent_name"], row["category"], cmd, error)

        console.print()
        console.print(table)
        console.print(
            f"\n[dim]{len(rows)} failure{'s' if len(rows) != 1 else ''} shown · "
            f"filter with [cyan]/failures <category>[/cyan]  "
            f"(bash_error · bash_timeout · bash_blocked · health_check_fail · "
            f"file_blocked · autopilot_cap_reached)[/dim]\n"
        )

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

    def clear_history(self, last_n: int | None = None):
        """Clear conversation history from the DB.

        - ``last_n is None`` → wipe ALL messages for this project
        - ``last_n > 0``     → delete only the last N messages
        """
        if last_n is not None:
            if last_n <= 0:
                console.print("[yellow]Usage: /clear-history <N> where N > 0[/yellow]")
                return
            deleted = self.db.delete_last_n_messages(self.project_name, last_n)
            # Also trim the in-memory list
            if deleted > 0:
                self.messages = self.messages[:-deleted] if deleted < len(self.messages) else []
            console.print(
                f"[dim]Deleted last {deleted} message(s) from DB. "
                f"Memory, docs, and skills untouched.[/dim]"
            )
        else:
            self.db.delete_project_messages(self.project_name)
            self.messages = []
            console.print(
                "[dim]All conversation history deleted from DB. "
                "Memory, docs, and skills untouched.[/dim]"
            )
