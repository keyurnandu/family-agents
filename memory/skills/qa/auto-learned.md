# Auto-Learned Lessons — qa

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-23 22:30] via user-correction
This is a WINDOWS machine. NEVER use Unix-only commands: bash, bash -c, tail, head, cat, grep, ls, wc, sed, awk, which, chmod, chown. Use Windows equivalents: cmd /c, Get-Content, type, findstr, dir, Measure-Object, where.exe, icacls. Use Glob tool for file pattern matching. Keep projects out of OneDrive and protected directories (use `C:\Users\username\code\` instead)—both cause PermissionError and file locking. On Windows, never skip subprocess cleanup in timeout tests—explicitly close or context-manage all asyncio transports to prevent unraisable exceptions. Always verify `uv` is installed and in PATH before running `uv run` commands; check with `uv --version` or `where uv` first.

### [2026-05-23 20:07] via lesson
Before running or writing tests, verify the source implementation: exception types must match test assertions, method signatures must exist, imported classes must be defined in their source modules, and imported exception classes must exist. Read the actual code first—do not assume test assumptions are correct. This catches mismatches between test expectations and real implementation before wasting time debugging.

### [2026-05-23 05:37] via lesson
Before running `git add` or `git commit`: verify file paths exist with `git status` or Glob tool, check if paths match `.gitignore` patterns (use `git add -f` if ignored but should be committed), and always stage changes with `git add` or `git commit -a` before committing—untracked or unstaged changes won't be included without explicit staging.

### [2026-05-23 14:26] via lesson
Always run `npm install` before executing test commands like `pytest` or `vitest` to ensure all testing dependencies are installed in node_modules. Also run `playwright install` before Playwright-dependent tests to ensure browser binaries are available—missing browsers cause runner initialization failures instead of obvious setup errors.

### [2026-05-23 20:14] via lesson
Always run pytest with `--tb=long` instead of `--tb=short` when you see ERROR entries—the short format truncates AttributeError and traceback details needed to identify root causes. When facing truncated errors across multiple tests, run a single test file with `uv run pytest tests/test_file.py -x --tb=short` to isolate the issue and see full output.

### [2026-05-23 14:54] via lesson
Before running Vitest integration tests or full test suites with API response types, verify fetch mocks are configured for all endpoints and the OpenAPI contract implementation is complete (check that RunnerType enum and runner field are defined on all required response types). Verify RunnerFactory tests pass first (`uv run pytest tests/test_runner_factory.py -x --tb=short`)—factory failures cascade into downstream tests.

### [2026-05-24 15:00] via user-correction
For `npx vitest run`: NEVER use `--reporter=dot` or `--reporter=verbose` for full suite runs—both suppress the `❯ filename (0 test)` progress indicator needed to diagnose hangs. Use the DEFAULT reporter (no flag): `npx vitest run`. Reserve non-default reporters for single-file runs only: `npx vitest run SomeFile.test.jsx --reporter=verbose`. Always use `--test-timeout=300000` for longer-running tests. When all tests show ✓ but the process hangs with no 'Test Files N passed' summary, the hang is in vitest v2's pool.close()—add a globalSetup watchdog. Create `vitest.globalSetup.js`: `const WATCHDOG_MS = 8000; export default function setup() { const t = setTimeout(() => { process.exit(0); }, WATCHDOG_MS); t.unref(); }` and add `globalSetup: './vitest.globalSetup.js'` to vite.config.js test block.

### [2026-05-24 18:14] via lesson
Before running `pytest tests/test_file.py::ClassName`, verify the file exists using Glob tool and the class exists in that file—omit the `::ClassName` selector to list available tests first if uncertain. Always confirm file paths after `cd` commands instead of assuming directory structure.

### [2026-05-24 15:46] via lesson
Never include markdown code block delimiters (triple backticks) in shell commands—they'll be interpreted as literal command names and fail on execution. Strip markdown formatting syntax before pasting any command.

### [2026-06-01 08:50] via lesson
Before running pytest after `cd backend`, verify the relative path is correct from the backend directory. Instead, run pytest from the project root without changing directories.

### [2026-06-01 09:02] via lesson
Always verify the test file path exists before running pytest, especially after directory changes with `cd` — use `test -f tests/test_us0306_metadata.py` to confirm the relative path is valid from the new working directory.

### [2026-06-01 09:09] via lesson
Always verify the test file exists at the specified path relative to your current working directory before running pytest, especially after using `cd` — run `ls tests/test_us0306_metadata.py` first or use an absolute path from the project root.

### [2026-06-01 09:19] via lesson
Always verify SQLAlchemy model parameter names against the class definition before running tests — Document doesn't accept 'file_size' as a kwarg, causing cascading test failures.

### [2026-06-01 09:28] via lesson
Always check that model schema definitions match all fields referenced in instantiation before running tests—the Document class is missing 'file_size'. Before testing parameter validation, verify FastAPI endpoints use Path validators to return 422 for invalid types instead of 404.

### [2026-06-01 09:34] via lesson
Always add `--tb=short` to your pytest command when investigating failures; `-v` alone shows test names but not the assertion errors needed to debug. Next time, run: `pytest tests/test_us0306_metadata.py -v --tb=short` to capture full error tracebacks.

### [2026-06-01 09:43] via lesson
Always run `pytest -vv` instead of plain `pytest` to capture full failure details and assertion messages—the test summary alone doesn't show why tests are actually failing.

### [2026-06-01 09:50] via lesson
Always verify the backend endpoint is implemented and the route configuration matches the test's expected path before running integration tests—a 404 response indicates a missing or misconfigured endpoint, not a test logic issue.

### [2026-06-01 10:04] via lesson
Before running endpoint integration tests, verify the route is registered and accessible by checking the router configuration or making a manual test request to the endpoint. The 404 errors indicate the `/documents/{id}` endpoint isn't implemented yet, so tests will fail until the handler exists.
