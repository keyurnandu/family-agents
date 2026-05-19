import re
from datetime import datetime
from pathlib import Path


class MemoryManager:
    def __init__(self, base_dir: Path, project_name: str):
        self.base_dir = base_dir
        self.project_name = project_name
        self.roles_dir = base_dir / "memory" / "roles"
        self.dynamic_dir = base_dir / "memory" / "dynamic" / project_name
        self.dynamic_dir.mkdir(parents=True, exist_ok=True)

    def load_role_memory(self, role: str) -> str:
        role_file = self.roles_dir / f"{role}.md"
        if role_file.exists():
            return role_file.read_text(encoding="utf-8")
        return f"# {role.upper()}\nNo predefined role memory found."

    def load_project_memory(self) -> str:
        memory_file = self.dynamic_dir / "memory.md"
        if memory_file.exists():
            content = memory_file.read_text(encoding="utf-8")
            return content if content.strip() else ""
        return ""

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
        """Return parsed memory entries as a list of dicts."""
        content = self.load_project_memory()
        if not content:
            return []

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
        return entries

    def delete_project_memory(self):
        memory_file = self.dynamic_dir / "memory.md"
        if memory_file.exists():
            memory_file.unlink()

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
