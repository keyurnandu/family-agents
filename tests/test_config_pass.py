"""Tests for passing config dict to Orchestrator instead of re-reading YAML."""
from pathlib import Path

import yaml

from utils.db_manager import DBManager
from utils.display import Display


class TestOrchestratorAcceptsConfig:
    def test_init_accepts_config_parameter(self, base_dir, config):
        """Orchestrator.__init__ should accept an optional config parameter."""
        from orchestrator import Orchestrator
        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator(
            project_name="_general",
            base_dir=base_dir,
            db=db,
            display=display,
            config=config,
        )
        assert orch.config is config
        db.close()

    def test_uses_passed_config_not_disk(self, base_dir, config):
        """When config is passed, it should be used directly without reading YAML."""
        from orchestrator import Orchestrator
        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()

        # Modify the config to prove we're using the passed version
        config["_test_marker"] = True

        orch = Orchestrator(
            project_name="_general",
            base_dir=base_dir,
            db=db,
            display=display,
            config=config,
        )
        assert orch.config.get("_test_marker") is True
        db.close()

    def test_falls_back_to_yaml_when_no_config(self, base_dir):
        """When config is not passed, should fall back to reading settings.yaml."""
        from orchestrator import Orchestrator
        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator(
            project_name="_general",
            base_dir=base_dir,
            db=db,
            display=display,
        )
        assert "team" in orch.config
        assert "agent_personas" in orch.config
        db.close()
