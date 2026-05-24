"""Tests for is_blocking_bash(), _diagnose_timeout(), and
_has_markdown_artifacts() — guards that prevent agents from running
interactive processes, help them understand timeouts, and stop them
from writing markdown into code files.
"""
import pytest
from pathlib import Path
from utils.action_executor import (
    is_blocking_bash,
    _diagnose_timeout,
    _has_markdown_artifacts,
)


class TestBlockedCommands:
    """Commands that must always be blocked."""

    def test_vite_dev_server(self):
        assert is_blocking_bash("node_modules\\.bin\\vite") is True

    def test_vite_with_no_args(self):
        assert is_blocking_bash("vite") is True

    def test_npm_start(self):
        assert is_blocking_bash("npm start") is True

    def test_npm_run_dev(self):
        assert is_blocking_bash("npm run dev") is True

    def test_yarn_start(self):
        assert is_blocking_bash("yarn start") is True

    def test_yarn_dev(self):
        assert is_blocking_bash("yarn dev") is True

    def test_npm_test_bare(self):
        assert is_blocking_bash("npm test") is True

    def test_npm_test_verbose_only(self):
        # --verbose alone does NOT disable watch mode
        assert is_blocking_bash("npm test -- --verbose") is True

    def test_npm_test_reporter_verbose_with_redirect(self):
        # The exact command that hung: 2>&1 redirect doesn't disable watch mode
        assert is_blocking_bash("npm test -- --reporter=verbose 2>&1") is True

    def test_npm_run_test(self):
        # npm run test is equivalent to npm test — must be caught
        assert is_blocking_bash("npm run test") is True

    def test_npm_run_test_in_cd_chain(self):
        # The exact command that slipped through: cd frontend && npm run test
        assert is_blocking_bash("cd frontend && npm run test") is True

    def test_npm_run_test_with_verbose(self):
        # --verbose alone doesn't disable watch mode in npm run test either
        assert is_blocking_bash("npm run test -- --verbose") is True

    def test_vitest_without_run(self):
        assert is_blocking_bash("npx vitest") is True
        assert is_blocking_bash("vitest") is True
        assert is_blocking_bash("npx vitest --reporter=verbose") is True

    def test_jest_bare(self):
        assert is_blocking_bash("jest") is True

    def test_jest_with_test_path(self):
        assert is_blocking_bash("jest src/App.test.js") is True

    def test_flask_run(self):
        assert is_blocking_bash("flask run") is True
        assert is_blocking_bash("flask run --port 5000") is True

    def test_uvicorn(self):
        assert is_blocking_bash("uvicorn app.main:app") is True
        assert is_blocking_bash("uvicorn app.main:app --reload") is True

    def test_django_runserver(self):
        assert is_blocking_bash("python manage.py runserver") is True
        assert is_blocking_bash("python manage.py runserver 0.0.0.0:8000") is True

    def test_nodemon(self):
        assert is_blocking_bash("nodemon server.js") is True


