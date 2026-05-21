## Skill: pip-venv-windows

- **Use pip and python -m venv exclusively on Windows**: Never use `uv`—it lacks proper Windows support. For all Python projects on Windows, use `pip` for package management and `python -m venv` for isolated environments. This is the standard and only supported approach.

- **Create and activate virtual environments correctly**: Execute `python -m venv venv`, then activate with `venv\Scripts\activate` (Command Prompt) or `venv\Scripts\Activate.ps1` (PowerShell). Verify activation by confirming `(venv)` appears in your terminal prompt before running any pip commands.

- **Manage dependencies with pip and requirements.txt**: Install packages with `pip install <package>`. Lock versions using `pip freeze > requirements.txt`. Reproduce environments with `pip install -r requirements.txt`. Never mix package managers on the same project.

- **Follow the standard Windows workflow**: (1) `python -m venv venv` → (2) Activate venv → (3) `pip install -r requirements.txt` → (4) Run Python scripts. This linear process is reliable and requires no special Windows configuration.

- **Avoid all uv syntax and directives**: Don't use `uv run`, `uv sync`, `uv pip`, or uv-specific pyproject.toml entries. Stick strictly to pip commands and standard Python packaging. Any uv syntax will fail in Windows environments.