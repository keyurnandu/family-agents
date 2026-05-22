# Auto-Learned Lessons — developer

Lessons captured automatically from failures, corrections, and retrospectives.

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
