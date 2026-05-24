# Auto-Learned Lessons — developer

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-23 22:30] via user-correction
This is a WINDOWS machine. NEVER use Unix-only commands: bash, bash -c, tail, head, cat, grep, ls, wc, sed, awk, which, chmod, chown. Use Windows equivalents: cmd /c, Get-Content -Tail, Get-Content -TotalCount, type, findstr, dir, Measure-Object, PowerShell, where.exe, icacls. For bash scripts, validate all commands are cross-platform before execution.

### [2026-05-23 22:00] via user-correction
Local git operations (git add, git commit, git tag, git stash) are fine — they're just local checkpoints. NEVER run git push, git merge, git rebase, git checkout, or git reset --hard without explicit user approval — these publish to remote or can lose uncommitted work.

### [2026-05-22 20:54] via lesson
Always verify the directory is a git repository before running any git command. Use `git rev-parse --is-inside-work-tree` to confirm, or check for `.git` directory. Never chain multiple git commands if the initial repo check fails.

### [2026-05-23 14:24] via lesson
Before running pytest after code changes, validate all application imports resolve with a quick `python -c "from app.module import ClassName"` test. Import errors cascade through module initialization and fail all test discovery—fix imports before debugging test logic.

### [2026-05-23 05:51] via lesson
Always use `pytest --collect-only` before running the full test suite to catch collection errors (imports, fixtures, setup) early. This distinguishes setup/import failures from actual test failures and prevents wasted time on invalid test runs.

### [2026-05-22 18:22] via lesson
When seeing widespread pytest failures across multiple modules, always run with `--tb=long` instead of `--tb=short` to reveal full error messages. Short traceback hides root causes of cascading failures.

### [2026-05-23 04:35] via lesson
Before debugging test failures, fix all test ERRORs first—they indicate setup/import/environment issues that prevent tests from running, whereas FAILUREs are logic problems that depend on the environment being correct.

### [2026-05-21 17:46] via bash-failure
Before running service-dependent scripts (migrations, database operations), verify the service is running and accessible. Use service query commands (e.g., `sc query MongoDB`, `Get-Service MongoDB`) or test connectivity (e.g., `mongosh` for MongoDB) before execution.

### [2026-05-23 10:35] via lesson
Before running OpenAPI contract tests, verify all parametrized schema names exist in `spec['components']['schemas']` by inspecting available keys to avoid KeyError. Add debug output printing available schema names when tests fail with collection errors.

### [2026-05-23 04:56] via lesson
Always quote file paths containing spaces in bash commands — paths like "OneDrive - Adobe" require quoting: `dir "tests\test_openapi*"` instead of `dir tests\test_openapi*`.

### [2026-05-23 11:38] via lesson
When writing Windows temporary files in PowerShell, use `$env:TEMP` with `[System.IO.Path]::Combine()` and execute with `powershell -ExecutionPolicy Bypass -File` to bypass permission constraints—the user's temp folder is always writable.

### [2026-05-23 13:00] via lesson
Always use `unittest.mock.AsyncMock` when mocking async methods like `browser_context.close()` in Playwright/async tests, or explicitly await the mock calls to prevent "coroutine was never awaited" RuntimeWarning failures during teardown.

### [2026-05-23 14:29] via lesson
Before writing tests, check which test framework is configured in package.json (jest vs vitest). Tests using jest.fn() syntax fail in Vitest—convert to vi.fn() or add jest globals in vitest.config.js.

### [2026-05-23 14:35] via lesson
Always declare test function callbacks as async when they use await: change `test('name', () => {` to `test('name', async () => {` to prevent transform errors before execution.

