# Auto-Learned Lessons — lead

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-23 22:30] via user-correction
On WINDOWS machines: Never use Unix-only commands (bash, tail, head, cat, grep, ls, wc, sed, awk, which, chmod, chown, tee). Use Windows equivalents (cmd /c, Get-Content -Tail, type, findstr, dir, Measure-Object, PowerShell, where.exe, icacls). Set PYTHONIOENCODING=utf-8 for Python scripts with Unicode output. Never pipe pytest through Unix utilities—use WSL 2, Docker, or PowerShell instead.

### [2026-05-23 22:00] via user-correction
Local git operations (git add, git commit, git tag, git stash) are safe. NEVER run git push, git merge, git rebase, git checkout, or git reset --hard without explicit user approval—these publish to remote or can lose uncommitted work.

### [2026-05-23 15:55] via lesson
Before running pytest: (1) Always execute `pytest --collect-only` first to catch import/initialization errors that block the entire suite. (2) Use `pytest -v --tb=long` (never `-q --tb=short`) to see complete error messages. (3) Run tests for changed modules first (e.g., `pytest tests/test_runner*.py`) to isolate failures before the full suite.

### [2026-05-23 17:04] via lesson
Before running pytest, verify all imported classes, exceptions, and methods actually exist in their source modules. Use grep: `grep 'class ClassName\|def method_name' app/module.py`. Check that `__init__.py` files don't reference non-existent names. This catches ImportError during collection before test execution wastes time.

### [2026-05-23 13:00] via lesson
Never run `uv` commands on cloud-synced directories (OneDrive, Google Drive, etc.)—they lock files during background sync, preventing venv cleanup. Move projects to a local directory without spaces. Before running `uv sync`, verify the project directory structure matches the package name in `pyproject.toml`. Always run `uv sync` after environment setup or after modifying critical dependencies.

### [2026-05-23 14:15] via lesson
Before merging code with new model schemas, regenerate the OpenAPI spec to include all response model fields, then run `pytest tests/test_sc3_openapi_runner_contract.py`. Contract tests validate that code implementations match the spec definition—missing spec updates cause all parameterized schema tests to fail with "schema not found" errors.

### [2026-05-23 04:36] via lesson
Before running pytest, verify MongoDB is running on localhost:27017 (check with `mongosh` or Windows Services). ERROR entries (not FAILED) indicate fixture initialization failures from missing service dependencies. Resolve infrastructure errors before debugging individual test failures.

### [2026-05-23 15:46] via lesson
Never include markdown code fences (```) when passing bash commands to the Bash tool—they're formatting syntax, not executable code. Always strip backticks and verify the command string contains only the executable instruction.

### [2026-05-22 15:49] via lesson
Always convert enum values to their underlying strings via the `.value` attribute in factory lookups (e.g., `RunnerType.PLAYWRIGHT.value` → `'playwright'`), never `str(enum)` which produces `'EnumType.VALUE'` instead of the registered key.

### [2026-05-23 13:22] via lesson
Before running pytest with custom markers (e.g., `-m performance`), register them in `pytest.ini` or `pyproject.toml` under `[tool.pytest.ini_options]` with `markers = ["performance", "isolation", "cleanup", "browser"]` to avoid PytestUnknownMarkWarning.

### [2026-05-22 10:51] via lesson
Always ensure Selenium/Playwright browser instances are properly closed in test teardown using context managers or explicit `driver.quit()`/`browser.close()` in fixtures to prevent "unclosed transport" and "closed pipe" failures.

### [2026-05-23 17:06] via lesson
Before committing changes to method signatures in factory classes and runners, verify that all test calls match the new parameters—mismatched `__init__` parameters and factory method arguments must be caught before tests run.

### [2026-05-23 14:52] via lesson
Never assume a ref contains an object with expected methods. Add a `typeof` check before calling methods (e.g., `renderTaskRef.current?.cancel?.()`) to prevent "is not a function" errors during async cleanup.

### [2026-05-23 16:22] via lesson
Always verify output redirection paths are complete and valid before executing commands (e.g., `> docs/test_results.txt` not `> docs/s` which appears truncated).

### [2026-05-23 08:21] via lesson
Never debug individual test assertions when all tests in a file error identically—it's always a setup/fixture issue. Verify that required input files (like OpenAPI specs or test fixtures) exist and are accessible before investigating test logic.

### [2026-05-21 17:44] via bash-failure
Before running `uv run` commands on Windows, verify uv is installed and in PATH. Use `python scripts/script.py` directly as a fallback. Similarly, verify binaries exist in PATH using `where mongod` before invoking them.

### [2026-05-22 22:43] via lesson
When setting environment variables in bash, use inline syntax (`VAR=value command`) or `export` statements, never Windows `set` command which won't affect child processes in bash.

### [2026-05-23 20:45] via lesson
Before running pytest, use grep to verify all settings.ATTRIBUTE_NAME references match your Settings model definition (e.g., MONGODB_URI vs MONGODB_URL) to catch AttributeError at startup. This prevents the entire test suite from erroring out on configuration mismatches.

### [2026-05-23 21:35] via lesson
Always verify that scripts exist at their referenced paths using `Glob` or `Read` before executing them, especially in OneDrive directories with spaces where path handling can fail silently. Check the working directory and relative path relationships first.

### [2026-05-23 21:45] via lesson
Never execute markdown code fence markers (```) as part of bash commands; strip the opening ```powershell and closing ``` before running any copied code.

### [2026-05-23 21:45] via lesson
Before pasting code from documentation or examples into the bash tool, verify the command starts with actual executable syntax, not markdown formatting delimiters.

### [2026-05-23 21:50] via lesson
Never use Windows path separators (backslashes like `venv\Scripts\python.exe`) in bash commands; use forward slashes or the native Windows command syntax instead, as bash interprets backslashes as escape characters.

### [2026-05-23 21:50] via lesson
Never use Unix-style environment variable syntax (`PYTHONIOENCODING=utf-8`) when invoking PowerShell; use `$env:PYTHONIOENCODING='utf-8'` or set the variable before calling the command.

### [2026-05-23 21:50] via lesson
Before running piped bash commands, ensure the command is syntactically complete—your command ended with `| 2>&1 |`, indicating a truncated or malformed pipe chain.
