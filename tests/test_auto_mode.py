"""Tests for /auto mode — auto-approve + auto-pilot continuation."""
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── memory_manager: persist auto mode ────────────────────────────────

class TestAutoModePersistence:
    def test_save_and_load_auto_mode(self, base_dir):
        """Auto mode flag should persist across MemoryManager instances."""
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "test-project")
        assert mm.load_auto_mode() is False  # default off

        mm.save_auto_mode(True)
        assert mm.load_auto_mode() is True

        # New instance reads from disk
        mm2 = MemoryManager(base_dir, "test-project")
        assert mm2.load_auto_mode() is True

    def test_auto_mode_off(self, base_dir):
        """Turning auto mode off should persist."""
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "test-project")
        mm.save_auto_mode(True)
        mm.save_auto_mode(False)
        assert mm.load_auto_mode() is False

    def test_auto_mode_missing_file_returns_false(self, base_dir):
        """When no auto.txt exists, load_auto_mode should return False."""
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "test-project")
        assert mm.load_auto_mode() is False


# ── action_executor: destructive bash detection ──────────────────────

class TestDestructiveBashDetection:
    def test_rm_rf_is_destructive(self):
        from utils.action_executor import is_destructive_bash

        assert is_destructive_bash("rm -rf /some/dir") is True

    def test_drop_table_is_destructive(self):
        from utils.action_executor import is_destructive_bash

        assert is_destructive_bash("psql -c 'DROP TABLE users'") is True

    def test_git_push_force_is_destructive(self):
        from utils.action_executor import is_destructive_bash

        assert is_destructive_bash("git push --force origin main") is True

    def test_git_reset_hard_is_destructive(self):
        from utils.action_executor import is_destructive_bash

        assert is_destructive_bash("git reset --hard HEAD~3") is True

    def test_format_disk_is_destructive(self):
        from utils.action_executor import is_destructive_bash

        assert is_destructive_bash("format C:") is True

    def test_safe_commands_not_destructive(self):
        from utils.action_executor import is_destructive_bash

        assert is_destructive_bash("npm install") is False
        assert is_destructive_bash("python -m pytest tests/ -v") is False
        assert is_destructive_bash("pip install -r requirements.txt") is False
        assert is_destructive_bash("git add .") is False
        assert is_destructive_bash("git commit -m 'test'") is False

    def test_del_star_is_destructive(self):
        from utils.action_executor import is_destructive_bash

        assert is_destructive_bash("del /s /q *.py") is True

    def test_sudo_rm_is_destructive(self):
        from utils.action_executor import is_destructive_bash

        assert is_destructive_bash("sudo rm -rf /var/log") is True

    def test_truncate_table_is_destructive(self):
        from utils.action_executor import is_destructive_bash

        assert is_destructive_bash("mysql -e 'TRUNCATE TABLE orders'") is True


# ── action_executor: auto-approve behaviour ──────────────────────────

