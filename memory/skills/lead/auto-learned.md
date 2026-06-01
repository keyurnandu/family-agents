# Auto-Learned Lessons — lead

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-23 22:00] via user-correction
Local git operations (git add, git commit, git tag, git stash) are safe. NEVER run git push, git merge, git rebase, git checkout, or git reset --hard without explicit user approval—these publish to remote or can lose uncommitted work.

### [2026-05-24 16:07] via lesson
Before running pytest: (1) Always execute `pytest --collect-only` first to catch import/initialization errors and verify test names exist (e.g., `pytest tests/file.py --collect-only` before `pytest tests/file.py::test_name`). (2) Verify all imported classes, exceptions, and methods actually exist using grep: `grep 'class ClassName\|def method_name' app/module.py`. Check `__init__.py` files don't reference non-existent names. (3) Use `pytest -v --tb=long` (never `-q --tb=short`) to see complete error messages.

### [2026-05-23 20:45] via lesson
Before running pytest, verify infrastructure and configuration: (1) Ensure MongoDB is running on localhost:27017 (check with `mongosh` or Windows Services)—ERROR entries indicate fixture initialization failures from missing dependencies. (2) Verify all settings.ATTRIBUTE_NAME references match your Settings model definition (e.g., MONGODB_URI vs MONGODB_URL) to catch AttributeError at startup. (3) Register custom pytest markers in `pytest.ini` or `pyproject.toml` under `[tool.pytest.ini_options]` with `markers = ["performance", ...]` to avoid PytestUnknownMarkWarning.

### [2026-05-23 08:21] via lesson
Never debug individual test assertions when all tests in a file error identically—it's always a setup/fixture issue. Verify that required input files (like OpenAPI specs or test fixtures) exist and are accessible before investigating test logic.

### [2026-05-23 14:15] via lesson
Before merging code with new model schemas, regenerate the OpenAPI spec to include all response model fields, then run `pytest tests/test_sc3_openapi_runner_contract.py`. Contract tests validate that code implementations match the spec definition—missing spec updates cause all parameterized schema tests to fail with "schema not found" errors.

### [2026-05-23 14:52] via lesson
Always ensure proper async resource cleanup: (1) Close Selenium/Playwright browser instances properly in test teardown using context managers or explicit `driver.quit()`/`browser.close()` in fixtures to prevent "unclosed transport" and "closed pipe" failures. (2) Never assume a ref contains an object with expected methods—add a `typeof` check before calling methods (e.g., `renderTaskRef.current?.cancel?.()`) to prevent "is not a function" errors during async cleanup.

### [2026-05-23 21:50] via lesson
On Windows and in bash: (1) Never use Unix-only commands (bash, tail, head, cat, grep, ls, wc, sed, awk, which, chmod, chown, tee)—use Windows equivalents (cmd /c, Get-Content, type, findstr, dir, Measure-Object, where.exe, icacls). (2) Never use Windows path separators (backslashes like `venv\Scripts\python.exe`) in bash commands; use forward slashes or native Windows syntax instead. (3) Never use Unix-style environment variable syntax (`PYTHONIOENCODING=utf-8`) when invoking PowerShell; use `$env:PYTHONIOENCODING='utf-8'` or set the variable before calling the command. (4) Never include markdown code fences (```) when passing bash commands—strip backticks and verify the command contains only the executable instruction. (5) Before running `uv` commands on Windows, verify uv is installed and in PATH; use `python scripts/script.py` directly as a fallback.

### [2026-05-23 13:00] via lesson
Never run `uv` commands on cloud-synced directories (OneDrive, Google Drive, etc.)—they lock files during background sync, preventing venv cleanup. Move projects to a local directory without spaces. Before running `uv sync`, verify the project directory structure matches the package name in `pyproject.toml`. Always run `uv sync` after environment setup or after modifying critical dependencies.

### [2026-05-22 15:49] via lesson
Always convert enum values to their underlying strings via the `.value` attribute in factory lookups (e.g., `RunnerType.PLAYWRIGHT.value` → `'playwright'`), never `str(enum)` which produces `'EnumType.VALUE'` instead of the registered key.
