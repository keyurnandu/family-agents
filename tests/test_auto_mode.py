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

    def test_git_remote_and_destructive_ops_are_destructive(self):
        """Git commands that publish to remote or can lose work require approval."""
        from utils.action_executor import is_destructive_bash

        # Remote — publishes to remote
        assert is_destructive_bash("git push origin main") is True
        assert is_destructive_bash("git push --force origin main") is True
        # Can lose uncommitted work
        assert is_destructive_bash("git merge feature-branch") is True
        assert is_destructive_bash("git rebase main") is True
        assert is_destructive_bash("git checkout feature") is True
        assert is_destructive_bash("git switch main") is True
        # Destroys data
        assert is_destructive_bash("git stash drop") is True
        assert is_destructive_bash("git branch -d old-branch") is True
        assert is_destructive_bash("git branch -D old-branch") is True

    def test_git_local_ops_are_safe(self):
        """Local-only git ops (add, commit, tag, stash save) are safe — just checkpoints."""
        from utils.action_executor import is_destructive_bash

        # Local checkpoints
        assert is_destructive_bash("git add .") is False
        assert is_destructive_bash("git add -A") is False
        assert is_destructive_bash("git commit -m 'test'") is False
        assert is_destructive_bash("git tag v1.0") is False
        assert is_destructive_bash("git stash") is False
        # Read-only
        assert is_destructive_bash("git status") is False
        assert is_destructive_bash("git log --oneline -5") is False
        assert is_destructive_bash("git diff") is False
        assert is_destructive_bash("git diff --stat") is False
        assert is_destructive_bash("git show HEAD") is False

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

    def test_failure_exit_continues_when_agent_wrote_fixes(self, base_dir, config):
        """Auto-pilot should continue when failures exist but agent wrote fix files."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        response = (
            "Looking at the failures:\n"
            "- test_runner_state.py — all fail because RunnerFactory.create() doesn't exist\n\n"
            "ACTIONS TAKEN:\n"
            "HEALTH_CHECK: FAILED\n3 failed, 12 passed\n"
            "FILE WRITTEN: app/services/runner/base_runner.py\n"
            "FILE WRITTEN: app/services/runner/factory.py"
        )

        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {"continue": True, "next_message": "Fix the remaining test"}
            result = orch._auto_pilot_decide(
                user_input="fix the test failures",
                final_response=response,
                iteration=0,
            )
        assert result["continue"] is True

    def test_failure_exit_continues_when_bash_ok_coexists(self, base_dir, config):
        """Auto-pilot should continue when failures coexist with successful commands."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        response = (
            "ACTIONS TAKEN:\n"
            "BASH OK: pip install missing-dep\nOUTPUT:\nInstalled successfully\n"
            "HEALTH_CHECK: FAILED\n1 failed, 24 passed"
        )

        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {"continue": True, "next_message": "Fix remaining failure"}
            result = orch._auto_pilot_decide(
                user_input="fix the tests",
                final_response=response,
                iteration=0,
            )
        assert result["continue"] is True

    def test_failure_exit_stops_on_pure_failure_no_progress(self, base_dir, config):
        """Auto-pilot should stop when only failures exist with no successful work."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        response = (
            "ACTIONS TAKEN:\n"
            "BASH FAILED (exit 1): npm test\nOUTPUT:\nAll 15 tests failed\n"
            "HEALTH_CHECK: FAILED\n0 passed, 15 failed"
        )

        result = orch._auto_pilot_decide(
            user_input="run the tests",
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
        """Auto-pilot should stop after AUTO_CHECKPOINT_INTERVAL (normal mode)."""
        from orchestrator import Orchestrator, AUTO_CHECKPOINT_INTERVAL
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # Simulate already at checkpoint interval (normal mode, not /auto)
        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {"continue": True, "next_message": "keep going"}
            result = orch._auto_pilot_decide(
                user_input="build the auth system",
                final_response="Done phase 1",
                iteration=AUTO_CHECKPOINT_INTERVAL,
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


# ── Auto-pilot resume on incomplete work ─────────────────────────────

class TestAutoPilotResume:
    """When auto-pilot stops prematurely (cap, failure, duplicate), it should
    save context so the user can type 'continue' to resume."""

    def test_guard2_user_input_needed_stops(self, base_dir, config):
        """Guard 2 (user-input-needed) should stop when team asks a question."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # Simulate Aria asking the user for input
        response = (
            "The uishift-backend2 project files are not available.\n"
            "Could you confirm: Is the project in a different directory?"
        )
        result = orch._auto_pilot_decide(
            user_input="implement sprint 3",
            final_response=response,
            iteration=0,
        )
        assert result["continue"] is False
        assert result.get("premature") is True
        assert result.get("reason") == "user_input_needed"

    def test_guard2_user_input_case_insensitive(self, base_dir, config):
        """User-input-needed detection should be case-insensitive."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        result = orch._auto_pilot_decide(
            user_input="build auth",
            final_response="PLEASE PROVIDE the database connection string.",
            iteration=0,
        )
        assert result["continue"] is False
        assert result.get("reason") == "user_input_needed"

    def test_guard3_failure_flags_premature(self, base_dir, config):
        """Guard 3 (failure with no progress) should return premature=True."""
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
        assert result.get("premature") is True

    def test_guard3_duplicate_flags_premature(self, base_dir, config):
        """Guard 3 (duplicate detection) should return premature=True."""
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
                final_response="Requirements are ready.",
                iteration=1,
                previous_messages=["Now implement the login page"],
            )
        assert result["continue"] is False
        assert result.get("premature") is True

    def test_haiku_complete_no_premature_flag(self, base_dir, config):
        """When Haiku says 'stop, work is done', premature should NOT be set."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {"continue": False, "next_message": ""}
            result = orch._auto_pilot_decide(
                user_input="build auth",
                final_response="All done. Tests pass. Auth system complete.",
                iteration=1,
            )
        assert result["continue"] is False
        assert result.get("premature") is not True  # None or False

    def test_pending_autopilot_saved_on_cap(self, base_dir, config):
        """When auto-pilot hits the iteration cap, _pending_autopilot should be set."""
        from orchestrator import Orchestrator, AUTO_CHECKPOINT_INTERVAL
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # Haiku always says continue — will hit the cap
        call_count = 0
        def vary_message(*a, **kw):
            nonlocal call_count
            call_count += 1
            return {"continue": True, "next_message": f"Step {call_count}"}

        # Mock process() for the nested calls so we don't trigger the full pipeline
        def mock_process(msg):
            orch.messages.append({"role": "assistant", "content": f"Done: {msg}"})

        with patch.object(orch, "_auto_pilot_decide", side_effect=vary_message), \
             patch.object(orch, "process", side_effect=mock_process):
            orch._run_autopilot_loop("build a big app", "Requirements ready. Next: implement.")

        assert orch._pending_autopilot is not None
        assert orch._pending_autopilot["original_request"] == "build a big app"
        assert orch._pending_autopilot["reason"] == "cap_reached"

    def test_auto_mode_continues_past_checkpoint(self, base_dir, config):
        """In /auto mode, auto-pilot should auto-reset at checkpoints and run past AUTO_CHECKPOINT_INTERVAL."""
        from orchestrator import Orchestrator, AUTO_CHECKPOINT_INTERVAL
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)
        orch._turn_auto = True  # /auto mode

        call_count = 0
        target_iterations = AUTO_CHECKPOINT_INTERVAL + 2  # Run past one checkpoint

        def mock_decide(user_input, final_response, iteration=0, previous_messages=None):
            nonlocal call_count
            call_count += 1
            if call_count <= target_iterations:
                return {"continue": True, "next_message": f"Step {call_count}"}
            return {"continue": False, "next_message": ""}

        def mock_process(msg):
            orch.messages.append({"role": "assistant", "content": f"Done: {msg}"})

        with patch.object(orch, "_auto_pilot_decide", side_effect=mock_decide), \
             patch.object(orch, "process", side_effect=mock_process):
            orch._run_autopilot_loop("build a big app", "Requirements ready.")

        # Should have run past the checkpoint interval
        assert call_count == target_iterations + 1  # +1 for the final "no more work" call
        # Should be complete (not cap_reached) since Haiku said stop
        assert orch._pending_autopilot is None

    def test_normal_mode_pauses_at_checkpoint(self, base_dir, config):
        """In normal mode (no /auto), auto-pilot should pause at AUTO_CHECKPOINT_INTERVAL."""
        from orchestrator import Orchestrator, AUTO_CHECKPOINT_INTERVAL
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)
        orch._turn_auto = False  # normal mode

        call_count = 0

        def mock_decide(user_input, final_response, iteration=0, previous_messages=None):
            nonlocal call_count
            call_count += 1
            return {"continue": True, "next_message": f"Step {call_count}"}

        def mock_process(msg):
            orch.messages.append({"role": "assistant", "content": f"Done: {msg}"})

        with patch.object(orch, "_auto_pilot_decide", side_effect=mock_decide), \
             patch.object(orch, "process", side_effect=mock_process):
            orch._run_autopilot_loop("build a big app", "Requirements ready.")

        # Should pause at exactly the checkpoint interval
        assert call_count == AUTO_CHECKPOINT_INTERVAL
        assert orch._pending_autopilot is not None
        assert orch._pending_autopilot["reason"] == "cap_reached"

    def test_pending_autopilot_saved_on_failure(self, base_dir, config):
        """When Guard 2 stops autopilot (failure, no progress), _pending_autopilot should be set."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # First iteration succeeds, second hits a failure with no progress
        call_count = 0
        def mock_decide(user_input, final_response, iteration=0, previous_messages=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"continue": True, "next_message": "Run the tests"}
            # Second call: Guard 2 triggers (failure response, no progress markers)
            return {"continue": False, "premature": True, "reason": "failure_no_progress"}

        # Mock process() for the nested call so we don't trigger the full pipeline
        def mock_process(msg):
            orch.messages.append({"role": "assistant", "content": "BASH FAILED (exit 1): npm test"})

        with patch.object(orch, "_auto_pilot_decide", side_effect=mock_decide), \
             patch.object(orch, "process", side_effect=mock_process):
            orch._run_autopilot_loop("build auth", "Code written. ACTIONS TAKEN:\nFILE WRITTEN: auth.py")

        assert orch._pending_autopilot is not None
        assert orch._pending_autopilot["reason"] == "failure_no_progress"

    def test_pending_autopilot_cleared_on_complete(self, base_dir, config):
        """When Haiku says work is complete, _pending_autopilot should be None."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        with patch("orchestrator.call_claude_json") as mock_json:
            mock_json.return_value = {"continue": False, "next_message": ""}
            orch._run_autopilot_loop("build auth", "All done. Tests pass.")

        assert orch._pending_autopilot is None

    def test_continue_resumes_autopilot(self, base_dir, config):
        """Typing 'continue' with pending context should resume auto-pilot."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # Set up pending autopilot context (simulating a previous premature stop)
        orch._pending_autopilot = {
            "original_request": "build the auth system",
            "last_context": "Phase 1 done. Still need tests.",
            "reason": "cap_reached",
        }

        # Mock the autopilot loop to verify it gets called with the right args
        with patch.object(orch, "_run_autopilot_loop") as mock_loop:
            orch.process("continue")

        mock_loop.assert_called_once_with(
            "build the auth system",
            "Phase 1 done. Still need tests.",
        )
        # Pending should be cleared before the call
        # (it will be re-set or cleared by the loop itself)

    def test_continue_variants_all_work(self, base_dir, config):
        """Various continue phrases should all resume auto-pilot."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        for phrase in ["continue", "/continue", "go", "keep going", "resume"]:
            db = DBManager(base_dir / "db" / "conversations.db")
            display = Display()
            orch = Orchestrator("test", base_dir, db, display, config=config)
            orch._pending_autopilot = {
                "original_request": "build it",
                "last_context": "Halfway done.",
                "reason": "cap_reached",
            }
            with patch.object(orch, "_run_autopilot_loop") as mock_loop:
                orch.process(phrase)
            mock_loop.assert_called_once(), f"'{phrase}' should resume autopilot"

    def test_continue_without_pending_routes_normally(self, base_dir, config):
        """Typing 'continue' with no pending context should NOT trigger resume
        and should fall through to normal routing."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # No pending autopilot
        assert orch._pending_autopilot is None

        # _run_autopilot_loop should NOT be called (no pending context)
        # Normal routing should proceed instead
        orch.is_new_project = False  # prevent scaffold from prompting
        with patch.object(orch, "_run_autopilot_loop") as mock_loop, \
             patch.object(orch, "_scaffold_project"), \
             patch("orchestrator.call_claude_json") as mock_json, \
             patch("orchestrator.call_claude") as mock_claude:
            mock_json.return_value = {
                "phases": [{"name": "General", "agents": ["pm"],
                            "tasks": {"pm": "respond"}}]
            }
            mock_claude.return_value = "How can I help?"
            orch.process("continue")
        mock_loop.assert_not_called()

    def test_interrupted_autopilot_no_pending(self, base_dir, config):
        """Ctrl+C during autopilot should NOT save pending context."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # First call raises KeyboardInterrupt (user pressed Ctrl+C)
        with patch("orchestrator.call_claude_json", side_effect=KeyboardInterrupt):
            orch._run_autopilot_loop("build auth", "Code written.")

        # User interrupted — don't nag them with "type continue"
        assert orch._pending_autopilot is None

    def test_inner_process_interrupt_stops_loop(self, base_dir, config):
        """If the inner process() catches KeyboardInterrupt and sets _interrupted,
        the autopilot loop should stop on the NEXT iteration — no extra Ctrl+C needed."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator("test", base_dir, db, display, config=config)

        # Mock _auto_pilot_decide to always continue
        call_count = 0
        def mock_decide(user_input, final_response, iteration=0, previous_messages=None):
            nonlocal call_count
            call_count += 1
            return {"continue": True, "next_message": f"Step {call_count}"}

        # Mock process(): simulate inner process() catching Ctrl+C on iteration 1
        # (sets _interrupted=True, returns normally — swallows the interrupt)
        def mock_process(msg):
            orch._interrupted = True  # inner process() caught Ctrl+C
            orch.messages.append({"role": "assistant", "content": "Interrupted."})

        with patch.object(orch, "_auto_pilot_decide", side_effect=mock_decide), \
             patch.object(orch, "process", side_effect=mock_process):
            orch._run_autopilot_loop("build auth", "Code written.")

        # Should have stopped after 1 iteration, not continued to AUTO_CHECKPOINT_INTERVAL
        assert call_count == 1
        # Should NOT save pending (user interrupted)
        assert orch._pending_autopilot is None


class TestBashSubprocessTimeout:
    """Bash command execution should have a timeout to prevent hanging."""

    def test_subprocess_run_has_timeout(self):
        """The subprocess.run call in prompt_and_execute should include a timeout."""
        import inspect
        from utils.action_executor import prompt_and_execute

        source = inspect.getsource(prompt_and_execute)
        # The subprocess.run call must include timeout parameter
        assert "timeout=" in source, (
            "subprocess.run in prompt_and_execute must have a timeout parameter "
            "to prevent hanging on Windows"
        )

    def test_timeout_expired_produces_failure_outcome(self):
        """When a command times out, it should produce a BASH FAILED outcome."""
        import subprocess
        from utils.action_executor import prompt_and_execute, Action

        action = Action(
            kind="bash",
            content="ping -n 300 127.0.0.1",  # would take 5 min without timeout
            agent_name="Sam",
            label="long-running command",
        )

        with patch("utils.action_executor.subprocess.run",
                    side_effect=subprocess.TimeoutExpired("cmd", 120)):
            outcomes = prompt_and_execute(
                [action],
                Path("."),
                auto_mode=True,
            )

        assert len(outcomes) == 1
        assert "BASH FAILED" in outcomes[0]
        assert "timed out" in outcomes[0].lower()


# ── Project sandbox: path escape prevention ──────────────────────────

class TestProjectSandbox:
    """Agents should not escape the project directory."""

    def test_file_write_blocks_path_traversal(self, tmp_path):
        """File writes with ../ that escape the project dir should be blocked."""
        from utils.action_executor import prompt_and_execute, Action

        project = tmp_path / "myproject"
        project.mkdir()

        action = Action(
            kind="file",
            content="malicious content",
            agent_name="Sam",
            label="../../etc/passwd",
        )

        outcomes = prompt_and_execute([action], project, auto_mode=True)
        assert len(outcomes) == 1
        assert "BLOCKED" in outcomes[0]
        # The file should NOT have been written
        assert not (tmp_path / "etc" / "passwd").exists()

    def test_file_write_allows_nested_inside_project(self, tmp_path):
        """File writes within the project dir (including subdirs) should be allowed."""
        from utils.action_executor import prompt_and_execute, Action

        project = tmp_path / "myproject"
        project.mkdir()

        action = Action(
            kind="file",
            content="console.log('hello')",
            agent_name="Sam",
            label="src/app.js",
        )

        outcomes = prompt_and_execute([action], project, auto_mode=True)
        assert len(outcomes) == 1
        assert "FILE WRITTEN" in outcomes[0]
        assert (project / "src" / "app.js").exists()

    def test_bash_blocks_scanning_outside_project(self):
        """Bash commands that scan outside the project directory should be blocked."""
        from utils.action_executor import is_path_escape_bash

        # Scanning user home recursively
        assert is_path_escape_bash(
            r'Get-ChildItem -Path C:\Users\knandu -Recurse -Filter *.py',
            Path(r"C:\Users\knandu\projects\myapp"),
        )
        # Scanning a sibling directory
        assert is_path_escape_bash(
            r'Get-ChildItem -Path C:\Users\knandu\Documents -Recurse',
            Path(r"C:\Users\knandu\projects\myapp"),
        )
        # Scanning parent with dir /s
        assert is_path_escape_bash(
            r"dir /s C:\Users\knandu\*.py",
            Path(r"C:\Users\knandu\projects\myapp"),
        )

    def test_bash_allows_commands_inside_project(self):
        """Bash commands working within the project should NOT be blocked."""
        from utils.action_executor import is_path_escape_bash

        project = Path(r"C:\Users\knandu\projects\myapp")

        # Relative paths — always fine
        assert not is_path_escape_bash("findstr /n foo src\\app.py", project)
        assert not is_path_escape_bash("pytest tests/ -v", project)
        assert not is_path_escape_bash("dir /s *.py", project)

        # Absolute path inside the project — fine
        assert not is_path_escape_bash(
            r'Get-ChildItem -Path C:\Users\knandu\projects\myapp\src -Recurse',
            project,
        )

    def test_bash_blocks_absolute_paths_outside_project(self):
        """Bash commands referencing absolute paths outside the project should be blocked."""
        from utils.action_executor import is_path_escape_bash

        project = Path(r"C:\Users\knandu\projects\myapp")

        # Reading a file outside the project
        assert is_path_escape_bash(
            r"type C:\Users\knandu\Documents\secrets.txt",
            project,
        )
        # PowerShell scanning outside
        assert is_path_escape_bash(
            r'powershell -Command "Get-ChildItem C:\Users\knandu -Recurse"',
            project,
        )

    def test_sandbox_instruction_in_agent_prompt(self):
        """Agent EXEC instructions should include sandbox restriction."""
        from agents.agent import _EXEC_INSTRUCTIONS

        assert "project directory" in _EXEC_INSTRUCTIONS.lower() or \
               "sandbox" in _EXEC_INSTRUCTIONS.lower() or \
               "outside" in _EXEC_INSTRUCTIONS.lower()


# ── Rich markup safety — raw subprocess output must not crash ───────

class TestRichMarkupSafety:
    """Subprocess output containing bracket patterns like [/raise/not-found]
    must not crash console.print() via Rich's markup parser."""

    def test_health_check_output_with_rich_brackets_no_crash(self, tmp_path):
        """Health-check snippet with Rich-like closing tags should not raise MarkupError."""
        from utils.action_executor import Action, prompt_and_execute

        # Output that mimics pytest failures containing bracket patterns
        poison_output = (
            "FAILED tests/test_example.py::test_it - "
            "raise ValueError('[/raise/not-found]')\n"
            "short test summary info\n"
            "1 failed in 0.42s"
        )
        action = Action(kind="file", label="src/app.py",
                        content="print('hello')", agent_name="Sam")
        project = tmp_path / "proj"
        project.mkdir()

        # Health check returns failure with poisoned output
        with patch("utils.action_executor.run_health_check",
                   return_value=(False, poison_output)):
            outcomes = prompt_and_execute(
                [action], project,
                tdd_health_cmd="pytest",
                auto_mode=True,
            )

        # Should NOT crash — outcome must contain the snippet
        assert any("HEALTH_CHECK: FAILED" in o for o in outcomes)
        assert any("[/raise/not-found]" in o for o in outcomes)

    def test_bash_output_with_rich_brackets_no_crash(self, tmp_path):
        """Bash command output containing Rich-like tags should not raise MarkupError."""
        from utils.action_executor import Action, prompt_and_execute

        poison_output = (
            "ERROR: [bold red]not a real tag[/bold red]\n"
            "[/some/fake/closing] bracket noise\n"
            "done"
        )
        action = Action(kind="bash", label="pytest tests/",
                        content="pytest tests/", agent_name="Sam")
        project = tmp_path / "proj"
        project.mkdir()

        fake_result = MagicMock()
        fake_result.stdout = poison_output
        fake_result.stderr = ""
        fake_result.returncode = 0

        with patch("utils.action_executor.subprocess.run", return_value=fake_result), \
             patch("utils.action_executor.is_path_escape_bash", return_value=False):
            outcomes = prompt_and_execute(
                [action], project,
                auto_mode=True,
            )

        # Should NOT crash
        assert any("BASH OK" in o for o in outcomes)