class TestSafeCommands:
    """Commands that must pass through (not be blocked)."""

    def test_vite_build(self):
        assert is_blocking_bash("vite build") is False
        assert is_blocking_bash("node_modules\\.bin\\vite build") is False
        assert is_blocking_bash("npx vite build") is False

    def test_vitest_run(self):
        assert is_blocking_bash("vitest run") is False
        assert is_blocking_bash("vitest run --reporter=verbose") is False
        assert is_blocking_bash("npx vitest run") is False
        assert is_blocking_bash("node_modules\\.bin\\vitest run --reporter=verbose") is False

    def test_npm_test_with_watchall_false(self):
        assert is_blocking_bash("npm test -- --watchAll=false") is False
        assert is_blocking_bash("npm test -- --watchAll=false --verbose") is False

    def test_npm_run_test_with_watchall_false(self):
        assert is_blocking_bash("npm run test -- --watchAll=false") is False

    def test_npm_run_test_with_ci_prefix(self):
        assert is_blocking_bash("set CI=true && npm run test -- --verbose") is False

    def test_jest_with_watchall_false(self):
        assert is_blocking_bash("jest --watchAll=false") is False

    def test_jest_with_ci_flag(self):
        assert is_blocking_bash("jest --ci") is False
        assert is_blocking_bash("jest --ci --verbose") is False

    def test_npm_test_with_ci_env_prefix(self):
        # CI= before npm test — the common Windows pattern
        assert is_blocking_bash("set CI=true && npm test -- --verbose") is False

    def test_npm_test_with_ci_env_inline(self):
        # Unix-style inline env var
        assert is_blocking_bash("CI=true npm test -- --verbose") is False

    def test_npm_install(self):
        assert is_blocking_bash("npm install") is False

    def test_npm_run_build(self):
        assert is_blocking_bash("npm run build") is False

    def test_npm_run_lint(self):
        assert is_blocking_bash("npm run lint") is False

    def test_python_script(self):
        assert is_blocking_bash("python -c \"from app.main import app\"") is False

    def test_pytest(self):
        assert is_blocking_bash("pytest tests/") is False
        assert is_blocking_bash("python -m pytest tests/ -v") is False

    def test_git_commands(self):
        assert is_blocking_bash("git status") is False
        assert is_blocking_bash("git add .") is False

    def test_pip_install(self):
        assert is_blocking_bash("pip install -r requirements.txt") is False


class TestCIEnvDoesNotDisableServers:
    """CI= in command must NOT unblock dev servers — only test runners."""

    def test_ci_does_not_unblock_vite_dev(self):
        # Someone might accidentally write this — vite still starts a server
        assert is_blocking_bash("set CI=true && vite") is True

    def test_ci_does_not_unblock_npm_start(self):
        assert is_blocking_bash("set CI=true && npm start") is True

    def test_ci_does_not_unblock_uvicorn(self):
        assert is_blocking_bash("set CI=true && uvicorn app.main:app") is True

    def test_ci_does_not_unblock_nodemon(self):
        assert is_blocking_bash("CI=true nodemon server.js") is True

    def test_ci_does_not_unblock_vitest_watch(self):
        # vitest without "run" is still watch mode even with CI=
        assert is_blocking_bash("set CI=true && vitest --reporter=verbose") is True


class TestDiagnoseTimeout:
    """_diagnose_timeout() returns actionable hints from partial output."""

    def test_jest_watch_mode_output(self):
        partial = "Watch Usage\n › Press a to run all tests.\n › Press f to run only failed tests."
        hint = _diagnose_timeout(partial)
        assert hint
        assert "watch" in hint.lower() or "CI=" in hint or "vitest run" in hint

    def test_credential_prompt(self):
        partial = "Username for 'https://github.com': "
        hint = _diagnose_timeout(partial)
        assert hint
        assert "credential" in hint.lower() or "ssh" in hint.lower() or "token" in hint.lower()

    def test_password_prompt(self):
        partial = "Password for 'https://user@github.com': "
        hint = _diagnose_timeout(partial)
        assert hint

    def test_server_started(self):
        partial = "  VITE v5.0.0  ready in 312 ms\n\n  ➜  Local:   http://localhost:5173/"
        hint = _diagnose_timeout(partial)
        assert hint
        assert "server" in hint.lower() or "build" in hint.lower()

    def test_file_watcher(self):
        partial = "watching files for changes..."
        hint = _diagnose_timeout(partial)
        assert hint
        assert "watch" in hint.lower()

    def test_slow_install(self):
        partial = "added 1234 packages\ninstalling dependencies..."
        hint = _diagnose_timeout(partial)
        assert hint
        assert "install" in hint.lower() or "build" in hint.lower() or "slow" in hint.lower()

    def test_slow_compile(self):
        partial = "compiling typescript... 847 files"
        hint = _diagnose_timeout(partial)
        assert hint

    def test_no_output_returns_empty(self):
        # No output — caller is responsible for the "no output" heuristic
        hint = _diagnose_timeout("")
        assert hint == ""

    def test_normal_output_no_hint(self):
        # Regular test output — no interactive pattern
        partial = "PASS src/App.test.js\n  ✓ renders without crashing (12ms)\n1 test passed"
        hint = _diagnose_timeout(partial)
        assert hint == ""


