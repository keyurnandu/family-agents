## Skill: Virtual Environment Setup Across Languages

- **Understand isolation principles**: Virtual environments create isolated dependency spaces to prevent version conflicts between projects. Know that each language has native tools (Python: `venv`/`virtualenv`; Node.js: `npm ci` + `.nvmrc`; Ruby: `Bundler` + Gemfile; Go: `go.mod`; etc.). Select the right tool based on the project's ecosystem.

- **Create and activate systematically**: For each language, script or document the exact commands: Python (`python -m venv venv && source venv/bin/activate`), Node (`npm install` with lockfile), Ruby (`bundle install`). Always activate before installing dependencies or running code; verify activation in your shell prompt.

- **Lock dependencies deterministically**: Use lock files to freeze versions across environments: Python (`requirements.txt` or `poetry.lock`), Node (`package-lock.json`), Ruby (`Gemfile.lock`), Go (`go.sum`). Commit lock files to version control; use `pip freeze`, `npm ci`, or `bundle install --frozen` in CI/production to ensure reproducibility.

- **Document setup in README or CLAUDE.md**: Include language version (`.python-version`, `.nvmrc`), activation steps, and any special initialization (e.g., `poetry install` vs. `pip install`). This ensures collaborators and future you can bootstrap quickly and consistently.

- **Isolate by environment (dev, test, prod)**: Use separate virtual environments or install profiles for different stages (dev tools like linters/tests separate from production dependencies). In Python, consider `poetry` or `pipenv` for robust multi-environment management; in Node, separate `devDependencies`.

- **Automate activation in workflows**: Configure shell hooks (`.bashrc`, `direnv`) or CI steps to auto-activate environments when entering a project directory. In Claude Code, leverage `.claude/settings.json` to run setup hooks (e.g., `pip install -r requirements.txt`) before tasks.