# ── Failure logging from orchestrator outcomes ──────────────────────

class TestFailureLoggingFromOutcomes:
    """Orchestrator should parse outcome strings and log failures to SQLite."""

    def _make_orchestrator(self, base_dir, config):
        from utils.db_manager import DBManager
        from utils.display import Display
        from orchestrator import Orchestrator

        db = DBManager(base_dir / "db" / "conversations.db")
        orch = Orchestrator(
            project_name="test-proj",
            base_dir=base_dir,
            db=db,
            display=Display(),
            config=config,
        )
        orch.is_new_project = False
        return orch

    def test_bash_failed_outcome_logged(self, base_dir, config):
        """BASH FAILED outcomes should be logged with category 'bash_error'."""
        orch = self._make_orchestrator(base_dir, config)
        outcomes = [
            "BASH FAILED (exit 1): pytest tests/\nOUTPUT:\nFAILED test_example.py"
        ]
        orch._log_failures_from_outcomes(outcomes, agent_name="Sam", user_request="build login")
        rows = orch.db.get_failures("test-proj")
        assert len(rows) == 1
        assert rows[0]["category"] == "bash_error"
        assert rows[0]["agent_name"] == "Sam"
        assert "pytest tests/" in rows[0]["command_or_file"]

    def test_bash_timeout_outcome_logged(self, base_dir, config):
        """BASH FAILED (timed out) outcomes should be logged with category 'bash_timeout'."""
        orch = self._make_orchestrator(base_dir, config)
        outcomes = ["BASH FAILED (timed out after 120s): npm run build"]
        orch._log_failures_from_outcomes(outcomes, agent_name="Sam", user_request="deploy")
        rows = orch.db.get_failures("test-proj")
        assert len(rows) == 1
        assert rows[0]["category"] == "bash_timeout"

    def test_bash_blocked_outcome_logged(self, base_dir, config):
        """BASH BLOCKED outcomes should be logged with category 'bash_blocked'."""
        orch = self._make_orchestrator(base_dir, config)
        outcomes = [
            "BASH BLOCKED: Get-ChildItem C:\\Users — references paths outside the project directory"
        ]
        orch._log_failures_from_outcomes(outcomes, agent_name="Sam", user_request="scan files")
        rows = orch.db.get_failures("test-proj")
        assert len(rows) == 1
        assert rows[0]["category"] == "bash_blocked"

    def test_health_check_failed_outcome_logged(self, base_dir, config):
        """HEALTH_CHECK: FAILED outcomes should be logged with category 'health_check_fail'."""
        orch = self._make_orchestrator(base_dir, config)
        outcomes = ["HEALTH_CHECK: FAILED\nImportError: cannot import 'app'"]
        orch._log_failures_from_outcomes(outcomes, agent_name="Sam", user_request="fix imports")
        rows = orch.db.get_failures("test-proj")
        assert len(rows) == 1
        assert rows[0]["category"] == "health_check_fail"

    def test_file_blocked_outcome_logged(self, base_dir, config):
        """FILE BLOCKED outcomes should be logged with category 'file_blocked'."""
        orch = self._make_orchestrator(base_dir, config)
        outcomes = ["FILE BLOCKED: ../../etc/passwd — escapes project directory"]
        orch._log_failures_from_outcomes(outcomes, agent_name="Sam", user_request="write config")
        rows = orch.db.get_failures("test-proj")
        assert len(rows) == 1
        assert rows[0]["category"] == "file_blocked"

    def test_success_outcomes_not_logged(self, base_dir, config):
        """BASH OK, FILE WRITTEN, HEALTH_CHECK: PASSED should NOT be logged."""
        orch = self._make_orchestrator(base_dir, config)
        outcomes = [
            "BASH OK: pytest tests/",
            "FILE WRITTEN: src/app.py",
            "HEALTH_CHECK: PASSED",
            "FILE SKIPPED: README.md",
            "BASH SKIPPED: npm install",
        ]
        orch._log_failures_from_outcomes(outcomes, agent_name="Sam", user_request="build app")
        rows = orch.db.get_failures("test-proj")
        assert len(rows) == 0

    def test_autopilot_premature_stop_logged(self, base_dir, config):
        """Autopilot premature stops should be logged with category 'autopilot_<reason>'."""
        orch = self._make_orchestrator(base_dir, config)
        orch._log_autopilot_stop(reason="cap_reached", user_request="build full app")
        rows = orch.db.get_failures("test-proj")
        assert len(rows) == 1
        assert rows[0]["category"] == "autopilot_cap_reached"
        assert rows[0]["agent_name"] == "autopilot"

    def test_multiple_failures_in_one_batch(self, base_dir, config):
        """Multiple failures in one outcome batch should all be logged."""
        orch = self._make_orchestrator(base_dir, config)
        outcomes = [
            "BASH FAILED (exit 1): cmd1\nOUTPUT:\nerr1",
            "BASH OK: cmd2",
            "HEALTH_CHECK: FAILED\nsome error",
            "FILE BLOCKED: ../../bad — escapes project directory",
        ]
        orch._log_failures_from_outcomes(outcomes, agent_name="Sam", user_request="do stuff")
        rows = orch.db.get_failures("test-proj")
        assert len(rows) == 3
        categories = {r["category"] for r in rows}
        assert categories == {"bash_error", "health_check_fail", "file_blocked"}