class TestDiagnoseTimeoutZeroTest:
    """_diagnose_timeout detects vitest (0 test) module-load hang."""

    def test_zero_test_signature_detected(self):
        """Vitest output with (0 test) on a stuck file triggers the hint."""
        partial = (
            " RUN  v2.1.9 C:/project/frontend\n\n"
            "❯ src/__tests__/PdfViewer.test.jsx (0 test)\n"
            " ✓ src/__tests__/PdfSearch.test.jsx (20 tests) 191ms\n"
        )
        hint = _diagnose_timeout(partial)
        assert hint, "Expected a hint for (0 test) signature"
        assert "PdfViewer.test.jsx" in hint
        assert "module" in hint.lower()
        assert "isolat" in hint.lower()  # "isolation" or "isolate"

    def test_hint_names_the_exact_stuck_file(self):
        """Stuck filename is extracted from the ❯ line and included in the hint."""
        partial = "❯ src/__tests__/HangingSpec.test.ts (0 test)\n✓ other.test.ts (5 tests) 40ms"
        hint = _diagnose_timeout(partial)
        assert "HangingSpec.test.ts" in hint

    def test_zero_test_takes_priority_over_watch_mode_pattern(self):
        """(0 test) hint fires even when watch-mode text also appears — gives the more specific hint."""
        partial = (
            "❯ src/__tests__/PdfViewer.test.jsx (0 test)\n"
            "watch mode enabled\nPress a to run all tests"
        )
        hint = _diagnose_timeout(partial)
        # Should get the targeted (0 test) hint, not the generic watch-mode one
        assert "PdfViewer.test.jsx" in hint
        assert "module" in hint.lower()


class TestDiagnoseTimeoutVerboseMode:
    """_diagnose_timeout detects silent hang when --reporter=verbose hides the ❯ bar."""

    def _make_verbose_output(self, files=None):
        """Build realistic verbose vitest output for the given completed test files."""
        files = files or [
            "src/__tests__/PdfSearch.test.jsx",
            "src/__tests__/DocumentSearch.test.jsx",
        ]
        lines = [" RUN  v2.1.9 C:/project/frontend\n"]
        for f in files:
            lines.append(f" ✓ {f} > Suite > test one\n")
            lines.append(f" ✓ {f} > Suite > test two\n")
        # NO "Test Files" summary — that only prints when ALL files complete
        return "".join(lines)

    def test_verbose_silent_hang_detected(self):
        """Verbose output with ✓ lines but no 'Test Files' summary triggers the hint."""
        partial = self._make_verbose_output()
        hint = _diagnose_timeout(partial)
        assert hint, "Expected a hint for verbose-mode silent hang"
        assert "Test Files" in hint or "summary" in hint.lower()
        assert "verbose" in hint.lower()

    def test_verbose_hint_lists_completed_files(self):
        """Completed test file names appear in the hint so the agent knows which is missing."""
        partial = self._make_verbose_output([
            "src/__tests__/PdfSearch.test.jsx",
            "src/__tests__/UploadButton.test.jsx",
        ])
        hint = _diagnose_timeout(partial)
        assert "PdfSearch.test.jsx" in hint
        assert "UploadButton.test.jsx" in hint

    def test_no_false_positive_when_summary_present(self):
        """If the 'Test Files' summary IS present, the verbose hint must NOT fire."""
        partial = (
            self._make_verbose_output()
            + "\n Test Files  2 passed (2)\n Tests  4 passed (4)\n"
        )
        hint = _diagnose_timeout(partial)
        # Summary is present — all files completed normally, no hang hint expected
        assert "Test Files" not in hint or "summary" not in hint.lower() or not hint

    def test_no_false_positive_with_no_test_output(self):
        """No verbose test lines at all → verbose hint must NOT fire (different problem)."""
        partial = " RUN  v2.1.9 C:/project/frontend\n"
        hint = _diagnose_timeout(partial)
        # No ✓ lines means something else is wrong — not the verbose-reporter hang
        assert "verbose" not in hint.lower()

    def test_verbose_hint_advises_removing_reporter_flag(self):
        """Hint must tell the agent to remove --reporter=verbose to reveal the stuck file."""
        partial = self._make_verbose_output()
        hint = _diagnose_timeout(partial)
        assert "verbose" in hint.lower()


