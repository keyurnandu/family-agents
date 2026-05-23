# Auto-Learned Lessons — developer

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-23 22:00] via user-correction
NEVER run git commands (git add, git commit, git push, git pull, git checkout, git stash, etc.) unless the user EXPLICITLY asks for it. The user manages git themselves. Focus only on writing code, running tests, and fixing errors. Git is off-limits.

### [2026-05-21 17:24] via bash-failure
Always add `asyncio_mode = 'auto'` to pytest.ini when running async Playwright tests on Windows to prevent `ValueError: I/O operation on closed pipe` during asyncio cleanup. Alternatively, ensure all Playwright fixtures use proper `async with async_playwright()` context managers and add explicit event loop cleanup in conftest.py.

### [2026-05-21 17:43] via bash-failure
Always verify the required service is running before executing migration scripts that depend on it—test MongoDB connectivity with `mongosh` or explicitly start `mongod` before running `scripts/migrate_p1_runner_field.py`.

### [2026-05-21 17:46] via bash-failure
Always check if a Windows service is registered before running `net start <servicename>` — use `Get-Service MongoDB` or `sc query MongoDB` first, as the service name may differ from the application name or may not exist.

### [2026-05-21 17:46] via bash-failure
Before running `scripts/migrate_p1_runner_field.py`, verify MongoDB is running on localhost:27017. The ServerSelectionTimeoutError indicates the database service wasn't listening — start it with `mongod` or check existing processes first.

### [2026-05-21 17:59] via bash-failure
Before running `mongod` commands, verify MongoDB is installed and in PATH with `mongod --version` or `where mongod`. This prevents 'not recognized' errors from missing installations.

### [2026-05-21 18:32] via bash-failure
Always verify that patched imports exist in their target modules before running pytest; the `AttributeError` on `RunnerFactory` means your tests expect a class that isn't in `app.services.run_service`. Use grep to check the module has the attribute you're mocking, or refactor tests to mock the correct import path.

### [2026-05-21 18:33] via bash-failure
Before committing source refactoring, run `pytest tests/ -v` to verify that all test imports resolve—mismatches where tests reference deleted or moved classes like `RunnerConfig` will fail collection immediately.

### [2026-05-21 18:36] via bash-failure
Before modifying module exports or structure, always run pytest to catch import mismatches in tests. ImportErrors during collection block the entire test suite until fixed.

### [2026-05-21 18:38] via bash-failure
Always run `pytest --collect-only` after modifying a module's exports (removing or renaming classes) to catch breaking imports before tests execute. This test failure should have been caught immediately by verifying that `RunnerConfig` is still exported from `base_runner.py`.

### [2026-05-21 18:54] via bash-failure
Always run `pytest --collect-only` before executing a full test suite to catch import errors without wasting time on test execution. This would have immediately revealed that `RunnerNotFoundError` and `RunnerNotInitializedError` don't exist in their source modules.

### [2026-05-21 18:56] via bash-failure
Always check for Unix-specific commands (`tail`, `head`, `sed`, etc.) in test code and fixtures when developing on Windows; replace them with cross-platform Python alternatives or add platform detection before running tests.

### [2026-05-21 19:05] via bash-failure
Always grep the target modules for each imported class before running pytest (e.g., `grep RunnerNotFoundError app/services/runner/factory.py`) to catch missing imports during test collection.

### [2026-05-21 19:17] via bash-failure
Before removing or renaming exception classes from the exceptions module, search the entire codebase for all imports to catch dangling references—`factory.py` is trying to import `RunnerContractError` which no longer exists in `exceptions.py`.

### [2026-05-21 19:21] via bash-failure
Always run `pytest --collect-only` before full tests to catch import errors early. This would have detected the missing `RunnerContractError` class in exceptions.py before breaking 20 test modules during collection.

### [2026-05-21 19:29] via bash-failure-batch
Always use PowerShell `-Head` parameter or platform-native alternatives instead of piping to `head` when running commands on Windows — the Unix command doesn't exist in cmd.exe.

### [2026-05-21 19:29] via bash-failure-batch
Before running pytest, ensure that `RunnerContractError` is defined and exported from `app/services/runner/exceptions.py` — factory.py line 7 imports it but the class doesn't exist, blocking all test collection.

### [2026-05-21 19:33] via bash-failure
Before merging constructor changes, run `pytest tests/runner/ -v` to catch signature mismatches. The `TypeError: __init__() got an unexpected keyword argument 'browser'` pattern means the implementation API doesn't match test expectations.

### [2026-05-22 10:23] via lesson
Before running `pytest`, verify test imports by checking that imported classes exist in source modules — use `grep 'RunnerNotFoundError' app/services/runner/factory.py` to catch import errors before test collection.

### [2026-05-22 10:27] via lesson
Always use `pytest --tb=long` when seeing multiple ERROR lines in test output, as `--tb=short` truncates the actual AttributeError causing test collection to fail. Scroll to the top of the output or run `pytest --collect-only` to see the root import/setup error before debugging individual test logic.

### [2026-05-22 10:40] via lesson
Before running pytest, verify that all classes and functions imported in test files actually exist in their source modules—use grep to check test imports against module contents.