# ── Auto-expand truncated docs ──────────────────────────────────────

class TestDocAutoExpand:
    """When a doc is truncated in an agent's system prompt, the system should
    auto-expand it if the task references that doc — zero extra LLM calls."""

    def test_truncation_marker_is_parseable(self, base_dir):
        """load_project_docs should produce [DOC_TRUNCATED:filename:size] markers."""
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "proj")
        docs_dir = base_dir / "projects" / "proj" / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "architecture.md").write_text("A" * 5000, encoding="utf-8")

        result = mm.load_project_docs(max_docs=1, max_chars_each=1500)
        assert "[DOC_TRUNCATED:architecture.md:5000" in result
        assert "READ_FILE:docs/architecture.md" in result

    def test_short_doc_no_truncation_marker(self, base_dir):
        """Docs shorter than max_chars_each should NOT have a truncation marker."""
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "proj")
        docs_dir = base_dir / "projects" / "proj" / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "notes.md").write_text("Short note", encoding="utf-8")

        result = mm.load_project_docs(max_docs=1, max_chars_each=1500)
        assert "DOC_TRUNCATED" not in result
        assert "Short note" in result

    def test_expand_replaces_truncated_when_task_matches(self):
        """Auto-expand should replace truncated block with full content for relevant tasks."""
        from agents.agent import _expand_truncated_docs

        prompt = (
            "Preamble\n\n"
            "### architecture.md\n"
            "# Architecture\nSection 1 content only.\n\n"
            "[DOC_TRUNCATED:architecture.md:5000 — use READ_FILE:docs/architecture.md for full content]\n\n"
            "Other sections follow"
        )
        full_content = "# Architecture\nSection 1 content only.\n## Section 2\nFull deep content."

        reader = lambda fname: full_content if fname == "architecture.md" else None
        result = _expand_truncated_docs(prompt, "review the architecture design", reader)

        assert "DOC_TRUNCATED" not in result
        assert "Full deep content" in result
        assert "Other sections follow" in result  # rest preserved
        assert "Preamble" in result  # preamble preserved

    def test_expand_skips_when_task_unrelated(self):
        """Auto-expand should NOT expand docs unrelated to the task."""
        from agents.agent import _expand_truncated_docs

        prompt = (
            "### architecture.md\n"
            "Truncated content.\n\n"
            "[DOC_TRUNCATED:architecture.md:5000 — use READ_FILE:docs/architecture.md for full content]"
        )
        reader = lambda fname: "FULL CONTENT"

        result = _expand_truncated_docs(prompt, "fix the login button CSS", reader)
        assert "DOC_TRUNCATED" in result  # NOT expanded
        assert "FULL CONTENT" not in result

    def test_expand_no_markers_returns_unchanged(self):
        """Prompt without truncation markers should be returned unchanged."""
        from agents.agent import _expand_truncated_docs

        prompt = "### notes.md\nFull short doc.\n\nOther stuff"
        reader = lambda fname: "anything"
        result = _expand_truncated_docs(prompt, "any task", reader)
        assert result == prompt

    def test_expand_force_all_ignores_task_relevance(self):
        """force_all=True should expand ALL truncated docs regardless of task."""
        from agents.agent import _expand_truncated_docs

        prompt = (
            "### architecture.md\n"
            "Truncated.\n\n"
            "[DOC_TRUNCATED:architecture.md:5000 — use READ_FILE:docs/architecture.md for full content]\n\n"
            "### sprint-plan.md\n"
            "Also truncated.\n\n"
            "[DOC_TRUNCATED:sprint-plan.md:3000 — use READ_FILE:docs/sprint-plan.md for full content]"
        )
        docs = {
            "architecture.md": "Full architecture content",
            "sprint-plan.md": "Full sprint plan content",
        }
        reader = lambda fname: docs.get(fname)

        result = _expand_truncated_docs(
            prompt, "unrelated task about CSS", reader, force_all=True,
        )
        assert "DOC_TRUNCATED" not in result
        assert "Full architecture content" in result
        assert "Full sprint plan content" in result

    def test_expand_multi_word_doc_name_matches(self):
        """Docs with hyphenated names like sprint-plan.md should match task words."""
        from agents.agent import _expand_truncated_docs

        prompt = (
            "### sprint-plan.md\n"
            "Truncated.\n\n"
            "[DOC_TRUNCATED:sprint-plan.md:4000 — use READ_FILE:docs/sprint-plan.md for full content]"
        )
        reader = lambda fname: "Full sprint plan" if fname == "sprint-plan.md" else None

        result = _expand_truncated_docs(prompt, "what's in the sprint plan?", reader)
        assert "DOC_TRUNCATED" not in result
        assert "Full sprint plan" in result


