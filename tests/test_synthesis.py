"""Tests for synthesis prompt token capping."""
from orchestrator import Orchestrator


class TestSynthesisResponseCap:
    def test_has_synthesis_per_agent_cap_constant(self):
        assert hasattr(Orchestrator, "_SYNTHESIS_PER_AGENT_CAP")
        assert Orchestrator._SYNTHESIS_PER_AGENT_CAP == 1600

    def test_long_agent_response_is_capped(self, base_dir, config):
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator(
            project_name="_general",
            base_dir=base_dir,
            db=db,
            display=display,
            config=config,
        )

        long_response = "A" * 5000
        agent_responses = {"developer": long_response}
        prompt = orch._synthesis_prompt("build a login page", agent_responses)

        # The prompt should NOT contain the full 5000-char response
        # It should be truncated to the cap
        assert long_response not in prompt
        # But it should contain a truncated version
        assert "[truncated]" in prompt or len(prompt) < len(long_response) + 500
        db.close()

    def test_short_response_not_truncated(self, base_dir, config):
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator(
            project_name="_general",
            base_dir=base_dir,
            db=db,
            display=display,
            config=config,
        )

        short_response = "Here is a brief summary of the work."
        agent_responses = {"developer": short_response}
        prompt = orch._synthesis_prompt("build a login page", agent_responses)

        # Short responses should be fully preserved
        assert short_response in prompt
        db.close()

    def test_multiple_agents_all_capped(self, base_dir, config):
        from utils.db_manager import DBManager
        from utils.display import Display

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator(
            project_name="_general",
            base_dir=base_dir,
            db=db,
            display=display,
            config=config,
        )

        agent_responses = {
            "developer": "X" * 5000,
            "lead": "Y" * 5000,
            "pm": "Z" * 5000,
        }
        prompt = orch._synthesis_prompt("plan the architecture", agent_responses)

        # Total prompt should be much less than 3*5000 = 15000
        assert len(prompt) < 8000
        db.close()
