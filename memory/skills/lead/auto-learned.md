# Auto-Learned Lessons — lead

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-23 22:00] via user-correction
Local git operations (git add, git commit, git tag, git stash) are fine — they're just local checkpoints. NEVER run git push, git merge, git rebase, git checkout, or git reset --hard without explicit user approval — these publish to remote or can lose uncommitted work.

### [2026-05-21 17:44] via bash-failure
Before running `uv run` commands, verify uv is installed and in PATH on the target system. On Windows, use `python scripts/migrate_p1_runner_field.py` directly as a fallback if uv isn't available.

### [2026-05-21 17:48] via bash-failure
Always verify a binary is in PATH before invoking it on Windows; use `where mongod` first. If not found, either install MongoDB or provide the full executable path (e.g., `C:\Program Files\MongoDB\Server\X.X\bin\mongod.exe`).

### [2026-05-21 17:48] via bash-failure
Before running `scripts/migrate_p1_runner_`, verify MongoDB is running on localhost:27017 to avoid ServerSelectionTimeoutError; check with `mongosh` or Windows Services first.

### [2026-05-21 17:55] via bash-failure
Before running Python scripts on Windows, set PYTHONIOENCODING=utf-8 environment variable. Never embed Unicode/emoji characters in console output without explicit encoding handling or cross-platform testing.

### [2026-05-21 18:07] via bash-failure
Before running `python -m pytest`, always verify pytest is installed by running `pip install pytest` or checking that project dependencies from `requirements.txt` are installed. Missing test dependencies block test execution immediately.

### [2026-05-21 19:17] via bash-failure
Before running `uv run pytest`, verify all test file path arguments are complete — this command was truncated at `tests/runner/test_`, causing the parse failure. Use shell completion or a script to generate the full list of test files.

### [2026-05-21 19:22] via bash-failure
Before running `uv run pytest`, always execute `uv sync` to ensure the UV environment is initialized and all dependencies are installed. Exit code 255 typically indicates an environment problem rather than a test failure, so verify prerequisites before investigating test code.

### [2026-05-21 19:29] via bash-failure
Before running `uv run pytest`, always run `uv sync` to ensure the environment and dependencies are properly initialized.

### [2026-05-22 10:28] via lesson
Never run the complete test suite when investigating failures—run tests for changed modules first (e.g., `pytest tests/test_runner*.py`) to isolate root causes before running all 331 tests. With 129 failures across multiple modules, selective runs identify which changes broke what, faster.

### [2026-05-22 10:49] via lesson
Always run `uv run` immediately after modifying factory.py or runner base classes — parameter type mismatches (dict vs string in `get_runner()`) cascaded across 17 tests because the changes weren't validated before commit.

### [2026-05-22 10:51] via lesson
Always ensure Selenium/Playwright browser instances are properly closed in test teardown—use context managers or explicit `driver.quit()`/`browser.close()` in fixtures to prevent "unclosed transport" and "closed pipe" failures. Before relying on `--tb=short`, run with default traceback when debugging to surface the actual assertion/execution errors hidden by these cleanup warnings.

### [2026-05-22 10:54] via lesson
Never run `uv run pytest tests/runner/ -q` when debugging failures; use `-v --tb=short` to see actual error tracebacks instead of just failure counts.

### [2026-05-22 15:38] via lesson
Before running `pytest tests/runner/test_phase5_integration.py`, verify that `RunnerFactory.get_runner()` converts enum types like `RunnerType.PLAYWRIGHT` to the string format it expects (`'playwright'`), and that all referenced DTO classes like `RunResponse` are actually exported from their modules.

### [2026-05-22 15:49] via lesson
Always convert enum values to their underlying strings via `.value` attribute in factory lookups, never `str(enum)` which produces `'EnumType.VALUE'` instead of the registered key like `'playwright'`.

### [2026-05-22 15:54] via lesson
Before running pytest, verify all imported classes are actually defined and exported in their source files—check `app.dtos.run` to confirm `RunSummaryPublic` exists before executing tests.

### [2026-05-22 16:01] via lesson
Before running pytest, verify all imported classes exist in their source modules by searching the files; grep for 'class TestRunListItem' in app/dtos/run.py to catch this ImportError immediately instead of discovering it during test execution.

### [2026-05-22 16:09] via lesson
Never include pytest-xdist arguments (`-n`, `--dist`) in pytest.ini without first verifying the plugin is loaded via `pytest --version`—if it's missing or misconfigured, pytest will fail with "unrecognized arguments" errors instead of a clear installation error.

### [2026-05-22 20:47] via lesson
Before running pytest on Windows, verify test dependencies don't invoke Unix utilities like `tail`. Switch to WSL 2 or Docker if they do.

### [2026-05-22 20:55] via lesson
Always verify MongoDB and external services are initialized before running `uv run pytest`; the 19 ERROR-level test failures indicate infrastructure setup issues rather than code defects, distinguishing them from FAILED assertions. Resolve infrastructure errors first before debugging individual test failures.

