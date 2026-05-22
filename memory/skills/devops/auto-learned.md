# Auto-Learned Lessons — devops

Lessons captured automatically from failures, corrections, and retrospectives.

### [2026-05-22 02:17] via lesson
Before running `reg add "HKLM\..."` registry modifications, ensure the shell is running with administrator privileges—HKLM writes require elevated access.

### [2026-05-22 02:17] via lesson
Never use Unix-specific commands like `head` in tests running on Windows; use Python's built-in slicing or `subprocess` with platform detection instead.

### [2026-05-22 02:20] via lesson
Always run `reg add` commands targeting HKLM registry paths with administrator elevation—use `runas /user:Administrator` or execute from an elevated PowerShell/Command Prompt to avoid "Access is denied" errors.

### [2026-05-22 02:23] via lesson
Before using Unix commands like 'head' on Windows, activate WSL/Git Bash or replace with PowerShell equivalents (e.g., `Get-Content -Head N`). The Bash tool requires a Unix-compatible environment on Windows systems.

### [2026-05-22 02:26] via lesson
Never use the Bash tool on Windows for Unix-specific commands like 'head'; switch to the PowerShell tool instead for Windows compatibility.

### [2026-05-22 02:43] via lesson
Never run `uv` commands from OneDrive paths — move the project to a local drive (e.g., `C:\dev\`) first, as OneDrive can cause path resolution and file access failures. Before executing any command with spaces in the path, test the directory navigation independently to isolate shell vs. project setup issues.

### [2026-05-22 02:48] via lesson
Never mix PowerShell syntax (like `-not` conditionals and cmdlets like `Get-ChildItem`, `Select-Object`) in bash commands — convert to bash equivalents (`[[ ... ]]`, `ls`, `grep`, etc.) before running.

### [2026-05-22 02:48] via lesson
Always use `$VARNAME` syntax for environment variables in bash, never `$env:VARNAME` PowerShell syntax — in the Bash tool, environment variables are accessed with standard shell syntax.

### [2026-05-22 09:00] via lesson
Never use Windows `dir` commands in bash environments; use `find` or `ls` instead. Always verify the shell context before running environment-specific commands.
