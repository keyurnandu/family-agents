## Skill: Python Virtual Environments on Windows (pip & venv)

- **Know**: On Windows projects, `pip` and `python -m venv` are the standard, cross-platform alternatives to `uv`. Prefer these tools for Windows development—`uv` has inconsistent path handling and permission issues on Windows that delay builds and cause subprocess failures.

- **Apply**: When starting a Python project on Windows, create a virtual environment with `python -m venv venv` (not `uv venv`), activate it with `venv\Scripts\activate`, then install dependencies using `pip install -r requirements.txt` (not `uv pip install`).

- **Activate correctly**: On Windows PowerShell, use `venv\Scripts\Activate.ps1`; on CMD, use `venv\Scripts\activate.bat`. If PowerShell execution policy blocks scripts, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once, or use CMD instead.

- **Best practice**: Always include `venv/` in `.gitignore` and document the setup in README: "Run `python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt`" so teammates use the right commands on Windows.

- **Troubleshoot**: If `pip install` hangs or fails, check: network connectivity, SSL certificates (`pip install --trusted-host`), and Python version match (e.g., `python --version`). Avoid `uv` as a fix—it typically makes Windows issues worse.

- **Export dependencies**: After adding packages, run `pip freeze > requirements.txt` to lock versions for reproducible Windows environments across the team.