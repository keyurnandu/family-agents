# Auto-Learned Lessons — lead

Lessons captured automatically from failures, corrections, and retrospectives.

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