### [2026-05-22 10:53] via lesson
Always initialize runners in pytest fixtures before tests execute; add `await runner.initialize()` calls to conftest.py setup methods to prevent `RunnerNotInitializedError` across Playwright and Selenium test suites.

### [2026-05-22 15:18] via lesson
Before starting a dependent development phase, always resolve blocking architectural decisions (Literal vs Enum for the DTO contract) with stakeholders and verify critical CI binaries (Chrome, Firefox, ChromeDriver, GeckoDriver) are available—request these confirmations synchronously, not discover them mid-phase.

### [2026-05-22 16:03] via lesson
Before running pytest, verify all imports resolve by checking that imported names actually exist in their source modules (e.g., confirm `TriggerRunResponse` exists in `app.dtos.run.py`).

### [2026-05-22 16:14] via lesson
Before running `pytest` with `-n auto` on Windows, use `--tb=long` and run serially first (remove `-n` flag) to diagnose import and fixture errors that parallel execution masks. The truncated file paths and ERROR-level collection failures indicate import/path resolution issues that `-n auto` and `--tb=short` are hiding.

### [2026-05-22 17:04] via lesson
Always verify that imported symbols are exported from their source modules before running import validation scripts — `RunnerType` is missing from `app.services.runner.__init__.py`.

### [2026-05-22 17:04] via lesson
Before running `pytest`, ensure all application imports are resolvable, since test collection fails on the first broken import in production code regardless of test validity.

### [2026-05-22 17:15] via lesson
Never skip examining ERROR statuses in pytest output—the 19 ERRORs across test_auth.py, test_database.py, test_health.py indicate collection or setup failures preventing test execution, which are distinct from the 58 FAILEDs and likely share a common root cause like missing dependencies or broken imports. Before debugging individual test assertions, run `pytest --tb=line` first to isolate what's blocking test collection.

### [2026-05-22 17:21] via lesson
Never use `--tb=line` when running initial pytest suite diagnostics — the truncated output hides root causes; use `--tb=short` or full traceback to identify why 19 tests errored and 58 failed.

### [2026-05-22 17:21] via lesson
Always verify the current directory is a git repository with `git status` before running `git log` to avoid "not a git repository" failures.

### [2026-05-22 17:42] via lesson
Before debugging pytest failures, always run `pytest --collect-only` to expose ERROR tests that indicate import/setup issues cascading to FAILED tests. Fix collection errors first before investigating downstream failures.

### [2026-05-22 18:22] via lesson
Before debugging failing tests, rerun pytest with `--tb=long` instead of `--tb=short` to reveal full error messages; the truncated output is hiding root causes of the 19 ERROR status tests.

### [2026-05-22 18:27] via lesson
Never use `is` to compare enum values in tests; use `==` instead to avoid identity mismatches with coerced or dynamically created enum instances. The assertions should check value equality, not object identity.

### [2026-05-22 18:45] via lesson
Always verify the current directory is a git repository (e.g., `test -d .git`) before chaining git commands with `&&` like `git status && git branch --show-current`.

### [2026-05-22 18:45] via lesson
Never run `git log --oneline` without first confirming the working directory contains a `.git` folder or is within a git repository.

### [2026-05-22 20:48] via lesson
Always verify you're in a git repository by checking for `.git` before running `git status`.

### [2026-05-22 20:48] via lesson
Never attempt `git add` without first confirming the current directory contains `.git`.

### [2026-05-22 20:48] via lesson
Before using `git branch --show-current`, verify the `.git` directory exists in your working directory.

### [2026-05-22 20:48] via lesson
Always validate git repository presence before staging multiple files with `git add .github/workflows/ci.yml scripts/audit_browsers.py tests/conftest.py`.

### [2026-05-22 20:48] via lesson
Before executing `git push origin main`, confirm the current directory contains `.git` to prevent remote operation failures.

### [2026-05-22 20:48] via lesson
Never run `git log --oneline` without first verifying you're in a git-tracked directory.

### [2026-05-22 20:54] via lesson
Always verify the directory is a git repository by running `git rev-parse --is-inside-work-tree` before executing `git status`, `git add`, or any subsequent git operations.

### [2026-05-22 20:54] via lesson
Never proceed to `git add` after `git status` fails with "not a git repository" — stop immediately and diagnose whether the `.git` directory exists in the current or parent directories.

### [2026-05-22 20:54] via lesson
Before running `git commit`, validate the working directory is initialized as a repository by confirming the `.git/` folder exists or testing with `git rev-parse --git-dir` first.

### [2026-05-22 20:54] via lesson
Never chain multiple git commands (status → add → commit → push) when the initial command fails with "not a git repository" — each subsequent command will fail identically, wasting execution attempts.

### [2026-05-22 21:04] via lesson
Always run `git status` before `git add [files]` to verify those files actually have changes. This prevents silent failures where nothing gets staged and reveals unexpected modifications elsewhere in the working tree.

### [2026-05-22 21:14] via lesson
Never use Unix utilities like `tail` in bash commands on Windows — use `findstr` or PowerShell's `Select-Object -Last` instead, or ensure the command doesn't pipe output to tail.

