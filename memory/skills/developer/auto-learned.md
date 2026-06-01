# Auto-Learned Lessons — developer

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-24 13:35] via user-correction
On Windows, use native tools (cmd.exe, PowerShell) or cross-platform equivalents; never use Unix-only commands (bash, tail, head, grep, sed, awk, which, chmod). Quote file paths containing spaces. For npm tools, use `npm run <script>` or `npx <tool>` for cross-platform compatibility—never direct `node_modules\.bin\` paths with backslashes.

### [2026-05-24 18:27] via lesson
Before git operations: verify repo exists (`git rev-parse --is-inside-work-tree`), check `git status` and `.gitignore` rules before `git add`, verify remote with `git remote -v` before `git push`. Never push/merge/rebase/checkout/reset without explicit approval. Always stage changes and verify with `git status` before committing.

### [2026-05-24 12:58] via lesson
Before running tests, validate all imports: use `python -c "from module import ClassName"` or `node -e "import('./file.js')"`, and grep source code for imported names to verify they exist in target modules. Check `__init__.py` exports match imports and audit for circular dependencies that cascade through test collection.

### [2026-05-24 16:02] via lesson
Before running pytest: use `pytest --collect-only -v` to catch import/setup errors early, validate syntax with `python -m py_compile`, verify all configured plugins in pytest.ini are installed. Use `--tb=long` to reveal full errors. Fix ERRORs (setup/import issues) before FAILUREs (logic problems).

### [2026-05-24 13:04] via lesson
Before running tests: check which test framework is configured (jest vs vitest, pytest) and use correct flags (`vitest --watch=false`, `jest --watchAll=false`). Declare test callbacks `async` when using `await`. Move projects off OneDrive on Windows. Use `&&` not `&` for chaining commands. Start application servers before running integration/smoke tests. For abstract base classes, verify all @abstractmethod implementations exist before instantiation.

### [2026-05-23 22:47] via lesson
When mocking async methods, use `AsyncMock` and await mock calls. Use `vi.useFakeTimers()` with `vi.advanceTimersByTime()` for debounced functions in Vitest. Never nest async/await inside setTimeout; use Promise-based patterns. Always use optional chaining for refs: `renderTaskRef.current?.cancel()`.

### [2026-05-23 22:53] via lesson
Never use Unicode special characters (✓, …, em dashes, smart quotes) in code files; use ASCII equivalents. Copy exact strings between test and component source rather than retyping to preserve special characters.

### [2026-05-24 15:30] via user-correction
Before running `npx vitest run`: (1) validate vite.config.js and setupTests.jsx syntax (unterminated strings, unclosed brackets), use `.jsx` file extensions for JSX files, (2) use DEFAULT reporter (no `--reporter` flag) to see `❯ filename (0 test)` progress indicator for hung files—NEVER use `--reporter=verbose` or `--reporter=dot` for full suites, (3) if timeout fires AFTER all files show ✓, hang is in pool.close() due to pending timers; add globalSetup watchdog: `export default function setup() { const t = setTimeout(() => process.exit(0), 8000); t.unref(); }` to vite.config.js, then add `globalSetup: './vitest.globalSetup.js'` in vite.config.js test block, (4) add `HTMLCanvasElement.prototype.getContext = vi.fn()` in setupTests.jsx to reduce timer leaks, (5) if stuck file hangs alone, probe imports: `node -e "import('./component').catch(e => console.error(e))"` to find module-level side effects (Web Workers, fetch, `new URL(import.meta.url)`)—guard with `if (!import.meta.env.TEST)`, (6) use `--no-coverage` to avoid coverage collection hangs, (7) increase bash timeout to ≥300s.

### [2026-05-23 20:44] via lesson
Resolve all syntax errors (marked by `^` in output) before investigating test timeouts—they prevent execution and cause files to hang. Validate with `python -m py_compile` (Python), `npx eslint` (JavaScript), or inspect unterminated strings, unclosed brackets, incomplete redirects (e.g., `2>` without target file).

### [2026-05-24 11:00] via user-correction
Never run long-running dev servers or interactive tools as EXEC commands (vite, npm start, npm test, flask run, uvicorn, pytest with watch mode, etc.)—they block forever. For dev servers, verify startup with a quick health check: `node -e "require('./src/main')"` or `python -c "from app.main import app"`. For test runners, disable watch mode: Jest: `set CI=true && npm test`, Vitest: `npx vitest run`, pytest: use `--collect-only` first.

### [2026-05-23 13:31] via lesson
Before accessing `Settings` attributes in code or tests, verify they are defined in the source config module (e.g., `app/core/config.py`) with type hints and defaults—missing attributes cause AttributeError cascades through all tests.

### [2026-05-21 17:46] via bash-failure
Before running service-dependent scripts (migrations, database operations), verify the service is running and accessible using service query commands (e.g., `sc query MongoDB`, `Get-Service MongoDB` on Windows) or connectivity tests (e.g., `mongosh` for MongoDB).

### [2026-05-23 14:32] via lesson
Never pass `app` directly to httpx.AsyncClient; use `transport=httpx.ASGITransport(app=app)` for testing ASGI applications.

### [2026-05-22 22:27] via lesson
Never use `is` to compare enum values in tests; use `==` instead to avoid identity mismatches with coerced or dynamically created enum instances.

### [2026-05-23 10:35] via lesson
Before running OpenAPI contract tests, verify all parametrized schema names exist in `spec['components']['schemas']` by inspecting available keys to avoid KeyError.

### [2026-05-24 18:16] via lesson
Before running commands referencing test or source files, verify the file exists with `ls` or `dir` from your current directory to prevent "file not found" errors when paths don't match working directory structure.

### [2026-06-01 08:53] via lesson
Before running `pytest tests/test_us0306_metadata.py`, always verify the file exists using `ls tests/test_us0306_metadata.py` to confirm the path is correct from your current directory.

### [2026-06-01 09:03] via lesson
Never include markdown code fence delimiters (```) when executing bash commands; copy only the command content between the markers.

### [2026-06-01 09:08] via lesson
Never include markdown triple backticks (```) when executing commands in the terminal — strip the backtick syntax and paste only the code content. On Windows systems, use a bash-compatible shell (WSL, Git Bash) rather than Command Prompt, which interprets backticks differently.

### [2026-06-01 09:16] via lesson
Never wrap EXEC:file content in triple-backtick fences. The artifact guard rejects any .py file containing ``` before the approval prompt — no permission dialog will appear. Write raw Python only: the first character of the file must be actual code, never a backtick. Aria's "permissions" explanation is wrong; the guard is the blocker.

### [2026-06-01 09:34] via lesson
Before investigating failed tests, re-run pytest with `--tb=short` to see actual error messages instead of just test names; `-v` alone hides the failure reasons.

### [2026-06-01 09:53] via lesson
Always verify the API endpoint is registered in the router and the URL path matches what the test expects before running tests; 404 responses indicate a missing or misrouted endpoint, not test logic issues.

### [2026-06-01 10:08] via lesson
Always run pytest with `-vv --tb=short` instead of just `-v`; the latter shows test names only, while you need full traceback output to see actual assertion failures and fix the root cause.

### [2026-06-01 10:10] via lesson
Before running `pytest tests/test_us0306_metadata.py` from backend/, verify that app/services/__init__.py exists, or explicitly set PYTHONPATH=.. to resolve module imports from the parent app package.