class TestAutoApproveMode:
    def test_file_writes_auto_approved_in_auto_mode(self, tmp_path):
        """In auto mode, file writes should proceed without prompting."""
        from utils.action_executor import Action, prompt_and_execute

        actions = [
            Action(kind="file", label="src/app.py", content="print('hello')", agent_name="Sam"),
        ]
        with patch("utils.action_executor.console"):
            outcomes = prompt_and_execute(actions, tmp_path, auto_mode=True)

        assert any("FILE WRITTEN" in o for o in outcomes)
        assert (tmp_path / "src" / "app.py").read_text() == "print('hello')"

    def test_safe_bash_auto_approved_in_auto_mode(self, tmp_path):
        """Safe bash commands should auto-approve in auto mode."""
        from utils.action_executor import Action, prompt_and_execute

        actions = [
            Action(kind="bash", label="echo hello", content="echo hello", agent_name="Sam"),
        ]
        with patch("utils.action_executor.console"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="hello\n", stderr=""
            )
            outcomes = prompt_and_execute(actions, tmp_path, auto_mode=True)

        assert any("BASH OK" in o for o in outcomes)

    def test_destructive_bash_still_prompts_in_auto_mode(self, tmp_path):
        """Destructive bash commands must ALWAYS prompt, even in auto mode."""
        from utils.action_executor import Action, prompt_and_execute

        actions = [
            Action(kind="bash", label="rm -rf /", content="rm -rf /", agent_name="Sam"),
        ]
        with patch("utils.action_executor.console"), \
             patch("utils.action_executor.Confirm") as mock_confirm:
            mock_confirm.ask.return_value = False
            outcomes = prompt_and_execute(actions, tmp_path, auto_mode=True)

        assert any("BASH SKIPPED" in o for o in outcomes)
        # Confirm.ask should have been called for the destructive command
        mock_confirm.ask.assert_called()

    def test_non_auto_mode_still_prompts_for_files(self, tmp_path):
        """Without auto mode, file writes should still require user prompt."""
        from utils.action_executor import Action, prompt_and_execute

        actions = [
            Action(kind="file", label="test.py", content="pass", agent_name="Sam"),
        ]
        with patch("utils.action_executor.console") as mock_console:
            mock_console.input.return_value = "n"
            outcomes = prompt_and_execute(actions, tmp_path, auto_mode=False)

        assert any("FILE SKIPPED" in o for o in outcomes)

    def test_direct_message_loads_auto_mode_from_disk(self, base_dir, config):
        """@mention direct messages must reload _turn_auto from disk,
        not use the stale __init__ default (False)."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # Simulate /auto on — save to disk
        orch.memory.save_auto_mode(True)
        # __init__ set _turn_auto = False (stale)
        assert orch._turn_auto is False

        # Mock the agent to return a response with EXEC blocks
        mock_agent = MagicMock()
        mock_agent.respond.return_value = (
            "Done.\n\nEXEC:file:test.py\n```python\npass\n```"
        )
        orch.agents["developer"] = mock_agent

        # Mock prompt_and_execute to capture the auto_mode param
        with patch("orchestrator.prompt_and_execute") as mock_pae, \
             patch("orchestrator.console"):
            mock_pae.return_value = ["FILE WRITTEN: test.py"]
            orch.direct_message("developer", "write test.py")

        # prompt_and_execute must have been called with auto_mode=True
        mock_pae.assert_called_once()
        _, kwargs = mock_pae.call_args
        assert kwargs.get("auto_mode") is True


# ── orchestrator: auto-pilot continuation ────────────────────────────

class TestAutoPilotSafetyGuards:
    """Guards that prevent auto-pilot from getting stuck in a loop."""

    def test_failure_exit_stops_on_bash_failure(self, base_dir, config):
        """Auto-pilot should stop if the last iteration had an unresolved BASH FAILED."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        result = orch._auto_pilot_decide(
            user_input="build the auth system",
            final_response="BASH FAILED (exit 1): npm test\nOUTPUT:\nError: Cannot find module",
            iteration=0,
        )
        assert result["continue"] is False

    def test_failure_exit_stops_on_health_check_failure(self, base_dir, config):
        """Auto-pilot should stop if the last iteration had an unresolved HEALTH_CHECK FAILED."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        result = orch._auto_pilot_decide(
            user_input="implement login",
            final_response="HEALTH_CHECK: FAILED\nImportError: cannot import name 'foo'",
            iteration=1,
        )
        assert result["continue"] is False

    def test_failure_exit_allows_continue_on_success(self, base_dir, config):
        """Auto-pilot should NOT stop if the last iteration succeeded."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {"continue": True, "next_message": "Now write tests"}
            result = orch._auto_pilot_decide(
                user_input="build the auth system",
                final_response="BASH OK: npm install\nAll dependencies installed.",
                iteration=0,
            )
        assert result["continue"] is True

    def test_failure_exit_continues_when_retry_resolved(self, base_dir, config):
        """Auto-pilot should continue if BASH FAILED was self-healed by retry."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        response = (
            "ACTIONS TAKEN:\n"
            "BASH FAILED (exit 255)\nOUTPUT:\n"
            "'tail' is not recognized as an internal or external command\n\n"
            "RETRY OUTCOMES:\n"
            "BASH OK: Get-Content log.txt -Tail 20\nOUTPUT:\nServer started on port 3000"
        )

        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {"continue": True, "next_message": "Now run tests"}
            result = orch._auto_pilot_decide(
                user_input="build the server",
                final_response=response,
                iteration=0,
            )
        assert result["continue"] is True

    def test_failure_exit_continues_when_health_check_retry_resolved(self, base_dir, config):
        """Auto-pilot should continue if HEALTH_CHECK FAILED was self-healed."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        response = (
            "ACTIONS TAKEN:\n"
            "HEALTH_CHECK: FAILED\nImportError: no module named 'foo'\n\n"
            "RETRY OUTCOMES:\n"
            "FILE WRITTEN: requirements.txt\n"
            "BASH OK: pip install foo\nOUTPUT:\nSuccessfully installed foo-1.0\n"
            "HEALTH_CHECK: PASSED"
        )

        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {"continue": True, "next_message": "Continue implementation"}
            result = orch._auto_pilot_decide(
                user_input="implement the feature",
                final_response=response,
                iteration=0,
            )
        assert result["continue"] is True

    def test_failure_exit_stops_when_retry_also_failed(self, base_dir, config):
        """Auto-pilot should still stop if the retry itself also failed."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        response = (
            "ACTIONS TAKEN:\n"
            "BASH FAILED (exit 1): npm test\nOUTPUT:\nModule not found\n\n"
            "RETRY OUTCOMES:\n"
            "BASH FAILED (exit 1): npm test\nOUTPUT:\nStill broken"
        )

        result = orch._auto_pilot_decide(
            user_input="build the auth system",
            final_response=response,
            iteration=0,
        )
        assert result["continue"] is False

    def test_failure_exit_stops_when_retry_has_no_outcomes(self, base_dir, config):
        """Auto-pilot should stop if retry section exists but is empty (agent gave text only)."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        response = (
            "ACTIONS TAKEN:\n"
            "BASH FAILED (exit 255): tail -n 20 log.txt\n\n"
            "RETRY OUTCOMES:\n"
            "RETRY NOTE from Sam: I need to use Get-Content instead"
        )

        result = orch._auto_pilot_decide(
            user_input="check the logs",
            final_response=response,
            iteration=0,
        )
        assert result["continue"] is False

    def test_duplicate_detection_stops_on_repeated_message(self, base_dir, config):
        """Auto-pilot should stop if next_message is too similar to a previous one."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        previous = ["implement the login page", "write tests for auth"]
        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {
                "continue": True,
                "next_message": "implement the login page",  # exact duplicate
            }
            result = orch._auto_pilot_decide(
                user_input="build the auth system",
                final_response="Requirements done.",
                iteration=1,
                previous_messages=previous,
            )
        assert result["continue"] is False

    def test_duplicate_detection_catches_near_duplicates(self, base_dir, config):
        """Auto-pilot should catch near-duplicate messages (>80% similar)."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        previous = ["Now implement the login page with JWT authentication"]
        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {
                "continue": True,
                "next_message": "Implement the login page with JWT authentication now",  # ~80% similar
            }
            result = orch._auto_pilot_decide(
                user_input="build the auth system",
                final_response="Auth module scaffolded.",
                iteration=1,
                previous_messages=previous,
            )
        assert result["continue"] is False

    def test_duplicate_detection_allows_genuinely_different(self, base_dir, config):
        """Auto-pilot should allow genuinely different next steps."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        previous = ["implement the login page"]
        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {
                "continue": True,
                "next_message": "write unit tests for the registration endpoint",
            }
            result = orch._auto_pilot_decide(
                user_input="build the auth system",
                final_response="Login page implemented.",
                iteration=1,
                previous_messages=previous,
            )
        assert result["continue"] is True


class TestAutoPilotDecision:
    def test_auto_pilot_returns_continue_or_done(self, base_dir, config):
        """_auto_pilot_decide should return a dict with 'continue' bool."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {
                "continue": True,
                "next_message": "Now implement the login page",
            }
            result = orch._auto_pilot_decide(
                user_input="build the auth system",
                final_response="Requirements are ready. Next: implement login.",
            )

        assert "continue" in result
        assert isinstance(result["continue"], bool)

    def test_auto_pilot_caps_iterations(self, base_dir, config):
        """Auto-pilot should stop after MAX_AUTO_ITERATIONS."""
        from orchestrator import Orchestrator, MAX_AUTO_ITERATIONS
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # Simulate already at max iterations
        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {"continue": True, "next_message": "keep going"}
            result = orch._auto_pilot_decide(
                user_input="build the auth system",
                final_response="Done phase 1",
                iteration=MAX_AUTO_ITERATIONS,
            )
        # Should force-stop regardless of what haiku says
        assert result["continue"] is False

    def test_synthesis_always_concise(self, base_dir, config):
        """Synthesis prompt should ALWAYS use concise style — not gated by /auto."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)
        # /auto is OFF — synthesis should still be concise
        orch._turn_auto = False

        prompt = orch._synthesis_prompt(
            "build the auth system",
            {"developer": "I'll implement the login page."},
        )
        # Should NEVER ask "what would you like to do next" regardless of /auto
        assert "Always close your response with" not in prompt
        # Should instruct Aria not to list options
        assert "Do NOT ask" in prompt


# ── Option B: always-on auto-pilot ─────────────────────────────────

class TestAlwaysOnAutoPilot:
    """Auto-pilot always runs for actionable tasks — NOT gated by /auto toggle."""

    def test_has_actionable_work_with_actions_taken(self, base_dir, config):
        """_has_actionable_work returns True when responses contain ACTIONS TAKEN."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        responses = {"developer": "Code written.\n\nACTIONS TAKEN:\nFILE WRITTEN: src/app.py"}
        phases = [{"name": "Implement", "agents": ["developer"], "tasks": {"developer": "build it"}}]
        assert orch._has_actionable_work(responses, phases) is True

    def test_has_actionable_work_with_multi_phase(self, base_dir, config):
        """_has_actionable_work returns True for multi-phase routing."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        responses = {"pm": "Requirements gathered."}
        phases = [
            {"name": "Requirements", "agents": ["pm"], "tasks": {"pm": "gather"}},
            {"name": "Implement", "agents": ["developer"], "tasks": {"developer": "build"}},
        ]
        assert orch._has_actionable_work(responses, phases) is True

    def test_has_actionable_work_false_for_simple_qa(self, base_dir, config):
        """_has_actionable_work returns False for simple Q&A responses."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        responses = {"pm": "The project uses Node.js with Express."}
        phases = [{"name": "General", "agents": ["pm"], "tasks": {"pm": "explain"}}]
        assert orch._has_actionable_work(responses, phases) is False

    def test_synthesis_concise_without_auto_mode(self, base_dir, config):
        """Synthesis stays concise even when /auto is OFF."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)
        orch._turn_auto = False  # /auto is OFF

        prompt = orch._synthesis_prompt(
            "build the auth system",
            {"developer": "I'll implement the login page."},
        )
        # Even without /auto, should NOT ask "what would you like to do next"
        assert "Always close your response with" not in prompt

    def test_single_agent_final_response_not_empty(self, base_dir, config):
        """When only one agent responds (synthesis skipped), auto-pilot should
        still receive the agent's response as context — not an empty string."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # Simulate the scenario: single agent with ACTIONS TAKEN
        agent_responses = {
            "qa": "Running tests.\n\nACTIONS TAKEN:\nBASH OK: pytest\nOUTPUT:\n28 passed"
        }
        # Synthesis is skipped for single-agent → final_response stays ""
        final_response = ""

        # _build_auto_pilot_context should fall back to agent responses
        pilot_context = orch._build_auto_pilot_context(final_response, agent_responses)
        assert len(pilot_context) > 0
        assert "ACTIONS TAKEN:" in pilot_context

    def test_export_path_saves_rich_message(self, base_dir, config):
        """Export path should save a message with enough context for auto-pilot
        to decide next steps — not just '[Generated doc_type]'."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # Mock export_doc so we don't actually call LLM
        with patch.object(orch, "export_doc") as mock_export, \
             patch.object(orch, "_detect_export_intent", return_value=("qa", "test-plan")), \
             patch.object(orch, "_detect_and_save_correction"), \
             patch.object(orch, "_update_project_state"):
            orch.process("generate a test plan")

        # The assistant message saved should be richer than just "[Generated test-plan]"
        last_msg = orch.messages[-1]
        assert last_msg["role"] == "assistant"
        assert "test-plan" in last_msg["content"]
        # Must include next-step hint for auto-pilot context
        assert len(last_msg["content"]) > len("[Generated test-plan]")

    def test_export_path_updates_project_state(self, base_dir, config):
        """Export path should call _update_project_state so state.md is
        current for the next auto-pilot iteration."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        with patch.object(orch, "export_doc") as mock_export, \
             patch.object(orch, "_detect_export_intent", return_value=("pm", "requirements")), \
             patch.object(orch, "_detect_and_save_correction"), \
             patch.object(orch, "_update_project_state") as mock_update:
            orch.process("export the requirements doc")

        mock_update.assert_called_once()
        # The call should pass a meaningful context (not empty)
        args, kwargs = mock_update.call_args
        user_input_arg = args[0]
        assert "requirements" in user_input_arg.lower() or "export" in user_input_arg.lower()

    def test_auto_pilot_augments_export_context(self, base_dir, config):
        """When auto-pilot's last iteration was an export, the context passed
        to _auto_pilot_decide should be augmented with the original request
        so Haiku doesn't stall on the terse export message."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # Simulate: auto-pilot loop reads an export message from self.messages
        # The _augment_pilot_context_for_export helper should enrich it
        export_msg = "[Generated test-plan] — Document saved. Next the team should run tests."
        original_request = "build the authentication system"

        augmented = orch._augment_pilot_context_for_export(export_msg, original_request)

        # Must include the original request so Haiku can reason about remaining work
        assert original_request in augmented
        # Must signal that the export was an intermediate step
        assert "intermediate" in augmented.lower() or "sub-step" in augmented.lower() or "part of" in augmented.lower()

    def test_auto_pilot_no_augment_for_normal_response(self, base_dir, config):
        """Normal (non-export) responses should NOT be augmented."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        normal_msg = "The team implemented the login page with JWT auth."
        result = orch._augment_pilot_context_for_export(normal_msg, "build auth")

        # Normal messages should be returned unchanged
        assert result == normal_msg