### [2026-05-23 13:16] via lesson
Before instantiating test doubles that inherit from abstract base classes, verify all `@abstractmethod` implementations are present by checking the parent ABC's method signatures. The `TypeError: Can't instantiate abstract class` error lists missing methods—implement or mock every one before running tests.

### [2026-05-23 13:31] via lesson
Before accessing any `Settings` attribute in code or tests, verify it's defined in `app/core/config.py` with a type hint and default value — referencing undefined attributes like `DEBUG` causes AttributeError cascading through all tests.

### [2026-05-22 22:27] via lesson
Never use `is` to compare enum values in tests; use `==` instead to avoid identity mismatches with coerced or dynamically created enum instances.

### [2026-05-22 22:27] via lesson
Never use Unicode special characters like ✓ in print statements without encoding verification — use ASCII alternatives on Windows where console encoding defaults to cp1252.

### [2026-05-23 15:52] via lesson
Never use em dashes (–) or smart quotes in Python files; replace them with standard ASCII characters like regular hyphens (-) and straight quotes ("). Also validate Python syntax with `python -m py_compile` before running pytest.

### [2026-05-23 14:32] via lesson
Never pass `app` directly to httpx.AsyncClient; use `transport=httpx.ASGITransport(app=app)` for testing ASGI applications. Replace `httpx.AsyncClient(app=app)` with `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))`.

### [2026-05-23 15:13] via lesson
Before running remote git operations like `git push` or `git ls-remote`, verify the remote exists with `git remote -v` to avoid fatal authentication errors.

### [2026-05-23 20:01] via lesson
Before running `git add` on multiple paths, check `.gitignore` with `git check-ignore` or use `git status` to verify target files aren't ignored, or be prepared to use `git add -f` if intentional.

### [2026-05-23 16:44] via lesson
Always grep for imported exception names in their source files before running tests: `grep 'ExceptionName' app/services/module/exceptions.py` catches import mismatches instantly. Validate all names in `__init__.py` imports exist in target modules before test execution.

### [2026-05-23 17:15] via lesson
Before running tests, grep the source code for method signatures (parameter names, argument counts) to verify they match test expectations. This catches API mismatches immediately instead of after test execution.

### [2026-05-21 18:54] via bash-failure
Always check for Unix-specific commands (`tail`, `head`, `sed`, etc.) in test code and fixtures when developing on Windows; replace them with cross-platform Python alternatives or add platform detection.

### [2026-05-23 13:47] via lesson
Before running pytest on Windows from project paths on OneDrive, move the project to a local directory to avoid PermissionError during pytest's temporary directory cleanup.

### [2026-05-23 13:48] via lesson
Always activate the virtual environment with `venv\Scripts\activate` on Windows before running pytest, rather than invoking `venv\Scripts\python.exe` directly, to avoid path resolution errors.

### [2026-05-23 13:46] via lesson
Always use `&&` instead of `&` when chaining dependent setup commands—the `&` operator runs commands in parallel, causing execution order issues. Never leave pip install commands incomplete (specify the full requirements file path).

### [2026-05-23 20:24] via lesson
Before running pytest, verify all imports in `__init__.py` files actually exist in their source modules — `_register_defaults` is missing from factory.py, causing collection failures across all test files.

### [2026-05-23 20:27] via lesson
Before running vitest, scan test matchers for typos (e.g., `toBeInT` should be `toBeInTheDocument`) since incomplete matcher names cause syntax errors and cascading test timeouts.

### [2026-05-23 20:29] via lesson
Before running cleanup commands, always verify they're written for the correct shell and are syntactically complete; the Windows batch syntax `for /d /r` is invalid in bash and the incomplete command caused the timeout.

### [2026-05-23 20:35] via lesson
Always resolve syntax errors (marked by `^` in output) before investigating test timeouts—they prevent test execution and cause the entire file to hang.

### [2026-05-23 20:40] via lesson
Before running `npx vitest run`, always validate syntax with `npx eslint src/__tests__/*.jsx` to catch parse errors that cause test timeouts and prevent actual test execution. Syntax errors in test files create timeout failures that mask the real problems.

### [2026-05-23 20:44] via lesson
Always verify cross-platform command compatibility — `head` doesn't exist on Windows, so avoid Unix-specific commands when running pytest via `venv\Scripts\python.exe`.

### [2026-05-23 20:44] via lesson
Never execute incomplete bash redirects — the command `pytest tests/ ... 2>` is missing the stderr destination file, causing a syntax error.

### [2026-05-23 21:35] via lesson
Before running `venv\Scripts\python.exe scripts\check_imports.py`, verify the file exists with `ls scripts/` and check the working directory is correct with `pwd`.

### [2026-05-23 21:50] via lesson
Always run `pytest -v` instead of `-q` when debugging collection errors; the quiet flag suppresses the actual error messages that reveal what's failing in `test_sb2_runner_config_wiring.py` and `test_sc3_openapi_runner_contract.py`.

### [2026-05-23 21:54] via lesson
Before running pytest, validate test files with `python -m py_compile` to catch syntax errors—the invalid em-dash (U+2014) and markdown backticks show documentation was pasted directly into code instead of being quoted or placed in docstrings.

### [2026-05-23 22:01] via lesson
Before running tests with `@patch()` decorators, verify that every patched attribute exists in its target module—`test_sb2_runner_config_wiring.py` failed because `update_run_status` is missing from `app.worker.tasks`.

### [2026-05-23 22:01] via lesson
Never run `pytest -m smoke` without starting the application server first—24 smoke tests failed with import errors and unreachable endpoints because the FastAPI server wasn't responding.

### [2026-05-23 22:07] via lesson
Always verify that all imported names are properly exported in their source module's `__init__.py` file before running tests, and audit for circular import chains between `app.models` and `app.services` to prevent cascading collection errors.

### [2026-05-23 23:30] via user-correction
Never use `npx` to run locally installed tools — `npx` re-resolves and potentially downloads the package every time, causing 30-60s+ delays especially on OneDrive-synced paths. Use `node_modules\.bin\<tool>` directly (e.g. `node_modules\.bin\eslint src/`) or `npm run <script>` if the tool has a package.json script defined.

### [2026-05-24 10:00] via user-correction
Never run long-running dev servers (`vite`, `vite dev`, `npm start`, `npm run dev`, `flask run`, `uvicorn`, `python manage.py runserver`, etc.) as EXEC:bash commands — they block the terminal indefinitely and never return. To verify a frontend build works, use `vite build` (exits after building). To verify a server starts, use a quick health check like `node -e "require('./src/main')"` or `python -c "from app.main import app"`. Dev servers are for the USER to run manually in a separate terminal.

### [2026-05-24 11:00] via user-correction
Never run `npm test` or `npx jest` without disabling watch mode — Jest starts in interactive watch mode by default, waits for keystrokes, and blocks forever. Always use one of these instead:
- Jest: `set CI=true && npm test -- --verbose` (CI=true disables watch mode)
- Jest explicit: `npm test -- --watchAll=false --verbose`
- Vitest: `node_modules\.bin\vitest run --reporter=verbose` (`run` subcommand exits after tests complete)
The `2>&1` redirect in `npm test -- --reporter=verbose 2>&1` does NOT prevent watch mode — it only redirects stderr, the process still blocks waiting for input.

### [2026-05-23 22:11] via lesson
Never use `npx` to run locally installed tools — invoke them directly via `./node_modules/.bin/<tool>` to ensure you're using the exact version specified in your project dependencies.

### [2026-05-23 22:14] via lesson
Always check for syntax errors before running tests with `vitest run` — the parse error at line 60 cascaded into 14 test failures and wasted 67 seconds. Fix source code syntax first, then rerun the test suite.

### [2026-05-23 22:14] via lesson
Never pipe to `tail` in Windows bash commands without verifying Unix tools are available; replace with Windows alternatives like `powershell -Command "... | Select-Object -Last 20"` or remove the filter.

### [2026-05-23 22:14] via lesson
Before running bash commands containing Unix utilities (`tail`, `head`, `grep`), check the environment platform or use cross-platform alternatives compatible with both Windows and Unix.

### [2026-05-23 22:16] via lesson
Before running `pytest --collect-only`, verify that `_execute_run_test_suite_task` actually exists in `app.worker.tasks` using grep—ImportError during collection means the function doesn't exist in the target module.

### [2026-05-23 22:16] via lesson
Never retry `pytest -q` after `pytest --collect-only` fails with ImportError—check if the function was removed/renamed from `app.worker.tasks` and update the import in `tests/test_worker.py` first.

### [2026-05-23 22:21] via lesson
Never ignore syntax errors in test output—the caret (^) on line 60 indicates the actual problem preventing tests from running, not just the timeout. Fix the syntax error in the test file first before investigating test timeouts.

### [2026-05-23 22:26] via lesson
Never end a bash command with a bare output descriptor like `1` — always use complete redirect syntax `1> filename` or `2> filename` with both the operator and target file.

### [2026-05-23 22:38] via lesson
Never mix Unix git commands with Windows CLI tools like `findstr` and `2>nul`; use `grep` and `2>/dev/null` for cross-platform compatibility or explicitly target your platform.

### [2026-05-23 22:40] via lesson
Always grep the exceptions module to verify imported classes exist before running `pytest --collect-only`—this catches import errors early in the test discovery phase.

### [2026-05-23 22:41] via lesson
Before running pytest, grep test files for imports from modules you've changed and verify they exist: `grep -r 'RunnerConfig' tests/` to catch stale imports before collection fails.

### [2026-05-23 22:44] via lesson
Before running `pytest`, grep the exceptions module to verify all imported exception classes exist—this would have caught `RunnerCrashError` missing from `app/services/runner/exceptions.py`.

### [2026-05-23 22:45] via lesson
Never nest async/await inside setTimeout; use Promise.all().then() pattern instead. Always run tests via node_modules/.bin/<tool> directly, never npx.

### [2026-05-23 22:46] via lesson
Before running pytest, validate that all test imports (like `RunResult` from `base_runner.py`) actually exist in their source modules. Check source files match test expectations before test execution.

### [2026-05-23 22:47] via lesson
Always use `vi.useFakeTimers()` when testing debounced functions in Vitest—advance time with `vi.advanceTimersByTime()` instead of waiting for real delays. This prevents the 5000ms timeout failures seen in PdfSearch debounce tests where actual debounce waits exceed the test timeout.

### [2026-05-23 22:53] via lesson
Always copy-paste text strings with special characters (like ellipsis …) between test and component source rather than retyping — the ellipsis character and three dots look identical but will fail `getByPlaceholderText` assertions.

### [2026-05-23 23:00] via lesson
Never call methods on refs without optional chaining or guards — use `renderTaskRef.current?.cancel()` instead of `renderTaskRef.current.cancel()` to prevent "is not a function" errors.

### [2026-05-23 23:01] via lesson
Always use `node_modules/.bin/<tool>` directly instead of `npx` when running locally installed development tools, as this ensures correct versioning and avoids npx initialization overhead.

### [2026-05-23 23:04] via lesson
Always use node_modules/.bin/<tool> directly instead of npx to ensure consistent, predictable execution and avoid unexpected version resolution issues. This is especially critical when running test suites where version consistency directly impacts test results.

### [2026-05-24 01:08] via lesson
Before running vitest with --reporter=verbose through Bash, set an explicit timeout parameter (e.g., `timeout: 300000`) instead of relying on the default 120s limit. Verbose test output commonly exceeds the default timeout, so always account for slower execution upfront.

### [2026-05-24 09:44] via lesson
Always use `npx vitest --version` instead of `node_modules\.bin\vitest --version` — backslash paths don't resolve in Windows bash shells.

### [2026-05-24 09:44] via lesson
Never invoke `node_modules\.bin\vitest run` with backslashes directly — use `npx vitest run` for cross-platform shell compatibility.

### [2026-05-24 11:18] via lesson
Always use `npx vitest` instead of `node_modules/.bin/vitest` — `npx` handles cross-platform path differences automatically, whereas direct `.bin/` paths fail on Windows. Before running Node CLI tools, check if `npx` can invoke them instead.

### [2026-05-24 12:22] via lesson
Always check that test cleanup methods (like `cancel()`) are actually implemented before calling them. Missing methods cause vitest to hang beyond the 120s bash timeout.

### [2026-05-24 12:29] via lesson
Always add `--timeout` or remove `--reporter=verbose` when running full test suites with `npx vitest run`, as verbose output causes the 120s default limit to be exceeded.

### [2026-05-24 12:34] via lesson
Before running `npx vitest run` on integration test suites, use `--reporter=dot` instead of `--reporter=verbose` or increase the timeout above 120s to avoid timeout failures on slow test execution.

### [2026-05-24 12:46] via lesson
Always increase the Bash timeout beyond 120s when running `vitest run`, or first debug why PdfViewer.test.jsx hangs during initialization (shows "0 test" in progress).

### [2026-05-24 12:52] via lesson
Always name files containing JSX with `.jsx` or `.tsx` extensions when using Vitest/Vite, as the import-analysis plugin requires correct file extensions to parse JSX syntax. Rename `src/setupTests.js` to `src/setupTests.jsx` before running tests.

### [2026-05-24 12:58] via lesson
Before running test or build commands, read vite.config.js to validate syntax—unterminated strings cause esbuild failures that are expensive to debug after the fact.

### [2026-05-24 13:00] via lesson
Always validate vite.config.js for syntax errors (unterminated strings, debug comments) before running `npx vitest` or build commands—check the file content at the error line number first.

### [2026-05-24 13:01] via lesson
Always check vite.config.js for syntax errors (unterminated strings, malformed code) before running vitest, since config load failures block all test execution regardless of test code validity.

### [2026-05-24 13:04] via lesson
Always verify the test framework (Jest vs Vitest) before passing CLI flags—Vitest uses `--watch=false`, not Jest's `--watchAll=false`.

### [2026-05-24 13:05] via lesson
Before running vitest commands, check vite.config.js for syntax errors (unterminated strings, unclosed brackets) as esbuild errors at startup prevent any tests from running. Use a syntax validator or carefully review recent changes to the config file first.

### [2026-05-24 13:07] via lesson
Before running npm test, ensure vite.config.js contains only valid JavaScript syntax with proper comment delimiters (// or /* */)—never add plain-text strings outside of quoted/commented code.

