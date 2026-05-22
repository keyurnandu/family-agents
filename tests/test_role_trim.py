"""Tests for trimmed role files and shared EXEC instructions."""
from pathlib import Path

ROLES_DIR = Path(__file__).resolve().parent.parent / "memory" / "roles"
IMPL_ROLES = {"developer", "lead", "qa", "devops"}


class TestRoleFilesTrimmed:
    def test_no_exec_instructions_section_in_role_files(self):
        """The '## Executing Actions' section should not exist in role files —
        it's injected by code via the shared _EXEC_INSTRUCTIONS constant."""
        for md in ROLES_DIR.glob("*.md"):
            content = md.read_text(encoding="utf-8")
            assert "## Executing Actions" not in content, (
                f"{md.name} still contains '## Executing Actions' section — "
                "these should be in the shared constant"
            )

    def test_role_files_under_line_limit(self):
        """Each role file should be under 80 lines after extracting shared EXEC sections."""
        for md in ROLES_DIR.glob("*.md"):
            lines = md.read_text(encoding="utf-8").splitlines()
            assert len(lines) <= 80, (
                f"{md.name} has {len(lines)} lines (limit 80)"
            )

    def test_shared_exec_constant_exists(self):
        """agents/agent.py should define a shared EXEC instructions constant."""
        from agents.agent import _EXEC_INSTRUCTIONS
        assert "EXEC:file" in _EXEC_INSTRUCTIONS
        assert "EXEC:bash" in _EXEC_INSTRUCTIONS

    def test_exec_injected_for_impl_roles(self, base_dir, config):
        """Implementation-capable roles should get EXEC instructions in their prompt."""
        from agents.agent import Agent
        from utils.memory_manager import MemoryManager
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        mm = MemoryManager(base_dir, "_general")
        personas = config["agent_personas"]

        for role in IMPL_ROLES:
            persona = personas.get(role, {"name": role})
            agent = Agent(
                role=role,
                persona=persona,
                memory=mm,
                model="sonnet",
                base_dir=base_dir,
            )
            prompt = agent._build_system_prompt()
            assert "EXEC:file" in prompt, (
                f"{role} prompt should contain EXEC instructions"
            )
        db.close()

    def test_exec_not_injected_for_non_impl_roles(self, base_dir, config):
        """Non-implementation roles (pm, bsa, researcher) should NOT get the
        full '## Executing Actions' block."""
        from agents.agent import Agent, _EXEC_INSTRUCTIONS
        from utils.memory_manager import MemoryManager
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        mm = MemoryManager(base_dir, "_general")
        personas = config["agent_personas"]

        for role in ("pm", "bsa", "researcher"):
            persona = personas.get(role, {"name": role})
            agent = Agent(
                role=role,
                persona=persona,
                memory=mm,
                model="sonnet",
                base_dir=base_dir,
            )
            prompt = agent._build_system_prompt()
            assert _EXEC_INSTRUCTIONS not in prompt, (
                f"{role} prompt should NOT contain the shared EXEC instructions block"
            )
        db.close()
