# Auto-Learned Lessons — qa

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-21 18:13] via bash-failure
Before running integration tests after code changes, verify that all test method calls match the current implementation signatures — here, `RunnerFactory.get_runner()` changed to accept 1 argument but 15 tests still called it with 2 (runner type + config).

### [2026-05-21 18:27] via bash-failure
Always verify `uv` is installed and in PATH before running `uv run` commands on Windows—check with `uv --version` or `where uv` first.
