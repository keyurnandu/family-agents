# Auto-Learned Lessons — devops

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-23 22:30] via user-correction
This is a WINDOWS machine. NEVER use Unix-only commands: bash, bash -c, tail, head, cat, grep, ls, wc, sed, awk, which, chmod, chown. Use Windows equivalents: cmd /c, Get-Content, type, findstr, dir, Measure-Object, PowerShell, where.exe, icacls.

### [2026-05-23 22:00] via user-correction
Local git operations (git add, git commit, git tag, git stash) are fine — they're just local checkpoints. NEVER run git push, git merge, git rebase, git checkout, or git reset --hard without explicit user approval — these publish to remote or can lose uncommitted work.

### [2026-05-22 02:20] via lesson
Run `reg add` commands targeting HKLM registry paths with administrator elevation—use `runas /user:Administrator` or execute from an elevated PowerShell/Command Prompt to avoid "Access is denied" errors.

### [2026-05-22 02:43] via lesson
Never run `uv` commands from OneDrive paths — move the project to a local drive (e.g., `C:\dev\`) first, as OneDrive can cause path resolution and file access failures.

### [2026-05-22 02:48] via lesson
Always use `$VARNAME` syntax for environment variables in bash, never `$env:VARNAME` PowerShell syntax — in the Bash tool, environment variables are accessed with standard shell syntax.
