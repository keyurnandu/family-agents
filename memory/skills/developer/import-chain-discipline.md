## SKILL: Import Chain Discipline — Fix All Broken Imports Before Running Tests

### The core rule
Never fix broken imports one at a time. Every time you fix one, another surfaces — this is whack-a-mole and wastes the user's time.

**ALWAYS: scan the entire codebase for ALL broken imports first, then fix everything in one pass.**

---

### Step 1: Before touching any file, audit what is missing

When an ImportError appears:
1. Read the source file that is being imported FROM (e.g. `app/models/test_case.py`)
2. Run a grep for ALL imports from that file across the whole codebase:
   ```
   grep -r "from app.models.test_case import" .
   ```
3. Collect every symbol that is imported but does not exist in the source file
4. Fix ALL of them in one edit — not one at a time

---

### Lessons from uishift-backend2 (real failures, not theory)

**Missing symbols that were never added to `app/models/test_case.py`:**
- `StepRunStatus` — imported by test_run.py, dtos/reporting.py, dtos/run.py, run_service.py, notifications
- `TestPriority` — imported by test_run.py, test_case_service.py, notifications
- `TestCaseStatus` — imported by run_service.py, dtos/test_case.py, test_case_service.py, api/v1/test_cases.py
- `SelectorType.POSITION` — referenced in services/healing/rule_based.py

**Pattern:** These were all planned symbols that got referenced in service/API files but never actually written into the model file. The codebase was written file-by-file without verifying the import chain end-to-end.

**Missing functions in `app/services/selectors.py`:**
- `parse_role_selector` — needed by healing/rule_based.py
- `parse_semantic_selector_value` — needed by healing/rule_based.py
- `serialize_semantic_selector` — needed by healing/rule_based.py
- `serialize_testid_selector` — needed by healing/rule_based.py

These were imported but the functions were never implemented.

---

### The check_imports.py pattern

Before running pytest, always verify the import chain is clean with a script file (NOT inline `-c` which hits Windows command-line length limits):

```python
# check_imports.py — place in project root
from app.main import app
print("Import OK")
```

Run it:
```
venv\Scripts\python.exe check_imports.py
```

If this passes, pytest collection will work. If it fails, fix the imports before running any tests.

---

### When adding a new Enum value

1. Add the value to the Enum class
2. If there is a defaults/scores dict keyed by that Enum (e.g. `SELECTOR_STABILITY_DEFAULTS`), add the new key there too
3. If the Enum is used as a field type on a Document/Model class, ensure the field exists on that class

Example — when adding `SelectorType.POSITION`:
- Add `POSITION = "position"` to `SelectorType`
- Add `SelectorType.POSITION: 0.30` to `SELECTOR_STABILITY_DEFAULTS`

---

### When adding a new status Enum (e.g. TestCaseStatus)

1. Add the Enum class to the model file
2. Add a `status` field to the Document class that uses it, with an appropriate default
3. Grep for every file importing it — they all need the same symbol name

---

### Summary checklist before running pytest

- [ ] `venv\Scripts\python.exe check_imports.py` passes
- [ ] All symbols imported from model files actually exist in those files
- [ ] All functions imported from service files are actually implemented
- [ ] Any new Enum values are reflected in associated dicts/fields
