"""Tests for is_blocking_bash() — the guard that prevents agents from running
interactive / watch-mode processes that never exit.
"""
import pytest
from utils.action_executor import is_blocking_bash


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
