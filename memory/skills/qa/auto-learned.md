# Auto-Learned Lessons — qa

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-21 18:13] via bash-failure
Before running integration tests after code changes, verify that all test method calls match the current implementation signatures — here, `RunnerFactory.get_runner()` changed to accept 1 argument but 15 tests still called it with 2 (runner type + config).

### [2026-05-21 18:27] via bash-failure
Always verify `uv` is installed and in PATH before running `uv run` commands on Windows—check with `uv --version` or `where uv` first.

### [2026-05-22 11:03] via lesson
Never skip subprocess cleanup in timeout tests on Windows — explicitly close or context-manage all asyncio transports to prevent unraisable exceptions from masking actual test failures.

### [2026-05-22 11:10] via lesson
Before running pytest on Playwright-dependent tests, run `playwright install` to ensure browser binaries are available—missing browsers cause runner initialization failures instead of obvious setup errors.

### [2026-05-22 11:18] via lesson
Always verify RunnerFactory tests pass before running dependent tests—factory tests failing (test_factory_raises_on_unknown_runner_type, test_factory_is_configurable_via_settings) cascade into RunnerNotInitializedError downstream.

### [2026-05-22 11:25] via lesson
Before running tests, grep the implementation to verify exception types and method signatures match test assertions—this would have caught `RunnerNotFoundError` vs `ValueError` and the missing `create_default()` method.
