# Auto-Learned Lessons — bsa

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-23 04:57] via lesson
Before writing code that depends on DTO fields, use `git grep` (e.g., `git grep "runner_used"`) to verify exact committed field names instead of assuming naming patterns.

### [2026-05-23 15:55] via lesson
Never use Unix pipe utilities like `head` in bash commands on Windows; use `pytest --maxfail=N` or file redirection (`> output.txt`) instead for output limiting.
