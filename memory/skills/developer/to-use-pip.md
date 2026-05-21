## HARD RULE: Never use uv — always use pip + venv

**`uv` is NOT installed on this machine. Any command using `uv` will fail with "not recognized as an internal or external command". Do not suggest it, do not use it, do not fall back to it.**

### The only allowed Python workflow on this machine:

1. **Create venv** (once per project): `python -m venv venv`
2. **Install deps**: `venv\Scripts\python.exe -m pip install -r requirements.txt`
3. **Run anything**: `venv\Scripts\python.exe -m pytest ...` or `venv\Scripts\python.exe script.py`

### Never use:
- `uv sync` ❌
- `uv run` ❌
- `uv pip` ❌
- `venv\Scripts\activate` in a chained command (activation doesn't persist across `&&` on Windows) ❌

### Always use instead:
- `venv\Scripts\python.exe -m pytest tests/ -v` ✅
- `venv\Scripts\python.exe -m pip install -r requirements.txt` ✅
- `venv\Scripts\python.exe app/main.py` ✅

If a venv already exists in the project folder, use it directly — do not recreate it.
