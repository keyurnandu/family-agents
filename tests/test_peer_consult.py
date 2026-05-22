"""Tests for peer consultation allowing bench agents."""
from unittest.mock import patch, MagicMock


class TestPeerConsultBenchAgents:
    def test_bench_agent_not_blocked(self, base_dir, config):
        """A bench agent (devops, researcher, qa) should be consultable via
        _get_peer_input even when not on the active roster."""
        from agents.agent import Agent
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "_general")
        personas = config["agent_personas"]

        # Create a mock orchestrator with devops NOT on active_roster
        # but present in self.agents (as it is in real code)
        mock_orch = MagicMock()
        mock_orch.active_roster = ["pm", "bsa", "developer", "lead"]
        mock_orch.loaded_path = None
        mock_orch.codebase_context = {}
        mock_orch.config = config

        # Create both the calling agent and the bench peer
        devops_agent = Agent(
            role="devops",
            persona=personas.get("devops", {"name": "Taylor"}),
            memory=mm,
            model="sonnet",
            base_dir=base_dir,
            orchestrator=mock_orch,
        )
        mock_orch.agents = {"devops": devops_agent}

        developer = Agent(
            role="developer",
            persona=personas.get("developer", {"name": "Sam"}),
            memory=mm,
            model="sonnet",
            base_dir=base_dir,
            orchestrator=mock_orch,
        )

        # Mock call_claude to avoid real LLM call
        with patch("agents.agent.call_claude", return_value="Use Docker Compose for local dev."):
            result = developer._get_peer_input("devops", "What deployment strategy?")

        # Should NOT return the "not on the active team" message
        assert "not on the active team" not in result
        assert "Docker" in result

    def test_completely_unknown_role_rejected(self, base_dir, config):
        """A role that doesn't exist in self.agents should still be rejected."""
        from agents.agent import Agent
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "_general")
        personas = config["agent_personas"]

        mock_orch = MagicMock()
        mock_orch.active_roster = ["developer"]
        mock_orch.loaded_path = None
        mock_orch.codebase_context = {}
        mock_orch.config = config
        mock_orch.agents = {}  # no agents at all

        developer = Agent(
            role="developer",
            persona=personas.get("developer", {"name": "Sam"}),
            memory=mm,
            model="sonnet",
            base_dir=base_dir,
            orchestrator=mock_orch,
        )

        result = developer._get_peer_input("nonexistent", "Hello?")
        assert "not found" in result

    def test_active_roster_agent_still_works(self, base_dir, config):
        """Agents on the active roster should still be consultable (no regression)."""
        from agents.agent import Agent
        from utils.memory_manager import MemoryManager

        mm = MemoryManager(base_dir, "_general")
        personas = config["agent_personas"]

        mock_orch = MagicMock()
        mock_orch.active_roster = ["pm", "developer"]
        mock_orch.loaded_path = None
        mock_orch.codebase_context = {}
        mock_orch.config = config

        pm_agent = Agent(
            role="pm",
            persona=personas.get("pm", {"name": "Alex"}),
            memory=mm,
            model="sonnet",
            base_dir=base_dir,
            orchestrator=mock_orch,
        )
        mock_orch.agents = {"pm": pm_agent}

        developer = Agent(
            role="developer",
            persona=personas.get("developer", {"name": "Sam"}),
            memory=mm,
            model="sonnet",
            base_dir=base_dir,
            orchestrator=mock_orch,
        )

        with patch("agents.agent.call_claude", return_value="Sprint 1 is on track."):
            result = developer._get_peer_input("pm", "What's the sprint status?")

        assert "not on the active team" not in result
        assert "Sprint" in result