### [2026-05-24 13:09] via lesson
Always validate syntax in vite.config.js (especially quote balance for string literals) before running vitest—unterminated strings will immediately fail config parsing during test startup.

### [2026-05-24 13:10] via lesson
Always validate setupTests.jsx for syntax errors before running `npx vitest run`—unterminated string literals in setup files fail the entire test transform pipeline.

### [2026-05-24 13:16] via lesson
When `npx vitest run` times out and partial output shows `❯ SomeFile.test.jsx (0 test)` while other files show ✓: the file is STUCK AT MODULE LOAD TIME — no tests ran at all. This is NEVER a test logic problem. Fallback isolation strategy: (1) Run the stuck file alone: `npx vitest run SomeFile.test.jsx`. (2) If it still hangs, probe the component it imports: `node --input-type=module -e "import('./src/components/X.jsx').then(()=>console.log('OK')).catch(e=>console.error(e.message))"`. (3) Cross-reference FILE WRITTEN history — the recently modified component that the stuck test imports is the suspect. Look for module-level side effects: `new URL(import.meta.url)`, Web Worker init, top-level `fetch()` — these crash silently in jsdom/vitest before any test can run. Fix: guard with `if (!import.meta.env.TEST)` or move the side effect inside a `useEffect`. Never retry the full suite until the isolated probe passes.

