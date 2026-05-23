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


# ── Auto-pilot resume on incomplete work ─────────────────────────────

class TestAutoPilotResume:
    """When auto-pilot stops prematurely (cap, failure, duplicate), it should
    save context so the user can type 'continue' to resume."""

    def test_guard2_failure_flags_premature(self, base_dir, config):
        """Guard 2 (failure with no progress) should return premature=True."""
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
        from orchestrator import Orchestrator, MAX_AUTO_ITERATIONS
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

        # Should have stopped after 1 iteration, not continued to MAX_AUTO_ITERATIONS
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