# ── parse_actions: EXEC block extraction ───────────────────────────────

class TestParseActionsCodeFences:
    """Ensure EXEC:file blocks with internal triple-backtick code fences
    are captured in full — not silently truncated at the first ```."""

    def test_simple_file_no_internal_fences(self):
        """Basic case — file content with no internal code fences."""
        from utils.action_executor import parse_actions

        text = (
            "Here's the file:\n"
            "EXEC:file:hello.py\n"
            "```python\n"
            "print('hello')\n"
            "```\n"
        )
        actions = parse_actions(text, "sam")
        assert len(actions) == 1
        assert actions[0].kind == "file"
        assert actions[0].label == "hello.py"
        assert "print('hello')" in actions[0].content

    def test_file_with_internal_code_fences(self):
        """File content containing markdown code blocks must not be truncated."""
        from utils.action_executor import parse_actions

        md_content = (
            "# Architecture\n"
            "\n"
            "## Folder Structure\n"
            "\n"
            "```\n"
            "backend/\n"
            "├── main.py\n"
            "└── models.py\n"
            "```\n"
            "\n"
            "## Config\n"
            "\n"
            "```\n"
            "DATABASE_URL=sqlite:///./db.sqlite\n"
            "```\n"
            "\n"
            "## Done"
        )
        text = (
            "EXEC:file:docs/architecture.md\n"
            "```\n"
            f"{md_content}\n"
            "```\n"
        )
        actions = parse_actions(text, "jordan")
        assert len(actions) == 1
        assert actions[0].label == "docs/architecture.md"
        # The critical assertions — content AFTER the internal fences must survive
        assert "## Config" in actions[0].content
        assert "DATABASE_URL" in actions[0].content
        assert "## Done" in actions[0].content

    def test_file_with_language_tagged_fences(self):
        """Internal fences with language tags (```python, ```json) must not truncate."""
        from utils.action_executor import parse_actions

        text = (
            "EXEC:file:README.md\n"
            "```\n"
            "# README\n"
            "\n"
            "```python\n"
            "import os\n"
            "```\n"
            "\n"
            "```json\n"
            '{"key": "value"}\n'
            "```\n"
            "\n"
            "End of README\n"
            "```\n"
        )
        actions = parse_actions(text, "sam")
        assert len(actions) == 1
        assert "End of README" in actions[0].content
        assert '{"key": "value"}' in actions[0].content

    def test_multiple_exec_blocks_with_fences(self):
        """Two EXEC:file blocks — each containing internal code fences."""
        from utils.action_executor import parse_actions

        text = (
            "EXEC:file:docs/arch.md\n"
            "```\n"
            "# Arch\n"
            "```\n"
            "folder/\n"
            "```\n"
            "End arch\n"
            "```\n"
            "\n"
            "EXEC:file:docs/api.md\n"
            "```\n"
            "# API\n"
            "```json\n"
            '{"endpoint": "/v1"}\n'
            "```\n"
            "End API\n"
            "```\n"
        )
        actions = parse_actions(text, "jordan")
        assert len(actions) == 2
        assert "End arch" in actions[0].content
        assert "End API" in actions[1].content
        assert '{"endpoint": "/v1"}' in actions[1].content

    def test_bash_simple(self):
        """Basic EXEC:bash extraction still works."""
        from utils.action_executor import parse_actions

        text = (
            "EXEC:bash\n"
            "```\n"
            "pytest tests/\n"
            "```\n"
        )
        actions = parse_actions(text, "sam")
        assert len(actions) == 1
        assert actions[0].kind == "bash"
        assert "pytest" in actions[0].content

    def test_mixed_file_and_bash(self):
        """EXEC:file with fences followed by EXEC:bash."""
        from utils.action_executor import parse_actions

        text = (
            "EXEC:file:docs/setup.md\n"
            "```\n"
            "# Setup\n"
            "```bash\n"
            "pip install -r requirements.txt\n"
            "```\n"
            "Done\n"
            "```\n"
            "\n"
            "EXEC:bash\n"
            "```\n"
            "pip install -r requirements.txt\n"
            "```\n"
        )
        actions = parse_actions(text, "sam")
        assert len(actions) == 2
        assert actions[0].kind == "file"
        assert "Done" in actions[0].content
        assert actions[1].kind == "bash"
        assert "pip install" in actions[1].content

    def test_path_strips_trailing_stars(self):
        """Bold markdown leaking into EXEC:file path (e.g. 'file.md**') must be cleaned."""
        from utils.action_executor import parse_actions

        text = (
            "EXEC:file:docs/roadmap.md**\n"
            "```\n"
            "# Roadmap\n"
            "```\n"
        )
        actions = parse_actions(text, "alex")
        assert len(actions) == 1
        assert actions[0].label == "docs/roadmap.md"
        assert "*" not in actions[0].label

    def test_path_strips_backticks(self):
        """Backtick-wrapped paths like `path/to/file.py` must be cleaned."""
        from utils.action_executor import parse_actions

        text = (
            "EXEC:file:`src/main.py`\n"
            "```python\n"
            "print('hi')\n"
            "```\n"
        )
        actions = parse_actions(text, "sam")
        assert len(actions) == 1
        assert actions[0].label == "src/main.py"

    def test_path_strips_quotes(self):
        """Quoted paths must be cleaned."""
        from utils.action_executor import parse_actions

        text = (
            'EXEC:file:"docs/notes.md"\n'
            "```\n"
            "Notes here\n"
            "```\n"
        )
        actions = parse_actions(text, "morgan")
        assert len(actions) == 1
        assert actions[0].label == "docs/notes.md"


