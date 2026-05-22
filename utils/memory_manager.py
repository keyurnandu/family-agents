import re
from datetime import datetime
from pathlib import Path

_SENTINEL = object()  # marks "not yet loaded from disk" for cached fields


class MemoryManager:
    def __init__(self, base_dir: Path, project_name: str):
        self.base_dir = base_dir
        self.project_name = project_name
        self.roles_dir = base_dir / "memory" / "roles"
        self.dynamic_dir = base_dir / "memory" / "dynamic" / project_name
        self.dynamic_dir.mkdir(parents=True, exist_ok=True)
        self._entries_cache: list | None = None  # invalidated on every save
        self._loaded_path_cache: str | None = _SENTINEL  # sentinel = not yet read

    def load_role_memory(self, role: str) -> str:
        role_file = self.roles_dir / f"{role}.md"
        if role_file.exists():
            return role_file.read_text(encoding="utf-8")
        return f"# {role.upper()}\nNo predefined role memory found."

    def load_project_memory(self, limit: int = 40, categories: set | None = None) -> str:
        """
        Return project memory for injection into agent prompts.
        Only the most recent `limit` entries are returned to control token usage.
        The full history is always preserved on disk.

        categories: optional set of lowercase category names to include
                    (e.g. {"decision", "technical", "epic-plan"}).
                    When None, all categories are included. Pass a role-specific
                    set so each agent only sees memory relevant to their domain.
        """
        memory_file = self.dynamic_dir / "memory.md"
        if not memory_file.exists():
            return ""
        content = memory_file.read_text(encoding="utf-8")
        if not content.strip():
            return ""

        entries = self.list_memory_entries()
        if not entries:
            return ""

        # Apply category filter when specified
        if categories:
            entries = [e for e in entries if e["category"].lower() in categories]
            if not entries:
                return ""

        if len(entries) <= limit and not categories:
            return content  # fast path: no filter, no truncation

        recent = entries[-limit:] if len(entries) > limit else entries
        omitted = len(entries) - len(recent)

        header = f"# Project Memory: {self.project_name}\n"
        if omitted:
            header += f"[{omitted} older entries omitted — full history in memory.md]\n"
        body = ""
        for e in recent:
            body += (
                f"\n### [{e['category'].upper()}] — {e['timestamp']} (via {e['source']})\n"
                f"{e['content'].strip()}\n"
            )
        return header + body

    def save_project_memory(self, content: str, category: str, source: str = "system"):
        memory_file = self.dynamic_dir / "memory.md"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        if memory_file.exists():
            existing = memory_file.read_text(encoding="utf-8")
        else:
            existing = f"# Project Memory: {self.project_name}\n\n"

        # Deduplicate: skip if same content already saved
        normalized = content.strip().lower()
        if normalized[:60] in existing.lower():
            return False

        entry = f"\n### [{category.upper()}] — {timestamp} (via {source})\n{content.strip()}\n"
        memory_file.write_text(existing + entry, encoding="utf-8")
        self._entries_cache = None  # invalidate cache
        return True

    def extract_and_save_memories(self, text: str, source_agent: str) -> int:
        """Extract explicit REMEMBER: markers from agent text and persist them."""
        pattern = r"(?:REMEMBER|NOTE):\s*(.+?)(?=\n|$)"
        matches = re.findall(pattern, text, re.IGNORECASE)
        saved = 0
        for match in matches:
            if self.save_project_memory(
                content=match.strip(),
                category="note",
                source=source_agent,
            ):
                saved += 1
        return saved

    def list_memory_entries(self) -> list[dict]:
        """Return parsed memory entries as a list of dicts. Result is cached until next save."""
        if self._entries_cache is not None:
            return self._entries_cache

        # Read the raw file directly — do NOT call load_project_memory() here
        # as that method calls list_memory_entries() and would cause infinite recursion.
        memory_file = self.dynamic_dir / "memory.md"
        if not memory_file.exists():
            self._entries_cache = []
            return self._entries_cache
        content = memory_file.read_text(encoding="utf-8")
        if not content:
            self._entries_cache = []
            return self._entries_cache

        entries = []
        current = None
        for line in content.splitlines():
            header_match = re.match(r"### \[(\w+)\] — (.+?) \(via (.+?)\)", line)
            if header_match:
                if current:
                    entries.append(current)
                current = {
                    "category": header_match.group(1),
                    "timestamp": header_match.group(2),
                    "source": header_match.group(3),
                    "content": "",
                }
            elif current and line.strip():
                current["content"] += line + "\n"
        if current:
            entries.append(current)
        self._entries_cache = entries
        return entries

    def delete_project_memory(self):
        memory_file = self.dynamic_dir / "memory.md"
        if memory_file.exists():
            memory_file.unlink()
        self._entries_cache = None

    def load_project_docs(self, max_docs: int = 3, max_chars_each: int = 3000) -> str:
        """
        Load the most recently exported docs from projects/<name>/docs/.
        Returns a combined string injected into agent system prompts so agents
        start a new session already aware of requirements, epics, sprint plans, etc.
        Capped to avoid excessive token usage — full docs always on disk.
        """
        docs_dir = self.base_dir / "projects" / self.project_name / "docs"
        if not docs_dir.exists():
            return ""

        doc_files = sorted(
            docs_dir.glob("*.md"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not doc_files:
            return ""

        parts = []
        for doc_file in doc_files[:max_docs]:
            try:
                content = doc_file.read_text(encoding="utf-8", errors="replace")
                if len(content) > max_chars_each:
                    content = (
                        content[:max_chars_each]
                        + f"\n\n[Truncated — {len(content):,} chars total. Full doc at docs/{doc_file.name}]"
                    )
                parts.append(f"### {doc_file.name}\n{content.strip()}")
            except Exception:
                pass

        if not parts:
            return ""

        total = len(doc_files)
        shown = min(total, max_docs)
        header = (
            f"The team has produced {total} document(s) for this project "
            f"(showing {shown} most recent). Treat these as the source of truth — "
            "do NOT re-analyse or re-discover what is already defined here.\n\n"
        )
        return header + "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # Loaded codebase path — persists across sessions
    # ------------------------------------------------------------------

    def save_loaded_path(self, path_str: str):
        """Persist the currently loaded codebase path so it survives a restart."""
        path_file = self.dynamic_dir / "loaded_path.txt"
        path_file.write_text(path_str.strip(), encoding="utf-8")
        self._loaded_path_cache = path_str.strip()

    def load_loaded_path(self) -> str | None:
        """Return the last loaded codebase path, or None if not set / missing."""
        if self._loaded_path_cache is not _SENTINEL:
            return self._loaded_path_cache if self._loaded_path_cache else None
        path_file = self.dynamic_dir / "loaded_path.txt"
        if path_file.exists():
            p = path_file.read_text(encoding="utf-8").strip()
            self._loaded_path_cache = p
            return p if p else None
        self._loaded_path_cache = ""
        return None

    def clear_loaded_path(self):
        """Remove the saved loaded path (called on /unload)."""
        path_file = self.dynamic_dir / "loaded_path.txt"
        if path_file.exists():
            path_file.unlink()
        self._loaded_path_cache = ""

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    @property
    def _skills_dir(self) -> Path:
        return self.base_dir / "memory" / "skills"

    def load_skills(self, role: str) -> str:
        """Load all skill files for a role, return combined markdown."""
        role_dir = self._skills_dir / role
        if not role_dir.exists():
            return ""
        files = sorted(role_dir.glob("*.md"))
        parts = [f.read_text(encoding="utf-8").strip() for f in files]
        return "\n\n---\n\n".join(p for p in parts if p)

    def save_skill(self, role: str, skill_name: str, content: str) -> Path:
        role_dir = self._skills_dir / role
        role_dir.mkdir(parents=True, exist_ok=True)
        filename = re.sub(r"[^\w\-]", "-", skill_name.lower()).strip("-") + ".md"
        path = role_dir / filename
        path.write_text(content.strip(), encoding="utf-8")
        return path

    def list_skills(self, role: str | None = None) -> dict[str, list[dict]]:
        """Returns {role: [{name, preview}]}."""
        base = self._skills_dir
        if not base.exists():
            return {}
        if role:
            roles_to_check = [role]
        else:
            roles_to_check = [d.name for d in sorted(base.iterdir()) if d.is_dir()]
        result = {}
        for r in roles_to_check:
            d = base / r
            if not d.exists():
                continue
            skills = []
            for f in sorted(d.glob("*.md")):
                content = f.read_text(encoding="utf-8").strip()
                skills.append({"name": f.stem, "preview": content[:120]})
            if skills:
                result[r] = skills
        return result

    def delete_skill(self, role: str, skill_name: str) -> bool:
        filename = re.sub(r"[^\w\-]", "-", skill_name.lower()).strip("-") + ".md"
        path = self._skills_dir / role / filename
        if path.exists():
            path.unlink()
            return True
        return False

    def skill_count(self, role: str) -> int:
        role_dir = self._skills_dir / role
        if not role_dir.exists():
            return 0
        return len(list(role_dir.glob("*.md")))

    # ------------------------------------------------------------------
    # TDD mode — persists across sessions per project
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Auto-learning — lessons extracted from failures / corrections
    # ------------------------------------------------------------------

    def save_auto_skill(self, role: str, lesson: str, trigger: str = "auto") -> Path:
        """
        Append a lesson to the role's auto-learned skill file.
        Lessons accumulate with a date + trigger header so the agent
        can see when and why each lesson was captured.
        """
        from datetime import datetime
        role_dir = self._skills_dir / role
        role_dir.mkdir(parents=True, exist_ok=True)
        path = role_dir / "auto-learned.md"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        header = f"\n### [{timestamp}] via {trigger}\n"

        if path.exists():
            existing = path.read_text(encoding="utf-8")
        else:
            existing = f"# Auto-Learned Lessons — {role}\n\nLessons captured automatically from failures, corrections, and retrospectives.\n"

        path.write_text(existing + header + lesson.strip() + "\n", encoding="utf-8")
        self._entries_cache = None
        return path

    def load_auto_skills(self, role: str) -> str:
        """Load the auto-learned lesson file for a role."""
        path = self._skills_dir / role / "auto-learned.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def save_tdd_mode(self, enabled: bool, health_cmd: str = "") -> None:
        """Persist TDD mode flag and optional health-check command."""
        tdd_file = self.dynamic_dir / "tdd.txt"
        tdd_file.write_text(f"{int(enabled)}\n{health_cmd.strip()}", encoding="utf-8")

    def load_tdd_mode(self) -> tuple[bool, str]:
        """Return (enabled, health_check_cmd). Defaults to (False, '')."""
        tdd_file = self.dynamic_dir / "tdd.txt"
        if not tdd_file.exists():
            return False, ""
        lines = tdd_file.read_text(encoding="utf-8").splitlines()
        enabled = lines[0].strip() == "1" if lines else False
        health_cmd = lines[1].strip() if len(lines) > 1 else ""
        return enabled, health_cmd