### [2026-05-24 13:35] via lesson
Never use `CI=true npx vitest` syntax on Windows CMD; instead use `set CI=true && npx vitest` or run from PowerShell/Git Bash which support Unix-style environment variable syntax.

### [2026-05-24 13:41] via lesson
Always increase test timeout from 3ms to a realistic value (e.g., 10000ms) and bash timeout from 120s to at least 300s when running full integration test suites with verbose reporting.

### [2026-05-24 14:00] via lesson
Never use `--reporter=verbose` for a FULL vitest suite run — it suppresses the `❯ filename (0 test)` progress bar that reveals stuck files. A silently hung file produces zero verbose output, making the failure completely invisible until the 120s timeout fires. Use the DEFAULT reporter (no flag) for full suite runs. Reserve `--reporter=verbose` for single-file runs only: `npx vitest run SomeFile.test.jsx --reporter=verbose`.

### [2026-05-24 15:00] via user-correction
NEVER use `--reporter=dot` OR `--reporter=verbose` for a full `npx vitest run` suite — both suppress the `❯ filename (0 test)` progress indicator that timeout diagnosis relies on to name the stuck file. Without it, a module-load hang produces no diagnostic output: the timeout fires, the generic 'slow build' fallback triggers, and the agent loops forever retrying the same failing command. ALWAYS use the DEFAULT reporter (no `--reporter` flag): `npx vitest run`. Reserve non-default reporters for SINGLE-FILE runs only: `npx vitest run SomeFile.test.jsx --reporter=verbose`.

