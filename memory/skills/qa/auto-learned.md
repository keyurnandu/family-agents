# Auto-Learned Lessons — qa

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-23 22:30] via user-correction
This is a WINDOWS machine. NEVER use Unix-only commands: bash, bash -c, tail, head, cat, grep, ls, wc, sed, awk, which, chmod, chown. Use Windows equivalents: cmd /c, Get-Content -Tail, Get-Content -TotalCount, type, findstr, dir, Measure-Object, PowerShell, where.exe, icacls. For checking if files exist, use `dir` or `if exist`, NOT `ls`. Use Glob tool for file pattern matching to avoid "command not recognized" errors.

### [2026-05-23 20:07] via lesson
Before running or writing tests, verify the source implementation: exception types must match test assertions, method signatures must exist, imported classes must be defined in their source modules, and imported exception classes must exist. Read the actual code first—do not assume test assumptions are correct. This catches mismatches between test expectations and real implementation before wasting time debugging.

### [2026-05-23 05:21] via lesson
Before running `git add path1 path2...`, verify all paths exist in the working tree using `git status` or Glob tool—non-existent files cause git add to fail silently or with exit(1).

### [2026-05-23 05:37] via lesson
Before running `git commit`, always stage changes first with `git add` or use `git commit -a` to stage and commit in one command. Untracked or unstaged changes won't be included without explicit staging.

### [2026-05-22 11:10] via lesson
Before running Playwright-dependent tests, run `playwright install` to ensure browser binaries are available—missing browsers cause runner initialization failures instead of obvious setup errors.

### [2026-05-21 18:27] via bash-failure
Always verify `uv` is installed and in PATH before running `uv run` commands on Windows—check with `uv --version` or `where uv` first.

### [2026-05-23 14:26] via lesson
Always run `npm install` before executing test commands like `vitest run` to ensure testing dependencies (e.g., `@testing-library/react`) are installed in node_modules.

### [2026-05-22 11:03] via lesson
On Windows, never skip subprocess cleanup in timeout tests—explicitly close or context-manage all asyncio transports to prevent unraisable exceptions from masking actual test failures.

### [2026-05-23 20:14] via lesson
Always run pytest with `--tb=long` instead of `--tb=short` when you see ERROR entries—the short format truncates AttributeError and traceback details needed to identify the root cause of setup or import failures.

### [2026-05-23 20:17] via lesson
On Windows, keep projects out of problematic paths: never run pytest from OneDrive or protected directories (use `C:\Users\username\code\` instead to avoid PermissionError and file locking), and avoid paths with spaces when using Vitest (e.g., 'OneDrive - Adobe')—both cause cryptic failures during test execution or transform phases.

### [2026-05-23 14:54] via lesson
Before running Vitest integration tests, verify fetch mocks are configured for all API endpoints—missing mocks cause unexpected failures ("Failed to load documents") instead of obvious setup errors.

### [2026-05-23 13:23] via lesson
Before running the full test suite with API response types, verify the OpenAPI contract implementation is complete—check that RunnerType enum and runner field are defined on all required response types (TriggerRunResponse, RunStatusResponse, RunSummary).

### [2026-05-22 11:18] via lesson
Verify RunnerFactory tests pass before running dependent tests—factory test failures (test_factory_raises_on_unknown_runner_type, test_factory_is_configurable_via_settings) cascade into RunnerNotInitializedError downstream.

### [2026-05-23 20:23] via lesson
Always run `uv run pytest tests/test_runner_factory.py -x --tb=short` on a single test file when facing truncated AttributeError messages across multiple tests. Full-suite runs cascade the initial failure and truncate error output, hiding the root cause.

### [2026-05-24 01:38] via lesson
Always add `--timeout=60000` when running `vitest run` to fail fast on hanging tests instead of waiting for the 120s default timeout. This prevents blocking test runs and surfaces slow/frozen tests immediately.

### [2026-05-24 12:54] via lesson
Never pass unsupported flags to Vitest—always verify flag names using `vitest run --help` before executing test commands. The `--timeout` flag caused a CACError because it's not a valid Vitest CLI option.

### [2026-05-24 13:23] via lesson
Always specify a higher test timeout for vitest (e.g., `vitest run --reporter=verbose --test-timeout=300000`) since PdfViewer.test.jsx hangs past the default 120s limit.
