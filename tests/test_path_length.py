"""Tests for Windows long-path mitigations."""
from pathlib import Path


class TestAgentPromptUsesRelativePaths:
    def test_prompt_instructs_relative_paths_for_bash(self, base_dir, config):
        """Agent system prompt should tell agents to use relative paths in EXEC:bash,
        because cwd is already set to the project/codebase root."""
        from agents.agent import Agent
        from utils.memory_manager import MemoryManager
        from unittest.mock import MagicMock

        mm = MemoryManager(base_dir, "_general")
        personas = config["agent_personas"]

        # Simulate a loaded codebase with a long OneDrive path
        mock_orch = MagicMock()
        mock_orch.active_roster = ["developer"]
        mock_orch.loaded_path = Path(
            r"C:\Users\knandu\OneDrive - Adobe\Desktop\Claude\some-project"
        )
        mock_orch.codebase_context = {
            "structure_tree": "src/\n  app.py",
            "key_files": {},
            "tech_stack": ["Python"],
            "total_files": 5,
        }
        mock_orch.config = config

        agent = Agent(
            role="developer",
            persona=personas.get("developer", {"name": "Sam"}),
            memory=mm,
            model="sonnet",
            base_dir=base_dir,
            orchestrator=mock_orch,
        )

        prompt = agent._build_system_prompt(task="implement the API")
        # Should explicitly mention relative paths for bash commands
        # (not just for file paths which is already there)
        assert "EXEC:bash" in prompt and "relative" in prompt.lower(), (
            "Prompt should instruct agents to use relative paths for EXEC:bash commands"
        )
        # Should NOT include the full absolute OneDrive path in bash instructions
        # The path can appear in the codebase header, but bash instructions should say to use relative
        assert "absolute" in prompt.lower() or "working directory is" in prompt.lower(), (
            "Prompt should warn agents about absolute paths or confirm cwd is set"
        )


class TestActionExecutorPathNormalization:
    def test_absolute_path_in_bash_normalized_to_relative(self):
        """If an agent's EXEC:bash command contains the project_dir absolute path,
        it should be stripped to a relative path before execution."""
        from utils.action_executor import normalize_bash_command

        project_dir = Path(
            r"C:\Users\knandu\OneDrive - Adobe\Desktop\Claude\family-agents\projects\my-app"
        )
        # Sam writes a command with the full absolute path
        cmd = str(project_dir / "venv" / "Scripts" / "python.exe") + " -m pytest tests/ -v"
        normalized = normalize_bash_command(cmd, project_dir)
        # Should be relative
        assert str(project_dir) not in normalized
        assert normalized.startswith("venv")

    def test_relative_command_unchanged(self):
        """Commands that are already relative should not be modified."""
        from utils.action_executor import normalize_bash_command

        project_dir = Path(r"C:\Users\knandu\OneDrive - Adobe\Desktop\Claude\family-agents\projects\my-app")
        cmd = r"venv\Scripts\python.exe -m pytest tests/ -v"
        normalized = normalize_bash_command(cmd, project_dir)
        assert normalized == cmd

    def test_multiple_absolute_paths_normalized(self):
        """Multiple occurrences of the project path in a command should all be replaced."""
        from utils.action_executor import normalize_bash_command

        project_dir = Path(
            r"C:\Users\knandu\OneDrive - Adobe\Desktop\Claude\family-agents\projects\my-app"
        )
        abs_python = str(project_dir / "venv" / "Scripts" / "python.exe")
        abs_config = str(project_dir / "config" / "settings.yaml")
        cmd = f"{abs_python} check.py --config {abs_config}"
        normalized = normalize_bash_command(cmd, project_dir)
        assert str(project_dir) not in normalized
        assert "venv" in normalized
        assert "config" in normalized


class TestNormalizeMultipleDirs:
    """When a codebase is /loaded at a short path, bash commands may still
    reference the long OneDrive project_dir or base_dir. normalize_bash_command
    should strip ALL of them."""

    def test_strips_project_dir_when_write_dir_is_loaded_path(self):
        """Agent uses OneDrive project path even though cwd is the loaded path."""
        from utils.action_executor import normalize_bash_command

        base_dir = Path(r"C:\Users\knandu\OneDrive - Adobe\Desktop\Claude\family-agents")
        project_dir = base_dir / "projects" / "uishift"
        loaded_path = Path(r"C:\uishift\backend2")

        # Sam references the project venv, not the loaded codebase
        cmd = str(project_dir / "venv" / "Scripts" / "python.exe") + " -m pytest tests/ -v"
        normalized = normalize_bash_command(cmd, loaded_path, [project_dir, base_dir])
        assert str(project_dir) not in normalized
        assert normalized.startswith("venv")

    def test_strips_base_dir_from_bash_command(self):
        """Agent references a file in the family-agents root."""
        from utils.action_executor import normalize_bash_command

        base_dir = Path(r"C:\Users\knandu\OneDrive - Adobe\Desktop\Claude\family-agents")
        loaded_path = Path(r"C:\uishift\backend2")

        cmd = str(base_dir / "utils" / "some_tool.py") + " --check"
        normalized = normalize_bash_command(cmd, loaded_path, [base_dir])
        assert str(base_dir) not in normalized
        assert "utils" in normalized

    def test_no_extra_dirs_still_works(self):
        """Backward compat: calling without extra_dirs should still work."""
        from utils.action_executor import normalize_bash_command

        project_dir = Path(r"C:\Users\knandu\OneDrive - Adobe\Desktop\Claude\family-agents\projects\my-app")
        cmd = str(project_dir / "venv" / "Scripts" / "python.exe") + " -m pytest"
        normalized = normalize_bash_command(cmd, project_dir)
        assert str(project_dir) not in normalized
        assert normalized.startswith("venv")

    def test_loaded_path_itself_is_also_stripped(self):
        """The primary write_dir (loaded path) should also be stripped."""
        from utils.action_executor import normalize_bash_command

        base_dir = Path(r"C:\Users\knandu\OneDrive - Adobe\Desktop\Claude\family-agents")
        loaded_path = Path(r"C:\uishift\backend2")

        cmd = str(loaded_path / "node_modules" / ".bin" / "jest") + " --coverage"
        normalized = normalize_bash_command(cmd, loaded_path, [base_dir])
        assert str(loaded_path) not in normalized
        assert normalized.startswith("node_modules")