class TestDiagnoseTimeoutTeardown:
    """_diagnose_timeout detects vitest teardown hang (all files passed, no summary)."""

    def _make_teardown_output(self, files=None):
        """Build default-reporter output where all files completed but no summary printed."""
        files = files or [
            ("src/__tests__/DocumentSearch.test.jsx", 24, 166),
            ("src/__tests__/PdfSearch.test.jsx", 20, 184),
            ("src/__tests__/UploadButton.test.jsx", 26, 202),
            ("src/__tests__/PdfViewer.test.jsx", 21, 470),
            ("src/__tests__/App.integration.test.jsx", 31, 693),
        ]
        lines = [" RUN  v2.1.9 C:/project/frontend\n\n"]
        for name, count, ms in files:
            lines.append(f" ✓ {name} ({count} tests) {ms}ms\n")
        # No "Test Files  5 passed (5)" summary — that's the hang
        return "".join(lines)

    def test_teardown_hang_detected(self):
        """All files passed but no summary triggers the teardown hint."""
        partial = self._make_teardown_output()
        hint = _diagnose_timeout(partial)
        assert hint, "Expected a hint for teardown hang"
        assert "teardown" in hint.lower() or "summary" in hint.lower() or "forceExit" in hint

    def test_hint_mentions_forceexit(self):
        """Hint must tell the agent to add forceExit: true."""
        partial = self._make_teardown_output()
        hint = _diagnose_timeout(partial)
        assert "forceExit" in hint

    def test_hint_mentions_canvas_mock(self):
        """Hint must suggest mocking canvas.getContext as the root cause fix."""
        partial = self._make_teardown_output()
        hint = _diagnose_timeout(partial)
        assert "canvas" in hint.lower() or "getContext" in hint

    def test_no_false_positive_when_summary_present(self):
        """If 'Test Files' summary IS present, teardown hint must NOT fire."""
        partial = self._make_teardown_output() + "\n Test Files  5 passed (5)\n Tests  122 passed (122)\n"
        hint = _diagnose_timeout(partial)
        assert "teardown" not in hint.lower()
        assert "forceExit" not in hint

    def test_no_false_positive_with_failures(self):
        """If any test file failed (× line), teardown hint must NOT fire."""
        partial = (
            " RUN  v2.1.9 C:/project/frontend\n"
            " ✓ src/__tests__/PdfSearch.test.jsx (20 tests) 184ms\n"
            " × src/__tests__/PdfViewer.test.jsx (3 failed | 18 passed) 312ms\n"
        )
        hint = _diagnose_timeout(partial)
        assert "forceExit" not in hint

    def test_teardown_takes_priority_over_slow_op_fallback(self):
        """Teardown hint fires instead of the generic slow build fallback."""
        partial = (
            self._make_teardown_output()
            + "installing packages...\n"   # would trigger slow-op fallback
        )
        hint = _diagnose_timeout(partial)
        assert "forceExit" in hint
        assert "slow build" not in hint.lower()

    def test_single_completed_file_triggers_hint(self):
        """Even one completed file with no summary is enough to detect teardown hang."""
        partial = " RUN  v2.1.9 C:/project/frontend\n ✓ src/__tests__/App.integration.test.jsx (31 tests) 693ms\n"
        hint = _diagnose_timeout(partial)
        assert hint
        assert "forceExit" in hint