# ── Project dir auto-scan ──────────────────────────────────────────────

class TestProjectDirAutoScan:
    """When no /loaded codebase exists, the project's own directory should be
    auto-scanned so agents can see their files."""

    def test_auto_scan_sets_loaded_path(self, base_dir, config):
        """process() should set loaded_path to the project dir when it has files."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        display = MagicMock()
        orch = Orchestrator(
            project_name="scan-test",
            base_dir=base_dir,
            db=db,
            display=display,
            config=config,
        )
        # Create a file in the project dir
        project_dir = base_dir / "projects" / "scan-test"
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "main.py").write_text("print('hi')", encoding="utf-8")

        assert orch.loaded_path is None
        assert orch.codebase_context == {}

        # Simulate the auto-scan portion of process()
        if not orch.loaded_path:
            pd = base_dir / "projects" / "scan-test"
            if pd.exists() and any(pd.iterdir()):
                orch.loaded_path = pd
                orch.codebase_context = orch._scan_codebase(pd)

        assert orch.loaded_path == project_dir
        assert "structure_tree" in orch.codebase_context
        assert orch.codebase_context["total_files"] >= 1
        db.close()

    def test_auto_scan_skipped_when_loaded(self, base_dir, config):
        """If /load already set loaded_path, auto-scan should not override it."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        display = MagicMock()
        orch = Orchestrator(
            project_name="scan-test2",
            base_dir=base_dir,
            db=db,
            display=display,
            config=config,
        )
        # Simulate an existing /load
        ext_path = base_dir / "external_codebase"
        ext_path.mkdir(parents=True, exist_ok=True)
        orch.loaded_path = ext_path

        # Create files in project dir
        project_dir = base_dir / "projects" / "scan-test2"
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "app.py").write_text("pass", encoding="utf-8")

        # Auto-scan should be skipped
        if not orch.loaded_path:
            pd = base_dir / "projects" / "scan-test2"
            if pd.exists() and any(pd.iterdir()):
                orch.loaded_path = pd

        assert orch.loaded_path == ext_path  # NOT overwritten
        db.close()

    def test_scan_ignore_filters_venv(self, base_dir, config):
        """_scan_codebase should ignore venv and node_modules directories."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        display = MagicMock()
        orch = Orchestrator(
            project_name="scan-test3",
            base_dir=base_dir,
            db=db,
            display=display,
            config=config,
        )
        project_dir = base_dir / "projects" / "scan-test3"
        project_dir.mkdir(parents=True, exist_ok=True)
        # Real file
        (project_dir / "main.py").write_text("pass", encoding="utf-8")
        # Venv file (should be ignored)
        venv_dir = project_dir / "venv" / "Lib"
        venv_dir.mkdir(parents=True, exist_ok=True)
        (venv_dir / "pip.py").write_text("pip stuff", encoding="utf-8")
        # node_modules file (should be ignored)
        nm_dir = project_dir / "node_modules" / "react"
        nm_dir.mkdir(parents=True, exist_ok=True)
        (nm_dir / "index.js").write_text("module.exports", encoding="utf-8")

        ctx = orch._scan_codebase(project_dir)
        tree = ctx["structure_tree"]
        assert "main.py" in tree
        assert "venv" not in tree
        assert "node_modules" not in tree
        # Total files should only count the real file
        assert ctx["total_files"] == 1
        db.close()


class TestSkillConsolidation:
    """Auto-consolidation of bloated auto-learned skill files."""

    def _make_orch(self, base_dir, config):
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        return Orchestrator("test", base_dir, db, display, config=config)

    def _write_big_skill_file(self, base_dir, role, lesson_count=40):
        """Write a skill file that exceeds the consolidation threshold."""
        skills_dir = base_dir / "memory" / "skills" / role
        skills_dir.mkdir(parents=True, exist_ok=True)
        path = skills_dir / "auto-learned.md"
        lines = [f"# Auto-Learned Lessons — {role}\n\n"]
        for i in range(lesson_count):
            lines.append(f"### [2026-05-{20 + i % 10:02d} 10:00] via bash-failure\n")
            lines.append(f"Always verify imports exist before running pytest (lesson {i}).\n\n")
        path.write_text("".join(lines), encoding="utf-8")
        return path

    def test_consolidation_triggers_on_large_file(self, base_dir, config):
        """Consolidation should call Haiku when a skill file exceeds the threshold."""
        orch = self._make_orch(base_dir, config)
        path = self._write_big_skill_file(base_dir, "developer", 40)

        original_content = path.read_text(encoding="utf-8")
        consolidated_mock = (
            "# Auto-Learned Lessons — developer\n\n"
            "### [2026-05-29 10:00] via bash-failure\n"
            "Always verify imports exist before running pytest.\n"
        )

        with patch("orchestrator.call_claude", return_value=consolidated_mock):
            orch._consolidate_skills_if_needed()

        # Should have written consolidated content
        new_content = path.read_text(encoding="utf-8")
        assert len(new_content) < len(original_content)
        # Should have created a plain .bak (cooldown marker)
        backup = path.with_suffix(".md.bak")
        assert backup.exists()
        assert backup.read_text(encoding="utf-8") == original_content
        # Should have created a versioned .YYYYMMDD.bak (permanent archive)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d")
        versioned = path.with_suffix(f".{ts}.bak")
        assert versioned.exists()
        assert versioned.read_text(encoding="utf-8") == original_content

    def test_consolidation_skips_small_files(self, base_dir, config):
        """Consolidation should not run on files below the threshold."""
        orch = self._make_orch(base_dir, config)
        # Write a small file (3 lessons)
        self._write_big_skill_file(base_dir, "developer", 3)

        with patch("orchestrator.call_claude") as mock_claude:
            orch._consolidate_skills_if_needed()
        # Haiku should NOT have been called
        mock_claude.assert_not_called()

    def test_consolidation_runs_once_per_session(self, base_dir, config):
        """Consolidation should only run on the first process() call."""
        orch = self._make_orch(base_dir, config)
        self._write_big_skill_file(base_dir, "developer", 40)

        consolidated_mock = (
            "# Auto-Learned Lessons — developer\n\n"
            "### [2026-05-29 10:00] via bash-failure\n"
            "Always verify imports exist before running pytest.\n"
        )

        with patch("orchestrator.call_claude", return_value=consolidated_mock):
            orch._consolidate_skills_if_needed()

        assert orch._skills_consolidated is True

        # Second call should be a no-op
        with patch("orchestrator.call_claude") as mock_claude:
            orch._consolidate_skills_if_needed()
        mock_claude.assert_not_called()

    def test_consolidation_handles_haiku_failure(self, base_dir, config):
        """If Haiku fails, consolidation should skip gracefully."""
        orch = self._make_orch(base_dir, config)
        path = self._write_big_skill_file(base_dir, "developer", 40)
        original_content = path.read_text(encoding="utf-8")

        with patch("orchestrator.call_claude", side_effect=Exception("API error")):
            orch._consolidate_skills_if_needed()  # should not raise

        # File should be unchanged
        assert path.read_text(encoding="utf-8") == original_content
        # No backup created
        assert not path.with_suffix(".md.bak").exists()

    def test_consolidation_skips_within_cooldown(self, base_dir, config):
        """Consolidation should skip if a .bak file exists and is recent."""
        import time

        orch = self._make_orch(base_dir, config)
        path = self._write_big_skill_file(base_dir, "developer", 40)

        # Create a recent .bak file (simulates consolidation happened today)
        backup = path.with_suffix(".md.bak")
        backup.write_text("old backup content", encoding="utf-8")

        with patch("orchestrator.call_claude") as mock_claude:
            orch._consolidate_skills_if_needed()

        # Haiku should NOT have been called — cooldown is active
        mock_claude.assert_not_called()

    def test_consolidation_runs_after_cooldown_expires(self, base_dir, config):
        """Consolidation should run if the .bak file is older than the cooldown."""
        import os
        import time

        orch = self._make_orch(base_dir, config)
        path = self._write_big_skill_file(base_dir, "developer", 40)

        # Create an old .bak file (8 days ago)
        backup = path.with_suffix(".md.bak")
        backup.write_text("old backup content", encoding="utf-8")
        old_time = time.time() - (8 * 86400)
        os.utime(backup, (old_time, old_time))

        consolidated_mock = (
            "# Auto-Learned Lessons — developer\n\n"
            "### [2026-05-29 10:00] via bash-failure\n"
            "Always verify imports exist before running pytest.\n"
        )

        with patch("orchestrator.call_claude", return_value=consolidated_mock):
            orch._consolidate_skills_if_needed()

        # Should have consolidated (backup overwritten with new content)
        new_content = path.read_text(encoding="utf-8")
        assert "lesson 0" not in new_content  # original lessons replaced
