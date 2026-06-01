# Auto-Learned Lessons — pm

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-22 11:05] via lesson
Before running bash commands on Windows, verify Unix utilities like `tail` are available—use PowerShell or cross-platform alternatives instead. Always check the target OS before executing platform-specific commands.

### [2026-05-23 20:04] via lesson
Never use Unix-only commands like `tail` in bash without platform verification; replace with cross-platform alternatives like Python slicing or direct output handling.

### [2026-05-24 17:45] via lesson
Before running `git add`, verify that target files aren't in ignored paths using `git check-ignore`, or use `git add -f` to force-add files when needed.