### [2026-05-22 21:14] via lesson
Always verify bash commands are syntactically complete before execution — Failures 1 and 2 show truncated commands ending abruptly at `set BRO` and `test_enum_`, which prevented the actual execution.

### [2026-05-22 21:14] via lesson
Before running bash commands on Windows, use platform-native alternatives or WSL — mixing `venv\Scripts\python.exe` (Windows path) with Unix tools causes compatibility errors; commit to either pure Windows commands or use `wsl` prefix for Unix tooling.

### [2026-05-22 21:19] via lesson
Always verify that fixture cleanup methods referenced in conftest.py actually exist on their target classes before running pytest (RunnerFactory.clear() is undefined). Check the class definition to confirm the method exists or use the correct cleanup method name.

### [2026-05-22 21:24] via lesson
Before running pytest, verify imported custom exceptions are actually defined in their modules — RunnerNotFoundError was missing from app.services.runner.factory and should have been checked when writing the test import.

### [2026-05-22 21:28] via lesson
Before renaming or deleting any exported class (like `RunnerConfigError`), search the entire codebase for all imports using grep and update them simultaneously. Always run `check_imports.py` before committing to catch import mismatches early.

### [2026-05-22 21:35] via lesson
Always execute check_imports.py before running pytest to catch ImportErrors early—I should have verified that RunnerError actually exists in exceptions.py before importing it in runner/__init__.py.

### [2026-05-22 21:36] via lesson
Always ensure RunnerFactory runner registration completes during test setUp, not after factory instantiation—the "Available runners: <none>" error indicates initialization was skipped or executed too late in the lifecycle.

### [2026-05-22 21:53] via lesson
Always use `--tb=long` instead of `--tb=s` when you see widespread failures across multiple test modules—short traceback hides the root cause of cascading failures. Before investigating, run a single failing test with full output: `pytest tests/test_runner_state.py::test_runner_is_not_initialized_before_init -v --tb=long` to identify the actual error.

### [2026-05-22 22:06] via lesson
Always inspect ERROR-status tests before FAILED tests in pytest output — ERROR indicates import/fixture/setup issues that must be resolved first, while FAILED indicates code logic problems that can't be debugged until infrastructure works.

### [2026-05-22 22:08] via lesson
Always run a single test module (`pytest tests/test_auth.py -v`) first when seeing ERROR across multiple modules—this isolates fixture/dependency issues faster than debugging the full suite.

### [2026-05-22 22:21] via lesson
Always implement factory methods like RunnerFactory.get_runner() before running tests that call them — missing this method caused AttributeError to cascade across 5 tests and break the entire suite.

### [2026-05-22 22:21] via lesson
Before debugging FAILED tests, always fix ERROR results first — the 19 collection/import errors (from the broken factory import) caused 63 cascading test failures downstream.

### [2026-05-22 22:27] via lesson
Always verify test exception expectations (pytest.raises) match the actual exceptions the implementation raises — here tests expected `ValueError` but code raises `RunnerNotFoundError`.

### [2026-05-22 22:27] via lesson
Never use Unicode special characters like ✓ in print statements without encoding verification — use ASCII alternatives on Windows where console encoding defaults to cp1252 (caused the \u2713 character crash).

### [2026-05-22 22:32] via lesson
Always validate imports compile before running pytest—missing exports in one module break test collection across the entire suite. Use `python -c 'import app.dtos.run'` or `python -m compileall app/` to catch import errors before pytest collection fails.

### [2026-05-22 22:37] via lesson
Never append `-` to `pytest --collect-only`; this flag doesn't support stdin notation and causes syntax failures. Always validate pytest flag syntax before execution.

### [2026-05-22 22:41] via lesson
Before running `pytest`, verify all test file imports exist in their source modules—e.g., check that `app.dtos.run` contains `ScheduleRunRequest` using `grep` to avoid import collection errors.

### [2026-05-22 22:46] via lesson
Before re-running full tests, investigate ERROR tests first using `pytest -vv tests/test_auth.py::test_register_route` in isolation. ERROR indicates systemic blockers (setup/imports) cascading across modules while FAILED are isolated assertion problems.

### [2026-05-22 22:50] via lesson
Always run `pytest --collect-only tests/` before executing the full test suite to catch collection errors early—the 19 ERROR entries in test_auth.py, test_database.py, etc. indicate systemic import/setup failures that won't be evident from raw failure counts.

### [2026-05-23 04:35] via lesson
Before debugging test failures, fix all test ERRORs first—they indicate setup/import/environment issues that prevent tests from running, whereas FAILUREs are logic problems that depend on the environment being correct.

### [2026-05-23 04:52] via lesson
Before running OpenAPI contract test suites, verify the spec file exists and is accessible. Always run a single test with `pytest -vv` flag first when seeing ERROR status—errors indicate setup issues like missing files, not logic failures.

### [2026-05-23 04:56] via lesson
Always quote file paths containing spaces in bash commands — the parent directory "OneDrive - Adobe" requires quoting: `dir "tests\test_openapi*"` instead of `dir tests\test_openapi*`.
