"""Tests for build_tree file counting integration."""
from pathlib import Path

from utils.db_manager import DBManager
from utils.display import Display


class TestBuildTreeFileCount:
    def test_scan_context_returns_total_files(self, base_dir, config):
        """_scan_codebase should return a total_files count."""
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
        ctx = orch._scan_codebase(base_dir)
        assert "total_files" in ctx
        assert isinstance(ctx["total_files"], int)
        assert ctx["total_files"] > 0
        db.close()

    def test_no_double_rglob(self, base_dir, config):
        """_scan_codebase should NOT call rglob('*') for file counting.

        We verify by checking that build_tree itself produces the count
        (the method should only traverse once).
        """
        import ast
        from orchestrator import Orchestrator

        source_file = Path(Orchestrator.__module__.replace(".", "/") + ".py")
        source = source_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_scan_codebase":
                body_source = ast.get_source_segment(source, node)
                rglob_count = body_source.count("rglob")
                assert rglob_count == 0, (
                    f"_scan_codebase still calls rglob {rglob_count} time(s); "
                    "file counting should be integrated into build_tree"
                )
                break
        else:
            raise AssertionError("Could not find _scan_codebase method")
        db = DBManager(base_dir / "db" / "conversations.db").close()

    def test_ignored_dirs_not_counted(self, base_dir, config):
        """Files inside ignored directories (node_modules, .git, etc.) should not
        be included in total_files."""
        from orchestrator import Orchestrator

        # Create some files in an ignored dir
        ignored = base_dir / "node_modules" / "pkg"
        ignored.mkdir(parents=True)
        (ignored / "index.js").write_text("module.exports = {};")
        (ignored / "util.js").write_text("// util")

        # And some visible files
        (base_dir / "app.py").write_text("print('hello')")

        db = DBManager(base_dir / "db" / "conversations.db")
        display = Display()
        orch = Orchestrator(
            project_name="_general",
            base_dir=base_dir,
            db=db,
            display=display,
            config=config,
        )
        ctx = orch._scan_codebase(base_dir)
        # The 2 node_modules files should NOT be counted
        # Count expected visible files
        all_visible = [
            f for f in base_dir.rglob("*")
            if f.is_file()
            and "node_modules" not in f.parts
            and ".git" not in f.parts
            and not any(p.startswith(".") for p in f.relative_to(base_dir).parts)
        ]
        assert ctx["total_files"] == len(all_visible)
        db.close()
