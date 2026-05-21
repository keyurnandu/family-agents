## SKILL: Python on Windows — Exact Commands, No Exceptions

### The absolute rules

1. **`uv` is NOT installed. Never use it.** `uv sync`, `uv run`, `uv pip` all fail with "not recognized as an internal or external command". Do not suggest it under any circumstances.

2. **Never use `venv\Scripts\activate` in a chained command.** Activation does not persist across `&&` on Windows. The activated shell state is lost immediately.

3. **Always use the venv Python directly by full path.** This works reliably on Windows regardless of activation state.

---

### The only workflow

```
# Step 1 — create venv (once per project, only if it doesn't exist)
python -m venv venv

# Step 2 — install dependencies
venv\Scripts\python.exe -m pip install -r requirements.txt

# Step 3 — run anything
venv\Scripts\python.exe -m pytest tests/ -v
venv\Scripts\python.exe -m pytest tests/test_runner.py -v
venv\Scripts\python.exe check_imports.py
venv\Scripts\python.exe app/main.py
```

---

### Windows-specific gotchas

| Wrong ❌ | Right ✅ |
|---|---|
| `uv sync && uv run pytest` | `venv\Scripts\python.exe -m pytest` |
| `venv\Scripts\activate && python -m pytest` | `venv\Scripts\python.exe -m pytest` |
| `python -c "from app.main import app"` (long string, hits 32KB limit) | `venv\Scripts\python.exe check_imports.py` |
| `pip install -r requirements.txt` (system pip, wrong env) | `venv\Scripts\python.exe -m pip install -r requirements.txt` |

---

### If venv already exists

Do NOT recreate it. Check first:
```
# If venv\Scripts\python.exe exists, use it directly
venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

### Inline -c commands hit Windows length limits

The Windows `CreateProcess` API has a 32,767 character limit on command-line arguments. Long inline Python (`-c "..."`) commands fail silently or with obscure errors.

**Always write a script file instead:**
```python
# check_imports.py
from app.main import app
print("Import OK")
```
Then run: `venv\Scripts\python.exe check_imports.py`
