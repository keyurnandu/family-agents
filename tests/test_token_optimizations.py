"""Tests for prompt/context token optimizations."""
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_orchestrator(base_dir, config, project_name="token-test"):
    from orchestrator import Orchestrator
    from utils.db_manager import DBManager
    from utils.display import Display

    db = DBManager(base_dir / "db" / "conversations.db")
    display = Display()
    orch = Orchestrator(
        project_name=project_name,
        base_dir=base_dir,
        db=db,
        display=display,
        config=config,
    )
    return orch, db


class TestAgentPromptTokenTrim:
    def test_exec_delivery_instructions_are_not_duplicated(self, base_dir, config):
        """Implementation prompts should have one shared EXEC instruction block."""
        from agents.agent import Agent, _EXEC_INSTRUCTIONS
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "_general")
        agent = Agent(
            role="developer",
            persona=config["agent_personas"]["developer"],
            memory=mm,
            model="sonnet",
            base_dir=base_dir,
        )

        prompt = agent._build_system_prompt(task="implement a script")

        assert _EXEC_INSTRUCTIONS in prompt
        assert "## Delivering Files and Commands" not in prompt
        assert prompt.count("## Executing Actions") == 1
        assert "Always include the COMPLETE file content" in _EXEC_INSTRUCTIONS

    def test_prompt_cache_key_changes_when_key_file_content_changes(self, base_dir, config):
        """Prompt cache invalidation should reflect key file content, not only filenames."""
        from agents.agent import Agent
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "_general")
        mock_orch = MagicMock()
        mock_orch.config = config
        mock_orch.loaded_path = Path(r"C:\repo")
        mock_orch.codebase_context = {
            "structure_tree": "repo/\n└── README.md",
            "key_files": {"README.md": "version one"},
            "tech_stack": ["Python"],
            "total_files": 1,
        }

        agent = Agent(
            role="developer",
            persona=config["agent_personas"]["developer"],
            memory=mm,
            model="sonnet",
            base_dir=base_dir,
            orchestrator=mock_orch,
        )

        first_key = agent._prompt_cache_key()
        mock_orch.codebase_context["key_files"]["README.md"] = "version two"
        second_key = agent._prompt_cache_key()

        assert first_key != second_key


class TestRoutingPromptTokenTrim:
    def test_routing_uses_state_routing_summary_when_present(self, base_dir, config):
        """Routing should receive the compact state summary, not the full state document."""
        orch, db = _make_orchestrator(base_dir, config)
        project_dir = base_dir / "projects" / "token-test"
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "state.md").write_text(
            "# Project State\n\n"
            "## Routing Summary\n"
            "- Auth flow is built.\n"
            "- Next step is test coverage.\n\n"
            "## What Exists\n"
            "PRIVATE DETAIL SHOULD NOT ROUTE " * 80,
            encoding="utf-8",
        )
        orch._turn_state = orch._load_project_state()

        prompt = orch._routing_system_prompt()

        assert "Auth flow is built" in prompt
        assert "Next step is test coverage" in prompt
        assert "PRIVATE DETAIL SHOULD NOT ROUTE" not in prompt
        db.close()

    def test_routing_doc_index_is_cached_by_mtime(self, base_dir, config):
        """Repeated routing doc-index reads should hit a cache until docs change."""
        orch, db = _make_orchestrator(base_dir, config)
        docs_dir = base_dir / "projects" / "token-test" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "requirements.md").write_text(
            "# Requirements\n\nFirst useful line.",
            encoding="utf-8",
        )

        original = Path.read_text
        with patch.object(
            Path,
            "read_text",
            autospec=True,
            side_effect=lambda self, *args, **kwargs: original(self, *args, **kwargs),
        ) as mock_read:
            first = orch._routing_doc_index()
            second = orch._routing_doc_index()

        assert first == second
        assert "requirements.md" in first
        assert mock_read.call_count == 1
        db.close()


class TestSynthesisAndMemoryTokenTrim:
    def test_synthesis_system_prompt_uses_compact_file_error_rule(self, base_dir, config):
        """Aria's synthesis prompt should keep constraints but avoid the old verbose warning."""
        orch, db = _make_orchestrator(base_dir, config, project_name="_general")
        prompt = orch._synthesis_system_prompt()

        assert "## CRITICAL CONSTRAINT" in prompt
        assert "FILE ERROR RULE" not in prompt
        assert "Do not mention sandbox" in prompt
        db.close()

    def test_should_skip_synthesis_for_one_substantive_response(self):
        """Multiple routed agents do not always need an extra synthesis call."""
        from orchestrator import Orchestrator

        responses = {
            "developer": "Implemented the change.\n\nACTIONS TAKEN:\nFILE WRITTEN: app.py",
            "lead": "Looks good.",
            "pm": "",
        }

        assert Orchestrator._should_synthesize(responses, all_file_errors=False) is False

    def test_should_synthesize_for_multiple_substantive_responses(self):
        from orchestrator import Orchestrator

        responses = {
            "developer": "Implemented the endpoint and updated config.",
            "lead": "Reviewed architecture tradeoffs and found migration risks.",
        }

        assert Orchestrator._should_synthesize(responses, all_file_errors=False) is True

    def test_default_doc_injection_budget_is_tighter(self, config):
        assert config["max_doc_chars"] <= 1000

    def test_skill_consolidation_is_more_aggressive(self):
        from orchestrator import Orchestrator

        assert Orchestrator._CONSOLIDATION_THRESHOLD <= 2000
        assert Orchestrator._CONSOLIDATION_MIN_LESSONS <= 6