### [2026-05-22 21:08] via lesson
Always check that names in module `__init__.py` files are actually defined in their source modules before running `pytest`.

### [2026-05-22 21:08] via lesson
Before running multiple test files, verify that all `__init__.py` imports in shared dependencies don't reference non-existent names.

### [2026-05-22 21:08] via lesson
Never run `pytest -q` when test collection shows the same `ImportError` across multiple modules—stop and fix the core import first.

### [2026-05-22 21:14] via lesson
Always verify conftest fixture code references actual module methods before running tests — `conftest.py:80` calls `_f._register_defaults()` which doesn't exist in `factory.py`.

### [2026-05-22 21:14] via lesson
Before running pytest on modified factory code, fix collection errors first — one broken fixture in `conftest.py` cascades into 18+ ERROR entries that mask the root issue.

### [2026-05-22 21:14] via lesson
Never import symbols without confirming they're exported from the module — `tests/test_runner_factory.py:10` imports `RunnerNotFoundError` that isn't defined in `factory.py`.

### [2026-05-22 21:15] via lesson
Never use `tail` command in bash or pytest operations on Windows; Windows doesn't have this built-in utility—replace with platform-specific alternatives like PowerShell's `Select-Object -Last` or write a cross-platform wrapper.

### [2026-05-22 21:15] via lesson
Before running pytest on Windows, audit pytest.ini, conftest.py, and any subprocess calls in fixtures for Unix-specific utilities (`tail`, `sed`, `grep`, `awk`) that aren't available on Windows CMD/PowerShell.

### [2026-05-22 21:15] via lesson
Always check pytest output capture configuration and test setup/teardown code for piped commands (`| tail`) when supporting both Unix and Windows; use conditional logic or remove pipes entirely.

### [2026-05-22 21:21] via lesson
Before running `pytest tests/`, verify all test file imports resolve to actual definitions in source modules—especially exceptions and factory classes. This prevents ImportError during test collection and avoids blocked test runs.

### [2026-05-22 21:25] via lesson
Before running pytest, verify that all imported exception classes exist in their modules—grep for `RunnerBrowserError` in `app/services/runner/exceptions.py` to catch import mismatches before test collection fails.

### [2026-05-22 21:29] via lesson
Before running pytest, verify that all imported exception class names exist in their source files—check that `RunnerConfigError` is defined in `exceptions.py` instead of discovering missing exports through cascading test collection failures.

### [2026-05-22 22:06] via lesson
Before running a test suite with pytest, verify all command flags are syntactically correct (e.g., `--tb=short` not `--tb=shor`) and use `--tb=long` for complete error output when debugging 100+ test failures.

### [2026-05-22 22:09] via lesson
Always run `uv run pytest tests/ -v --tb=long` as the first diagnostic step when tests fail at scale; the `-q --tb=short` flags obscure whether failures are import/setup errors (which block test discovery) versus assertion failures, making root cause diagnosis impossible.

### [2026-05-22 22:17] via lesson
Always set `PYTHONIOENCODING=utf-8` before running Python scripts with Unicode output, or use `sys.stdout.reconfigure(encoding='utf-8')` in the code itself. This prevents the cp1252 UnicodeEncodeError that crashed check_imports.py when trying to print the ✓ character.

### [2026-05-22 22:20] via lesson
Always address `tool.uv.dev-dependencies` deprecation warnings immediately—they indicate a broken environment that cascades into widespread test failures across the suite. Never assume deprecation warnings are optional cleanup.

### [2026-05-22 22:33] via lesson
Before running the test suite, use grep to search source modules for imported symbols — e.g., `grep 'class ScheduleRunRequest\|def validate_runner_strict' app/dtos/run.py` — to catch missing exports before collection errors halt the entire test run.

### [2026-05-22 22:36] via lesson
Always run `pytest --collect-only` before `pytest tests/` to catch import errors during collection instead of wasting time on the full test suite execution.

### [2026-05-22 22:43] via lesson
Before running commands with environment variables in bash, use inline syntax (`VAR=value command`) or `export` statements instead of `set`, which is cmd.exe syntax and won't affect child processes in bash.

### [2026-05-22 22:45] via lesson
Always run `pytest --tb=long` not `--tb=short` when triaging failures—full tracebacks are essential for diagnosing the root cause across 111+ failures and 19 errors.

### [2026-05-23 04:36] via lesson
Never pipe pytest output through Unix utilities like `tail` in Windows cmd/batch commands — use `findstr` or WSL instead.

### [2026-05-23 04:36] via lesson
Before running pytest against tests/test_auth.py, tests/test_database.py, and tests/test_projects.py, verify MongoDB is running — the 19 ERROR entries (not FAILED) indicate fixture initialization failures from missing service dependencies.
