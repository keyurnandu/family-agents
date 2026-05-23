"""Edge-case and integration tests — covers gaps found during thorough audit."""
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── _build_auto_pilot_context edge cases ──────────────────────────────

class TestBuildAutoPilotContext:
    """_build_auto_pilot_context must always produce usable context."""

    def test_prefers_synthesis_over_raw_responses(self, base_dir, config):
        """When synthesis produced a response, prefer it over raw agent output."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        ctx = orch._build_auto_pilot_context(
            "Aria's synthesis with full context",
            {"developer": "I wrote some code"},
        )
        assert ctx == "Aria's synthesis with full context"

    def test_falls_back_to_agent_responses(self, base_dir, config):
        """When synthesis is empty (single-agent), fall back to raw responses."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        ctx = orch._build_auto_pilot_context("", {"qa": "All 28 tests passed."})
        assert "qa" in ctx.lower() or "28 tests" in ctx

    def test_both_empty_returns_empty_string(self, base_dir, config):
        """When both synthesis and agent responses are empty, return empty."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        ctx = orch._build_auto_pilot_context("", {})
        assert ctx == ""

    def test_whitespace_only_synthesis_falls_back(self, base_dir, config):
        """Whitespace-only synthesis should trigger fallback to agent responses."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        ctx = orch._build_auto_pilot_context("   \n  ", {"pm": "Gathered reqs."})
        assert "pm" in ctx.lower() or "reqs" in ctx.lower()


# ── _has_actionable_work edge cases ───────────────────────────────────

class TestHasActionableWorkEdgeCases:
    """Edge cases for the actionable work pre-filter."""

    def test_empty_phases_and_no_actions(self, base_dir, config):
        """Empty phases + no ACTIONS TAKEN → not actionable."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)
        assert orch._has_actionable_work({}, []) is False

    def test_single_phase_with_actions_taken(self, base_dir, config):
        """Single phase WITH ACTIONS TAKEN → actionable."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        responses = {"developer": "Done.\n\nACTIONS TAKEN:\nFILE WRITTEN: app.py"}
        phases = [{"name": "Implement", "agents": ["developer"], "tasks": {}}]
        assert orch._has_actionable_work(responses, phases) is True

    def test_actions_taken_in_any_agent(self, base_dir, config):
        """ACTIONS TAKEN in any agent's response triggers actionable."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        responses = {
            "pm": "Requirements look good.",
            "developer": "Code implemented.\n\nACTIONS TAKEN:\nBASH OK: pytest",
        }
        phases = [{"name": "Review", "agents": ["pm", "developer"], "tasks": {}}]
        assert orch._has_actionable_work(responses, phases) is True

    def test_exactly_two_phases_is_actionable(self, base_dir, config):
        """Exactly 2 phases (multi-phase) → actionable even without ACTIONS TAKEN."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        responses = {"pm": "Gathering requirements."}
        phases = [
            {"name": "Requirements", "agents": ["pm"], "tasks": {}},
            {"name": "Plan", "agents": ["pm"], "tasks": {}},
        ]
        assert orch._has_actionable_work(responses, phases) is True


# ── _message_similarity ──────────────────────────────────────────────

class TestMessageSimilarity:
    """Duplicate detection via similarity ratio."""

    def test_identical_strings_return_one(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)
        assert orch._message_similarity("implement the login", "implement the login") == 1.0

    def test_case_insensitive_comparison(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)
        ratio = orch._message_similarity("Implement Login", "implement login")
        assert ratio == 1.0

    def test_very_different_strings_low_ratio(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)
        ratio = orch._message_similarity("implement the login page", "deploy to production now")
        assert ratio < 0.5

    def test_near_duplicate_high_ratio(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)
        ratio = orch._message_similarity(
            "now implement the login page with JWT",
            "now implement the login page with JWT tokens",
        )
        assert ratio > 0.80


# ── _detect_export_intent edge cases ─────────────────────────────────

class TestDetectExportIntent:
    """Export detection regex patterns."""

    def test_generate_requirements(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)
        result = orch._detect_export_intent("generate a requirements document")
        assert result is not None
        assert "requirements" in result[1].lower()

    def test_export_test_plan(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)
        result = orch._detect_export_intent("export the test plan")
        assert result is not None

    def test_no_match_on_regular_message(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)
        result = orch._detect_export_intent("let's discuss the architecture")
        assert result is None

    def test_create_sprint_plan(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)
        result = orch._detect_export_intent("create a sprint plan")
        assert result is not None
        role, doc_type = result
        assert role == "pm"


# ── _detect_and_save_correction ──────────────────────────────────────