class TestDiagnoseTimeoutDotMode:
    """_diagnose_timeout detects silent hang when --reporter=dot hides the ❯ bar."""

    def test_dot_reporter_hang_detected(self):
        """Dot reporter with no 'Test Files' summary triggers the hint."""
        partial = (
            " RUN  v2.1.9 C:/project/frontend\n\n"
            " .......................\n"
        )
        hint = _diagnose_timeout(partial)
        assert hint, "Expected a hint for dot-reporter silent hang"
        assert "dot" in hint.lower()

    def test_dot_hint_advises_default_reporter(self):
        """Hint must tell the agent to remove --reporter=dot and use the default."""
        partial = " RUN  v2.1.9 C:/project/frontend\n .....\n"
        hint = _diagnose_timeout(partial)
        assert "dot" in hint.lower()
        assert "default" in hint.lower() or "no --reporter" in hint.lower() or "no flag" in hint.lower()

    def test_no_false_positive_when_summary_present(self):
        """If 'Test Files' summary IS present, the dot hint must NOT fire."""
        partial = (
            " RUN  v2.1.9 C:/project/frontend\n\n"
            " .......................\n"
            "\n Test Files  5 passed (5)\n Tests  22 passed (22)\n"
        )
        hint = _diagnose_timeout(partial)
        assert "dot" not in hint.lower()

    def test_no_false_positive_without_run_header(self):
        """Dots in non-vitest output (e.g. progress bars) must NOT trigger the hint."""
        partial = "Downloading...\n.....\nDone.\n"
        hint = _diagnose_timeout(partial)
        assert "dot" not in hint.lower()

    def test_dot_takes_priority_over_slow_op_fallback(self):
        """Dot-reporter hint must fire instead of the generic slow build fallback."""
        partial = (
            " RUN  v2.1.9 C:/project/frontend\n"
            " .......................\n"
            "bundling 45 modules\n"   # would normally trigger slow-op fallback
        )
        hint = _diagnose_timeout(partial)
        assert "dot" in hint.lower()
        assert "slow build" not in hint.lower()


class TestMarkdownArtifactDetection:
    """_has_markdown_artifacts() catches stray markdown written into code files."""

    def test_triple_backtick_in_jsx_rejected(self):
        content = "export default function App() {\n  return <div/>\n}\n```\n"
        warning = _has_markdown_artifacts(Path("src/App.jsx"), content)
        assert warning is not None
        assert "backtick" in warning.lower() or "fence" in warning.lower() or "```" in warning

    def test_triple_backtick_in_py_rejected(self):
        content = "def hello():\n    pass\n```\nNow run the suite\n"
        warning = _has_markdown_artifacts(Path("utils/helper.py"), content)
        assert warning is not None

    def test_prose_instruction_in_js_rejected(self):
        content = "const x = 1;\nNow run the following command to test:\nnpm test\n"
        warning = _has_markdown_artifacts(Path("src/index.js"), content)
        assert warning is not None
        assert "prose" in warning.lower() or "markdown" in warning.lower()

    def test_clean_jsx_not_rejected(self):
        content = (
            "import React from 'react';\n"
            "export default function App() {\n"
            "  return <div className='app'>Hello</div>;\n"
            "}\n"
        )
        assert _has_markdown_artifacts(Path("src/App.jsx"), content) is None

    def test_clean_python_not_rejected(self):
        content = (
            "def greet(name: str) -> str:\n"
            "    \"\"\"Return a greeting.\"\"\"\n"
            "    return f'Hello, {name}'\n"
        )
        assert _has_markdown_artifacts(Path("utils/greet.py"), content) is None

    def test_markdown_file_not_checked(self):
        """Markdown files may contain ``` — they must never be rejected."""
        content = "# Title\n\n```python\nprint('hello')\n```\n"
        assert _has_markdown_artifacts(Path("README.md"), content) is None

    def test_yaml_file_not_checked(self):
        content = "name: my-project\nversion: 1.0.0\n"
        assert _has_markdown_artifacts(Path("project.yaml"), content) is None

    def test_now_run_phrase_in_tsx_rejected(self):
        content = "export const x = 1;\nNow run:\nnpm test\n"
        warning = _has_markdown_artifacts(Path("src/constants.tsx"), content)
        assert warning is not None

    def test_here_is_phrase_in_py_rejected(self):
        content = "class Foo:\n    pass\nHere is how to use it:\nfoo = Foo()\n"
        warning = _has_markdown_artifacts(Path("app/models.py"), content)
        assert warning is not None
