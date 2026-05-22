"""Tests for threading lock on _update_project_state."""
import threading


class TestStateLock:
    def test_orchestrator_has_state_lock(self, base_dir, config):
        """Orchestrator should have a _state_lock attribute of type threading.Lock."""
        from orchestrator import Orchestrator
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
        assert hasattr(orch, "_state_lock")
        assert isinstance(orch._state_lock, type(threading.Lock()))
        db.close()

    def test_update_project_state_source_uses_lock(self, base_dir, config):
        """The _update_project_state method body should acquire _state_lock."""
        import ast
        from pathlib import Path
        from orchestrator import Orchestrator

        source_file = Path(Orchestrator.__module__.replace(".", "/") + ".py")
        source = source_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_update_project_state":
                body_source = ast.get_source_segment(source, node)
                assert "_state_lock" in body_source, (
                    "_update_project_state should use self._state_lock"
                )
                break
        else:
            raise AssertionError("Could not find _update_project_state method")
