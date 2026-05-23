# Auto-Learned Lessons — qa

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-23 22:30] via user-correction
This is a WINDOWS machine. NEVER use Unix-only commands: bash, bash -c, tail, head, cat, grep, ls, wc, sed, awk, which, chmod, chown. Use Windows equivalents: cmd /c, Get-Content -Tail, Get-Content -TotalCount, type, findstr, dir, Measure-Object, PowerShell, where.exe, icacls. For checking if files exist, use `dir` or `if exist`, NOT `ls`.

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

### [2026-05-22 15:39] via lesson
Always verify the test file path exists before running pytest; use `Glob` or `ls tests/` to confirm files are in the expected location. This prevents 'file or directory not found' errors that waste time.

### [2026-05-22 22:42] via lesson
Always verify that imported classes in test files actually exist in their source modules before running pytest—ScheduleRunRequest must be defined in app.dtos.run or imports will fail during collection. Check the source module first to confirm the class is exported before investigating test logic.

### [2026-05-22 22:45] via lesson
Always use `--tb=long` when running `pytest` on a full test suite with failures; `--tb=short` hides the actual error messages needed to identify whether failures are from a common root cause (like a missing import or config issue) versus isolated test problems.

### [2026-05-23 04:59] via lesson
Before running `git add` with multiple file paths, verify each file exists using the Glob tool or `ls` command. Always check that paths are relative to the repository root to prevent pathspec mismatch errors that block commits.

### [2026-05-23 05:00] via lesson
Always verify the exact file path using `ls` or `find` against the actual directory structure before staging changes to `.github/workflows/` configuration files. Never commit with an assumed path for CI workflows without confirming the location exists first.

### [2026-05-23 05:01] via lesson
Never use Unix commands like `ls` in CI/CD scripts without specifying bash explicitly — this failed because the process fell back to cmd.exe instead of running in bash. Always wrap with `bash -c` or verify the shell environment is active first.

### [2026-05-23 05:03] via lesson
Always verify exact file paths in chained bash commands (`&&`) before execution—the command used `tests\conft` instead of the actual `tests\conftest.py`, causing the entire verification chain to exit(1).

### [2026-05-23 05:10] via lesson
Never use `git bash` to run shell commands; `git bash` is not a valid git command—use the Bash tool directly instead.

### [2026-05-23 05:10] via lesson
Never use Unix commands like `ls` on Windows systems; use the Glob tool for file pattern matching to avoid "command not recognized" errors.

### [2026-05-23 05:10] via lesson
Before running `git add` with specific file paths, verify those files exist in the repository using the Glob tool, since attempting to add non-existent files fails silently.
