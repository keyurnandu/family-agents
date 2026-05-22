"""Tests for import hygiene: no inline re/threading imports."""
import ast
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


class TestNoInlineImports:
    def _find_inline_imports(self, filepath: Path, module_name: str) -> list[int]:
        """Return line numbers where 'import <module_name>' appears inside a function/method."""
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
        hits = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if isinstance(child, ast.Import):
                        for alias in child.names:
                            if alias.name == module_name or (alias.asname and alias.asname == module_name):
                                hits.append(child.lineno)
                    elif isinstance(child, ast.ImportFrom):
                        if child.module == module_name:
                            hits.append(child.lineno)
        return hits

    def test_no_inline_re_import_in_orchestrator(self):
        """orchestrator.py should not have 'import re as _re' inside any function."""
        hits = self._find_inline_imports(BASE / "orchestrator.py", "re")
        assert hits == [], f"Found inline 'import re' at lines {hits} in orchestrator.py"

    def test_threading_is_module_level_in_orchestrator(self):
        """orchestrator.py should import threading at module level, not inside functions."""
        hits = self._find_inline_imports(BASE / "orchestrator.py", "threading")
        assert hits == [], f"Found inline 'import threading' at lines {hits} in orchestrator.py"

    def test_threading_in_module_level_imports(self):
        """threading should be in the top-level imports of orchestrator.py."""
        source = (BASE / "orchestrator.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_imports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_level_imports.append(alias.name)
        assert "threading" in top_level_imports


class TestTrimForSynthesisWorks:
    """Ensure _trim_for_synthesis still works correctly after removing inline re import."""

    def test_strips_exec_file_blocks(self):
        from orchestrator import Orchestrator
        text = (
            "Here is the implementation:\n"
            "EXEC:file:src/main.py\n"
            "```python\n"
            "def main():\n"
            "    print('hello')\n"
            "```\n"
            "That's the file."
        )
        result = Orchestrator._trim_for_synthesis(text)
        assert "def main" not in result
        assert "shown in apply prompt" in result

    def test_strips_exec_bash_blocks(self):
        from orchestrator import Orchestrator
        text = (
            "Running tests:\n"
            "EXEC:bash\n"
            "```\n"
            "npm test\n"
            "```\n"
            "Done."
        )
        result = Orchestrator._trim_for_synthesis(text)
        assert "npm test" not in result
        assert "shown in apply prompt" in result

    def test_condenses_large_output_blocks(self):
        from orchestrator import Orchestrator
        output_lines = "\n".join(f"test_{i} PASSED" for i in range(20))
        text = f"BASH OK: pytest\nOUTPUT:\n{output_lines}"
        result = Orchestrator._trim_for_synthesis(text)
        assert "last 3 lines" in result