### [2026-05-24 15:30] via user-correction
When `npx vitest run` times out AFTER all test files show ✓ (e.g. "5 test files passed" but no 'Test Files N passed' summary prints), the hang is in vitest's TEARDOWN phase — all tests passed but an open async handle is keeping the Node.js event loop alive. Do NOT retry the same command. Fix: (1) Add `forceExit: true` to the `test` block in `vite.config.js` — forces process exit once all tests complete. (2) Root cause: add a global `HTMLCanvasElement.prototype.getContext = vi.fn(...)` mock in `setupTests.jsx` so PDF.js render tasks complete synchronously instead of leaving pending timer callbacks in the worker thread after test cleanup. Pending timers from un-awaited `act()` calls in navigation tests (e.g. click handlers) are the most common cause.

### [2026-05-24 14:00] via lesson
Never write markdown formatting into code files. When writing a .jsx, .js, .ts, .py or other code file, include ONLY the code — never the triple-backtick fences (```) or prose lines like "Now run the following:" or "Here is the implementation:". These are valid in a markdown response but are syntax errors when written to a code file. The file write is rejected immediately with FILE REJECTED if markdown artifacts are detected.

### [2026-05-24 13:51] via lesson
Always identify which test file is hanging when `npx vitest run` times out; PdfViewer.test.jsx showing "0 test" indicates it's stuck in setup/teardown. Increase the timeout to 180-240s for test suites involving file I/O operations like PDF parsing.

### [2026-05-24 14:00] via lesson
Before running `npx vitest run` on full test suites, increase BASH_TIMEOUT_SECONDS beyond 120s or install the `canvas` npm package to prevent bash-level timeout when jsdom's missing canvas context delays test completion.

### [2026-05-24 14:11] via lesson
Always specify an explicit timeout parameter (e.g., `timeout: 300000`) when running `npx vitest run`, since the default 120-second bash timeout is insufficient for complete test execution. The tests were actually passing but the command was killed before finishing.