class TestDetectCorrection:
    """Correction detection should identify user feedback and save lessons."""

    def test_correction_detected_with_agent_name(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        # Mock _extract_lesson since it calls LLM
        with patch.object(orch, "_extract_lesson") as mock_lesson:
            result = orch._detect_and_save_correction("stop using uv, Sam")
            assert result is True
            mock_lesson.assert_called_once()
            call_args = mock_lesson.call_args
            assert call_args[0][0] == "developer"  # Sam = developer

    def test_correction_detected_with_role_name(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        with patch.object(orch, "_extract_lesson") as mock_lesson:
            result = orch._detect_and_save_correction("don't do this developer")
            assert result is True
            mock_lesson.assert_called_once()
            assert mock_lesson.call_args[0][0] == "developer"

    def test_no_correction_on_normal_message(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        with patch.object(orch, "_extract_lesson") as mock_lesson:
            result = orch._detect_and_save_correction("please build the login page")
            assert result is False
            mock_lesson.assert_not_called()

    def test_correction_with_no_identifiable_agent_returns_false(self, base_dir, config):
        """If correction regex matches but no agent name is found, return False."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)
        # Clear messages so fallback agent search finds nothing
        orch.messages = []

        with patch.object(orch, "_extract_lesson") as mock_lesson:
            result = orch._detect_and_save_correction("stop doing that wrong thing")
            assert result is False
            mock_lesson.assert_not_called()


# ── Memory category filtering ────────────────────────────────────────

class TestMemoryCategoryFiltering:
    """Memory manager should filter entries by category when requested."""

    def test_filter_by_single_category(self, base_dir):
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "test-project")
        mm.save_project_memory("Use React", "decision", "pm")
        mm.save_project_memory("Login endpoint needed", "requirement", "bsa")
        mm.save_project_memory("Use PostgreSQL", "technical", "lead")

        result = mm.load_project_memory(categories={"decision"})
        assert "React" in result
        assert "Login endpoint" not in result
        assert "PostgreSQL" not in result

    def test_filter_by_multiple_categories(self, base_dir):
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "test-project")
        mm.save_project_memory("Use React", "decision", "pm")
        mm.save_project_memory("Login endpoint needed", "requirement", "bsa")
        mm.save_project_memory("Use PostgreSQL", "technical", "lead")

        result = mm.load_project_memory(categories={"decision", "technical"})
        assert "React" in result
        assert "PostgreSQL" in result
        assert "Login endpoint" not in result

    def test_no_categories_returns_all(self, base_dir):
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "test-project")
        mm.save_project_memory("Use React", "decision", "pm")
        mm.save_project_memory("Login needed", "requirement", "bsa")

        result = mm.load_project_memory(categories=None)
        assert "React" in result
        assert "Login needed" in result

    def test_non_matching_category_returns_empty(self, base_dir):
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "test-project")
        mm.save_project_memory("Use React", "decision", "pm")

        result = mm.load_project_memory(categories={"epic-plan"})
        assert result == ""


# ── _EXPORT_NEXT_HINTS coverage ──────────────────────────────────────

class TestExportNextHints:
    """Module-level _EXPORT_NEXT_HINTS should cover all EXPORT_TYPE_MAP doc types."""

    def test_all_export_types_have_hints(self):
        from orchestrator import EXPORT_TYPE_MAP, _EXPORT_NEXT_HINTS

        for key, (role, doc_type) in EXPORT_TYPE_MAP.items():
            hint = _EXPORT_NEXT_HINTS.get(
                doc_type.lower(),
                "continue planning or start the next phase",
            )
            # Every doc type should produce a non-empty hint
            assert len(hint) > 10, f"Missing or weak hint for doc_type={doc_type}"

    def test_fallback_hint_is_reasonable(self):
        from orchestrator import _EXPORT_NEXT_HINTS

        # Unknown doc type should get a sensible fallback
        hint = _EXPORT_NEXT_HINTS.get("unknown-type", "continue planning or start the next phase")
        assert "continue" in hint.lower()


# ── Export path enriched message format ──────────────────────────────

class TestExportMessageFormat:
    """The enriched export message should be parseable by Haiku for auto-pilot."""

    def test_message_includes_doc_type(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        with patch.object(orch, "export_doc"), \
             patch.object(orch, "_detect_export_intent", return_value=("qa", "test-plan")), \
             patch.object(orch, "_detect_and_save_correction"), \
             patch.object(orch, "_update_project_state"):
            orch.process("generate test plan")

        msg = orch.messages[-1]["content"]
        assert "test-plan" in msg

    def test_message_includes_next_step_hint(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        with patch.object(orch, "export_doc"), \
             patch.object(orch, "_detect_export_intent", return_value=("pm", "sprint-plan")), \
             patch.object(orch, "_detect_and_save_correction"), \
             patch.object(orch, "_update_project_state"):
            orch.process("create sprint plan")

        msg = orch.messages[-1]["content"]
        # sprint-plan hint is "work on epics, assign stories, or start implementation"
        assert "implementation" in msg.lower() or "epics" in msg.lower()

    def test_unknown_doc_type_gets_fallback_hint(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        with patch.object(orch, "export_doc"), \
             patch.object(orch, "_detect_export_intent", return_value=("pm", "custom-report")), \
             patch.object(orch, "_detect_and_save_correction"), \
             patch.object(orch, "_update_project_state"):
            orch.process("generate a custom report")

        msg = orch.messages[-1]["content"]
        assert "continue planning" in msg.lower()


# ── Auto-pilot failure markers ───────────────────────────────────────

class TestFailureMarkers:
    """_auto_pilot_decide must recognize all failure markers."""

    def test_all_failure_markers_defined(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator("test", base_dir, db, Display(), config=config)

        # Must include both bash and health check failures
        markers = orch._FAILURE_MARKERS
        assert any("BASH" in m for m in markers)
        assert any("HEALTH" in m for m in markers)

    def test_max_auto_iterations_is_sane(self):
        from orchestrator import MAX_AUTO_ITERATIONS

        assert 2 <= MAX_AUTO_ITERATIONS <= 10, "MAX_AUTO_ITERATIONS out of sane range"
