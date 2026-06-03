"""
Parses agent responses for executable actions (file writes, shell commands)
and prompts the user for permission before running them.

Agents signal an action by wrapping content in a tagged code block:

    EXEC:file:path/to/file.py
    ```
    <file content>
    ```

    EXEC:bash
    ```
    npm install && npm run build
    ```

File changes are collected and shown as a compact summary with diff stats —
NEW / +added -removed lines. One "apply all?" prompt for the whole batch.
Bash commands are confirmed individually.
"""
import difflib
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.panel import Panel

# Maximum seconds a bash command may run before being killed.
# Prevents subprocess.run from blocking forever (Ctrl+C can't interrupt
# a C-level pipe wait on Windows).
BASH_TIMEOUT_SECONDS = 120
from rich.prompt import Confirm
from rich.syntax import Syntax

from utils.display import _ts
from rich.table import Table
from rich.text import Text

console = Console()


# ── Smart output truncation ───────────────────────────────────────────
# Test runners put key info at both the start (collection, import errors)
# and end (summary, tracebacks). A naive tail-only truncation loses the
# beginning. This keeps head + tail + extracts summary lines.

_SUMMARY_PATTERNS = [
    re.compile(r"^=+ .*(passed|failed|error).*=+$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^FAILED\s+", re.MULTILINE),
    re.compile(r"^ERROR\s+", re.MULTILINE),
    re.compile(r"^\d+ passed", re.MULTILINE),
    re.compile(r"^Tests:\s+\d+", re.MULTILINE),          # jest
    re.compile(r"^Test Files\s+\d+", re.MULTILINE),       # vitest
    re.compile(r"^E\s+\w+Error:", re.MULTILINE),           # pytest tracebacks
    re.compile(r"^ImportError", re.MULTILINE),
    re.compile(r"^SyntaxError", re.MULTILINE),
]


def _smart_truncate(output: str, budget: int = 3000) -> str:
    """Truncate command output keeping the most useful parts.

    Strategy:
    1. If under budget, return as-is
    2. Extract summary/error lines (always included)
    3. Keep first 30 lines (collection, imports, early errors)
    4. Keep last N lines to fill remaining budget
    5. Join with a [truncated] marker in the middle
    """
    if len(output) <= budget:
        return output

    lines = output.splitlines()

    # Extract critical summary lines
    summary_lines = []
    for line in lines:
        for pattern in _SUMMARY_PATTERNS:
            if pattern.search(line):
                summary_lines.append(line)
                break

    # Head: first 30 lines (import errors, collection)
    head_count = min(30, len(lines) // 3)
    head = lines[:head_count]

    # Tail: last lines to fill budget
    head_text = "\n".join(head)
    summary_text = "\n".join(f"  >> {l}" for l in summary_lines) if summary_lines else ""
    marker = "\n\n[... output truncated ...]\n\n"

    used = len(head_text) + len(summary_text) + len(marker) + 100  # padding
    tail_budget = max(budget - used, 500)

    # Take last lines that fit in tail_budget
    tail_lines = []
    tail_chars = 0
    for line in reversed(lines[head_count:]):
        if tail_chars + len(line) + 1 > tail_budget:
            break
        tail_lines.insert(0, line)
        tail_chars += len(line) + 1

    # Assemble
    parts = [head_text]
    if tail_lines and tail_lines[0] != lines[head_count]:
        parts.append(marker)
    if summary_text:
        parts.append("KEY LINES:\n" + summary_text)
    if tail_lines:
        parts.append("\n".join(tail_lines))

    result = "\n".join(parts)
    return result[:budget + 500]  # hard cap with some grace


# ── Anti-hallucination footer ─────────────────────────────────────────
# Appended to every failure outcome so agents see it right next to
# the error. Prevents agents from inventing infrastructure blockers
# (".claude/settings.json", "permission wall", "paste the output").
_ANTI_HALLUCINATION_FOOTER = (
    " DO NOT mention .claude, settings.json, permissions, allow lists, "
    "or ask the customer to run commands manually — fix the issue using EXEC: blocks."
)

# ── Blocking command detection ─────────────────────────────────────────
# Commands that start interactive / watch-mode processes and never exit.
# These are ALWAYS blocked — there is no scenario where running them in
# an EXEC:bash block is useful. The agent should use a build or CI command
# instead (e.g. `vite build`, `vitest run`, `npm test -- --watchAll=false`).
_BLOCKING_PATTERNS = [
    # JavaScript dev servers
    re.compile(r"\bvite\b(?!\s+build)", re.IGNORECASE),          # vite / vite dev (not vite build)
    re.compile(r"\bnpm\s+(?:run\s+)?(?:start|dev)\b", re.IGNORECASE),  # npm start, npm run dev
    re.compile(r"\byarn\s+(?:start|dev)\b", re.IGNORECASE),      # yarn start, yarn dev
    # Jest / Vitest in watch mode
    re.compile(r"\bnpm\s+(?:run\s+)?tests?\b(?!.*--watchAll=false)(?!.*CI=)", re.IGNORECASE),  # npm test / npm run test without --watchAll=false or CI=
    re.compile(r"\bvitest\b(?!\s+run)", re.IGNORECASE),           # vitest (not vitest run)
    re.compile(r"\bjest\b(?!.*--watchAll=false)(?!.*--ci)", re.IGNORECASE),  # jest without --watchAll=false or --ci
    # Python / other servers
    re.compile(r"\bflask\s+run\b", re.IGNORECASE),
    re.compile(r"\buvicorn\b(?!.*--reload\s+False)", re.IGNORECASE),
    re.compile(r"\bpython\s+.*manage\.py\s+runserver\b", re.IGNORECASE),
    re.compile(r"\bnodemon\b", re.IGNORECASE),
]

_BLOCKING_SAFE_REPLACEMENTS = {
    "npm test": "set CI=true && npm test -- --verbose",
    "npm run test": "set CI=true && npm run test -- --verbose",
    "vitest": "node_modules\\.bin\\vitest run --reporter=verbose",
    "vite": "node_modules\\.bin\\vite build",
    "jest": "npm test -- --watchAll=false --verbose",
}


def _auto_fix_blocking_command(cmd: str) -> str | None:
    """Try to convert a blocking command into its safe non-interactive equivalent.

    Returns the fixed command string, or None if no safe replacement is known.
    Handles compound commands (e.g. "cd frontend && npm test") by fixing
    the blocking part while preserving the prefix (cd, env vars, etc.).
    """
    # Split on && to preserve cd/env prefix
    parts = [p.strip() for p in cmd.split("&&")]
    prefix_parts = []
    blocking_part = None

    for part in parts:
        if is_blocking_bash(part):
            blocking_part = part
            break
        prefix_parts.append(part)

    if not blocking_part:
        return None

    # Try each replacement pattern
    fixed = None
    lower = blocking_part.lower().strip()

    # npm test / npm run test → set CI=true && npm test -- --verbose
    if re.search(r"\bnpm\s+(?:run\s+)?tests?\b", lower):
        fixed = "set CI=true && npm test -- --verbose"
    # vitest (without run) → node_modules\.bin\vitest run --reporter=verbose
    elif re.search(r"\bvitest\b(?!\s+run)", lower):
        fixed = r"node_modules\.bin\vitest run --reporter=verbose"
    # jest → set CI=true && npx jest --verbose
    elif re.search(r"\bjest\b", lower):
        fixed = "set CI=true && npx jest --watchAll=false --verbose"
    # vite (without build) → node_modules\.bin\vite build
    elif re.search(r"\bvite\b(?!\s+build)", lower):
        fixed = r"node_modules\.bin\vite build"

    if not fixed:
        return None

    # Reassemble with prefix
    if prefix_parts:
        return " && ".join(prefix_parts) + " && " + fixed
    return fixed


def is_blocking_bash(cmd: str) -> bool:
    """Return True if the command starts an interactive/watch process that never exits.

    Whole-command safety overrides are checked first so that patterns like
    ``set CI=true && npm test -- --verbose`` (where CI= precedes npm test)
    are correctly treated as safe even though the negative lookahead in the
    npm-test pattern only looks *forward*.
    """
    # ``vitest run`` and ``vite build`` are always safe — check before patterns
    if re.search(r"\bvitest\s+run\b", cmd, re.IGNORECASE):
        return False
    if re.search(r"\bvite\s+build\b", cmd, re.IGNORECASE):
        return False

    # CI= anywhere in the command makes npm test / jest non-blocking (watch disabled)
    # but dev-server patterns (vite dev, npm start, uvicorn …) are still blocked.
    ci_anywhere = bool(re.search(r"(?:^|[\s&;|])(?:set\s+)?CI=", cmd, re.IGNORECASE))
    if ci_anywhere:
        # Only check the server/daemon patterns; skip npm-test (3) and jest (5)
        # because CI= makes those exit after one run.
        # Still block: vite-dev (0), npm-start (1), yarn-start (2),
        #              vitest-watch (4), flask (6), uvicorn (7), runserver (8), nodemon (9)
        server_patterns = (
            _BLOCKING_PATTERNS[0],   # vite (not vite build)
            _BLOCKING_PATTERNS[1],   # npm run start/dev
            _BLOCKING_PATTERNS[2],   # yarn start/dev
            _BLOCKING_PATTERNS[4],   # vitest (not vitest run) — CI= alone doesn't exit vitest
            _BLOCKING_PATTERNS[6],   # flask run
            _BLOCKING_PATTERNS[7],   # uvicorn
            _BLOCKING_PATTERNS[8],   # manage.py runserver
            _BLOCKING_PATTERNS[9],   # nodemon
        )
        return any(p.search(cmd) for p in server_patterns)

    return any(p.search(cmd) for p in _BLOCKING_PATTERNS)


# ── Streaming bash execution ────────────────────────────────────────────
# Run a shell command and stream stdout+stderr to the console as lines
# arrive, so the user can see progress (or recognise that a process is
# stuck) without waiting for the full timeout.

# Seconds of zero output before showing the "no output" idle warning.
_IDLE_WARNING_SECS = 20


def _run_bash_streaming(
    safe_cmd: str,
    project_dir: str,
    timeout_secs: int,
    _console: Console,
) -> tuple[int | None, str, bool]:
    """Run *safe_cmd* in a subprocess, streaming every output line to
    *_console* as it arrives.

    Returns ``(returncode, full_output, timed_out)``.
    *returncode* is ``None`` when the process was killed by the timeout.
    *full_output* is the merged stdout+stderr captured before termination.
    *timed_out* is ``True`` when the hard ceiling was hit.

    Design notes
    ~~~~~~~~~~~~
    * stdout and stderr are merged via ``stderr=STDOUT`` — one reader
      thread instead of two, which avoids deadlocks on Windows pipes.
    * A background daemon thread drains the pipe into a ``queue.Queue``
      so the main thread can enforce the hard ceiling without blocking
      on ``readline()``.
    * The main loop polls every 0.5 s; if no line arrives for
      ``_IDLE_WARNING_SECS`` seconds, a yellow warning is printed so the
      user knows the process is not producing output (classic sign of a
      watch-mode / interactive command that slipped past the pattern guard).
    * An elapsed-time ticker (``\\r`` overwrite) shows the user the
      command is still running.
    """
    line_queue: queue.Queue = queue.Queue()

    try:
        proc = subprocess.Popen(
            safe_cmd,
            shell=True,
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # merge so one thread suffices
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return 1, f"Failed to start process: {exc}", False

    def _reader() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line_queue.put(line)
        finally:
            line_queue.put(None)   # sentinel — EOF reached

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()

    collected: list[str] = []
    start_time = time.monotonic()
    last_output_time = start_time
    idle_warned = False
    timed_out = False

    while True:
        elapsed = time.monotonic() - start_time

        if elapsed >= timeout_secs:
            proc.kill()
            timed_out = True
            break

        try:
            line = line_queue.get(timeout=0.5)
        except queue.Empty:
            # ── Idle ticker ─────────────────────────────────────────────
            idle_secs = time.monotonic() - last_output_time
            # Overwrite the same terminal line with elapsed counter
            _console.print(
                f"  [dim]running… {int(elapsed)}s[/dim]",
                end="\r",
                highlight=False,
            )
            if idle_secs >= _IDLE_WARNING_SECS and not idle_warned:
                idle_warned = True
                _console.print(
                    f"\n  [bold yellow]⚠ No output for {int(idle_secs)}s — "
                    "process may be waiting for input or running in watch/server mode. "
                    "Press Ctrl+C to interrupt.[/bold yellow]"
                )
            continue

        if line is None:
            # EOF — process finished normally; flush any remaining items
            while True:
                try:
                    tail = line_queue.get_nowait()
                    if tail is None:
                        break
                    collected.append(tail)
                    _console.print(tail, end="", markup=False, highlight=False)
                except queue.Empty:
                    break
            break

        # ── Live output line ─────────────────────────────────────────────
        collected.append(line)
        last_output_time = time.monotonic()
        idle_warned = False          # reset warning if output resumes
        # Clear the ticker (overwrite with spaces) then print the real line
        _console.print(" " * 60, end="\r")
        _console.print(line, end="", markup=False, highlight=False)

    # Ensure the process is fully gone before we read returncode
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    reader.join(timeout=2)

    returncode = proc.returncode if not timed_out else None
    full_output = "".join(collected).strip()
    return returncode, full_output, timed_out


# ── Timeout diagnosis ───────────────────────────────────────────────────
# When a command times out, scan partial output for known "stuck" signatures
# so the agent receives a plain-English hint rather than a bare timeout message.

# Each entry: (pattern to search in partial output, hint string for agent)
_INTERACTIVE_OUTPUT_HINTS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"watch\s*usage|press\s+\w+\s+to\s+(?:run|quit)|watch\s+mode", re.IGNORECASE),
        "Process entered watch/interactive mode. Use 'vitest run' or 'set CI=true && npm test -- --verbose'.",
    ),
    (
        re.compile(r"username\s*(?:for|:)|password\s*(?:for|:)|enter\s+passphrase|credential", re.IGNORECASE),
        "Process is waiting for credentials. Configure SSH keys or a token and retry.",
    ),
    (
        re.compile(r"^\s*>\s*$", re.MULTILINE),
        "Process is in a REPL/interactive shell. Do not run interactive interpreters via EXEC.",
    ),
    (
        re.compile(r"press\s+any\s+key|press\s+enter\s+to\s+continue", re.IGNORECASE),
        "Process is waiting for a keypress. Use non-interactive flags or pipe 'yes' to the command.",
    ),
    (
        re.compile(r"listening\s+on|started\s+server|server\s+running|ready\s+in\s+\d+", re.IGNORECASE),
        "Process started a long-running server. Use a build command instead (e.g. vite build, gunicorn --workers 1 --timeout 5).",
    ),
    (
        re.compile(r"waiting\s+for\s+changes|watching\s+files|file\s+watcher", re.IGNORECASE),
        "Process is watching the filesystem. Use a one-shot command that exits after running.",
    ),
]

# Patterns in partial output that suggest a slow-but-legitimate operation
_SLOW_OP_PATTERNS = [
    re.compile(r"installing|downloading|fetching|resolving\s+packages", re.IGNORECASE),
    re.compile(r"compiling|bundling|transpiling|building", re.IGNORECASE),
    re.compile(r"running\s+\d+\s+tests?", re.IGNORECASE),  # "running 847 tests" — in-progress marker
]


def _diagnose_timeout(partial_output: str) -> str:
    """Return a plain-English hint about why a command timed out.

    Scans the partial output captured before the kill for well-known
    interactive/stuck signatures. Returns an empty string if no pattern
    matches (caller falls back to the no-output heuristic).

    The vitest ``(0 test)`` case is handled first (before the general hint
    loop) because it extracts the stuck filename for a targeted hint.
    """
    # ── vitest teardown hang (all files done, no summary) ───────────────
    # All test files completed successfully (default reporter prints
    # "✓ src/file (N tests) Xms" per file) but vitest never printed the
    # "Test Files N passed" final summary.  The hang is in vitest's
    # multi-fork pool coordinator: when all forks complete simultaneously
    # and each sends IPC results at the same time, the pool teardown
    # race-conditions and hangs.  Every individual file runs fine alone
    # ("npx vitest run file.test.jsx" exits cleanly); only the parallel
    # multi-fork teardown gets stuck.
    # Must be checked BEFORE the verbose check because default-reporter
    # file-completion lines ("✓ src/... (N tests)") also match the
    # broad "^\s+✓\s+src/" pattern used in the verbose check below.
    _teardown_completed = re.findall(
        r"✓\s+src/__tests__/[\w./-]+\.(?:test|spec)\.[jt]sx?\s+\(\d+ tests?\)",
        partial_output,
    )
    _teardown_failures = bool(re.search(r"[×✗x]\s+src/", partial_output))
    if (_teardown_completed
            and not _teardown_failures
            and "Test Files" not in partial_output
            and "❯" not in partial_output):
        n = len(set(_teardown_completed))
        return (
            f"Vitest completed {n} test file(s) successfully but never printed "
            f"the 'Test Files N passed' summary — vitest v2's pool.close() is "
            f"stuck. pool.close() waits for worker IPC channels that never close "
            f"because workers have pending handles (React 18 scheduler timers, "
            f"canvas callbacks). All pool types are affected (forks, vmForks, "
            f"threads). Every individual file exits fine alone; only multi-file "
            f"runs hang. "
            f"Fix: add a watchdog globalSetup file to vite.config.js that "
            f"force-exits after a short delay if pool.close() is stuck. "
            f"Create vitest.globalSetup.js: "
            f"export default function setup() {{ "
            f"  const t = setTimeout(() => {{ process.exit(0); }}, 8000); "
            f"  t.unref(); }}  "
            f"Then in vite.config.js test block add: "
            f"globalSetup: './vitest.globalSetup.js'. "
            f"The unref() ensures the timer does NOT block a clean exit; "
            f"it only fires if the event loop stays alive past 8s due to stuck IPC. "
            f"Tests complete in <2s and exit code 0 confirms all passed. "
            f"Also add `HTMLCanvasElement.prototype.getContext = vi.fn(() => "
            f"({{...}}))` in setupTests.jsx to reduce canvas timer leaks."
        )

    # ── vitest verbose-reporter silent hang ─────────────────────────────
    # With --reporter=verbose vitest streams individual test names (no ❯
    # progress bar).  A file that crashes at load time produces zero output,
    # so the final "Test Files  N passed" summary is never printed.
    # Detect: verbose ✓ lines (with ">" suite separator) exist, but no
    # "Test Files" summary and no ❯.  The ">" distinguishes verbose
    # per-test lines from default-reporter file-completion lines.
    if (re.search(r"^\s+✓\s+src/.*>", partial_output, re.MULTILINE)
            and "Test Files" not in partial_output
            and "❯" not in partial_output):
        completed = sorted(set(
            re.findall(
                r"src/__tests__/[\w./-]+\.(?:test|spec)\.[jt]sx?",
                partial_output,
            )
        ))
        completed_str = ", ".join(completed) if completed else "other files"
        return (
            "Vitest verbose reporter shows individual test results "
            f"({completed_str}) but never printed a 'Test Files' summary — "
            "one test file is silently stuck at module-load time. "
            "The stuck file is the one NOT in the completed list above. "
            "Step 1: re-run WITHOUT --reporter=verbose so the "
            "'❯ filename (0 test)' indicator identifies the exact stuck file. "
            "Step 2: check recently written code files for stray markdown "
            "content (``` fences, prose lines after closing brace) — these "
            "cause silent parse failures in the Vite/esbuild transform pipeline."
        )

    # ── vitest zero-test hang ────────────────────────────────────────────
    # Vitest shows "❯ path/to/file.test.jsx (0 test)" when a file is loaded
    # but no test has started — always means a module-level crash/hang in
    # the component under test (new URL(import.meta.url), Worker init, fetch).
    _zero_test_m = re.search(r"❯\s+(\S+.*?)\s+\(0 test", partial_output)
    if _zero_test_m:
        stuck_file = _zero_test_m.group(1).strip()
        return (
            f"A test file is stuck at module-load time — vitest shows "
            f"'{stuck_file} (0 test)' and never advances while other files pass. "
            f"Isolation strategy: "
            f"(1) Run the stuck file alone: `npx vitest run {stuck_file}`. "
            f"(2) If it still hangs, probe the component it imports directly: "
            f"`node --input-type=module -e \"import('./src/components/X/X.jsx')"
            f".then(()=>console.log('OK')).catch(e=>console.error(e.message))\"`. "
            f"(3) Cross-reference FILE WRITTEN history — the recently modified "
            f"component that '{stuck_file}' imports is the suspect. "
            f"Look for module-level side effects: new URL(import.meta.url), "
            f"Web Worker init, top-level fetch(), or canvas.getContext() — "
            f"these crash or hang in jsdom/vitest before any test can run."
        )

    # ── vitest dot-reporter silent hang ─────────────────────────────────
    # With --reporter=dot vitest prints dots (.) for each passing test but
    # emits no ❯ progress bar and no ✓ src/ lines. A file stuck at module-
    # load time silently stops the dots — no indicator of which file hung.
    # The slow-op fallback then fires on esbuild "bundling"/"compiling"
    # output, causing an infinite retry loop with a useless diagnosis.
    # Detect: vitest RUN header present, a line of 2+ dots exists,
    # no "Test Files" summary, and no ❯ bar (default reporter already
    # caught above via the zero-test check).
    if (re.search(r"\bRUN\b", partial_output)
            and re.search(r"^\s*\.{2,}", partial_output, re.MULTILINE)
            and "Test Files" not in partial_output
            and "❯" not in partial_output):
        return (
            "Vitest dot reporter shows test progress (dots) but no 'Test Files' "
            "summary printed — one test file is silently stuck at module-load time. "
            "The --reporter=dot flag hides the '❯ filename (0 test)' indicator "
            "that names the stuck file. "
            "STOP using --reporter=dot. Re-run with the DEFAULT reporter "
            "(no --reporter flag): `npx vitest run` — the stuck file will then "
            "appear as '❯ filename (0 test)' in the output."
        )

    for pattern, hint in _INTERACTIVE_OUTPUT_HINTS:
        if pattern.search(partial_output):
            return hint
    for pattern in _SLOW_OP_PATTERNS:
        if pattern.search(partial_output):
            return (
                "Process appears to be a slow build / install. "
                "Consider splitting into smaller steps or increasing BASH_TIMEOUT_SECONDS in action_executor.py."
            )
    return ""


# ── Markdown artifact detection ────────────────────────────────────────
# Agents occasionally write their markdown-formatted response (including
# the closing ``` fence and prose like "Now run the full suite:") directly
# into code files instead of extracting only the code content.  This
# produces a JavaScript/Python syntax error that causes completely silent
# test-worker crashes — the hardest failure mode to diagnose.
#
# Check every code file write BEFORE it hits disk so the agent receives
# an immediate FILE REJECTED outcome instead of discovering the corruption
# 15 iterations and hundreds of thousands of tokens later.

_CODE_EXTENSIONS = frozenset({
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".py", ".pyw",
    ".java", ".kt", ".swift", ".go", ".rs", ".c", ".cpp", ".h",
    ".cs", ".rb", ".php",
})

# Patterns that are valid in plain text / markdown but NOT in code files
_MARKDOWN_ARTIFACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"^```", re.MULTILINE),
        "triple-backtick fence (```) — markdown wrapper written into code file",
    ),
    (
        re.compile(
            r"^(?:Now run|Here is|Run the following|The above|You can now|"
            r"This (?:file|component|code|implementation)|Note that|"
            r"Make sure|Don't forget|Next(?:,| step)|"
            r"\*\*(?:Step|Note|Next|Now|Run|Here|The |This |Make))\b",
            re.MULTILINE,
        ),
        "prose instruction line — agent wrote markdown explanation into code file",
    ),
]


def _has_markdown_artifacts(path: Path, content: str) -> str | None:
    """Return a warning string if *content* looks like it contains markdown
    wrapper artifacts that do not belong in a code file.

    Returns ``None`` when the file looks clean.  Only checks file extensions
    in ``_CODE_EXTENSIONS``; skips markdown, yaml, config, and other text
    files where backticks or prose are valid.
    """
    if path.suffix.lower() not in _CODE_EXTENSIONS:
        return None
    for pattern, description in _MARKDOWN_ARTIFACT_PATTERNS:
        if pattern.search(content):
            return description
    return None


def _auto_clean_markdown_artifacts(path: Path, content: str) -> tuple[str, bool]:
    """Strip markdown artifacts from code file content instead of rejecting.

    Returns ``(cleaned_content, was_cleaned)``.  Only processes file
    extensions in ``_CODE_EXTENSIONS``.  Removes:
    - ALL triple-backtick fence lines anywhere in the file (```python,
      ```, etc.) — these have no valid meaning in code files
    - Trailing prose instruction lines that match ``_MARKDOWN_ARTIFACT_PATTERNS``
    """
    if path.suffix.lower() not in _CODE_EXTENSIONS:
        return content, False

    lines = content.splitlines()
    changed = False

    # Strip ALL fence lines — ```python, ```jsx, ```, etc.
    # These never appear in valid JS/JSX/TS/PY code files.
    fence_re = re.compile(r"^```\w*\s*$")
    cleaned_lines = []
    for line in lines:
        if fence_re.match(line):
            changed = True
        else:
            cleaned_lines.append(line)
    lines = cleaned_lines

    # Strip ALL prose instruction lines anywhere in the file —
    # agents write "Now run the full test suite:" or "Here is the
    # implementation:" into __init__.py and other small files.
    prose_pattern = _MARKDOWN_ARTIFACT_PATTERNS[1][0]  # the prose regex
    code_lines = []
    for line in lines:
        if prose_pattern.match(line.strip()):
            changed = True
        else:
            code_lines.append(line)
    lines = code_lines

    # Strip trailing blank lines left behind
    while lines and not lines[-1].strip():
        lines.pop()

    cleaned = "\n".join(lines)
    return cleaned, changed


# ── Destructive command detection ──────────────────────────────────────
# Commands that can cause irreversible data loss. In /auto mode, these
# are the ONLY bash commands that still require manual confirmation.
_DESTRUCTIVE_PATTERNS = [
    re.compile(r"\brm\s+.*-\w*[rf]", re.IGNORECASE),           # rm -rf, rm -r, rm -f
    re.compile(r"\bsudo\s+rm\b", re.IGNORECASE),                # sudo rm anything
    re.compile(r"\bdel\s+/", re.IGNORECASE),                    # Windows del /s /q
    re.compile(r"\brmdir\s+/s", re.IGNORECASE),                 # Windows rmdir /s
    re.compile(r"\bgit\s+push", re.IGNORECASE),                   # git push (publishes to remote)
    re.compile(r"\bgit\s+(?:merge|rebase|checkout|switch)\b", re.IGNORECASE),  # can lose uncommitted work
    re.compile(r"\bgit\s+reset\s+--hard", re.IGNORECASE),       # git reset --hard
    re.compile(r"\bgit\s+clean\s+.*-[df]", re.IGNORECASE),      # git clean -fd
    re.compile(r"\bgit\s+stash\s+drop", re.IGNORECASE),         # git stash drop (destroys stash)
    re.compile(r"\bgit\s+branch\s+-[dD]", re.IGNORECASE),       # git branch -d/-D (deletes branch)
    re.compile(r"\bdrop\s+(?:table|database)\b", re.IGNORECASE), # DROP TABLE/DATABASE
    re.compile(r"\btruncate\s+table\b", re.IGNORECASE),         # TRUNCATE TABLE
    re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),         # format C:
    re.compile(r"\bmkfs\b", re.IGNORECASE),                     # mkfs (format disk on Linux)
    re.compile(r"\bdd\s+if=", re.IGNORECASE),                   # dd (disk destroy)
]


def is_destructive_bash(cmd: str) -> bool:
    """Return True if the bash command matches any destructive pattern."""
    return any(p.search(cmd) for p in _DESTRUCTIVE_PATTERNS)


# Regex patterns that extract absolute paths from common scanning commands.
# Matches: C:\..., /home/..., ~\..., and quoted variants.
_ABSOLUTE_PATH_RE = re.compile(
    r"""(?:                            # Windows absolute path
        [A-Za-z]:[\\\/][^\s"'|&;>]+
    |                                  # Unix absolute path
        /(?:home|usr|etc|tmp|var|opt|root|mnt|media|Users)[/\w.-]*
    )""",
    re.VERBOSE,
)


def is_path_escape_bash(cmd: str, project_dir: Path) -> bool:
    """Return True if a bash command references absolute paths outside the project.

    Detects commands like:
    - Get-ChildItem -Path C:\\Users\\someone -Recurse
    - find / -name '*.log'
    - dir /s C:\\Users\\someone\\*.py
    - type C:\\Users\\someone\\Documents\\secrets.txt

    Paths that are INSIDE project_dir (or equal to it) are allowed.
    Relative paths are always allowed (they resolve under project_dir's cwd).
    """
    project_root = str(project_dir.resolve()).rstrip("\\/").lower()

    for match in _ABSOLUTE_PATH_RE.finditer(cmd):
        abs_path = match.group(0).rstrip("\\/").lower()
        # Allow if the path is inside (or equal to) the project dir
        if abs_path.startswith(project_root):
            continue
        # Allow if the project dir is inside the matched path
        # (e.g., project is C:\Users\me\projects\app and command reads C:\Users\me\projects\app\src)
        # Already handled by the startswith above.
        return True
    return False


def normalize_bash_command(
    cmd: str,
    project_dir: Path,
    extra_dirs: list[Path] | None = None,
) -> str:
    """Replace absolute paths in a bash command with relative paths.

    Agents sometimes emit full absolute paths (e.g. the OneDrive path) in
    EXEC:bash commands. On Windows this can exceed MAX_PATH (260 chars) and
    trigger WinError 206. Since subprocess already runs with cwd=project_dir,
    relative paths work correctly and avoid the length issue.

    When a codebase is /loaded at a short path (e.g. C:\\uishift\\backend2),
    agents may still reference the long OneDrive project_dir or the
    family-agents base_dir. Pass those as extra_dirs so they get stripped too.
    Longest paths are stripped first so nested paths don't partially match.
    """
    dirs = [project_dir]
    if extra_dirs:
        dirs.extend(extra_dirs)
    # Sort longest-first so e.g. base_dir/projects/app/ is tried before base_dir/
    dirs.sort(key=lambda d: len(str(d)), reverse=True)

    for d in dirs:
        abs_str = str(d)
        for variant in (abs_str, abs_str.replace("\\", "/")):
            for sep in (variant + "\\", variant + "/", variant):
                idx = cmd.lower().find(sep.lower())
                while idx != -1:
                    cmd = cmd[:idx] + cmd[idx + len(sep):]
                    idx = cmd.lower().find(sep.lower())
    return cmd


@dataclass
class Action:
    kind: Literal["file", "bash", "edit"]
    label: str       # file path or command summary
    content: str     # file content, bash script, or edit instructions
    agent_name: str


def _strip_nested_fences(content: str) -> str:
    """Remove accidental nested markdown fences from extracted file content.

    Agents sometimes wrap file content in an extra ```python / ``` layer
    inside the EXEC:file block. The outer fences are already stripped by
    the regex, but the inner ones slip through and trigger the markdown
    artifact guard. Strip them so clean code reaches the guard.
    """
    lines = content.splitlines()
    if lines and re.match(r"^```\w*\s*$", lines[0]):
        lines = lines[1:]
    if lines and re.match(r"^```\s*$", lines[-1]):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_actions(response_text: str, agent_name: str) -> list[Action]:
    """Extract EXEC: tagged blocks from an agent response."""
    actions: list[Action] = []

    chunks = re.split(r"(?=EXEC:(?:file:|edit:|bash))", response_text, flags=re.IGNORECASE)

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.upper().startswith("EXEC:"):
            continue

        # ── EXEC:edit:path — surgical line edits (low token cost) ────
        edit_match = re.match(
            r"EXEC:edit:([^\n]+)\n"
            r"```[^\n]*\n"
            r"(.*)"
            r"\n```",
            chunk,
            re.IGNORECASE | re.DOTALL,
        )
        if edit_match:
            path = edit_match.group(1).strip().strip("*`'\"")
            content = edit_match.group(2).strip()
            content = _strip_nested_fences(content)
            if content:
                actions.append(Action(kind="edit", label=path, content=content, agent_name=agent_name))
            continue

        file_match = re.match(
            r"EXEC:file:([^\n]+)\n"
            r"```[^\n]*\n"
            r"(.*)"          # greedy — stops at the LAST ``` in the chunk
            r"\n```",        # so internal code fences are captured, not treated as end
            chunk,
            re.IGNORECASE | re.DOTALL,
        )
        if file_match:
            path = file_match.group(1).strip().strip("*`'\"")
            content = file_match.group(2).strip()
            content = _strip_nested_fences(content)
            if content:
                actions.append(Action(kind="file", label=path, content=content, agent_name=agent_name))
            continue

        bash_match = re.match(
            r"EXEC:bash\s*\n"
            r"```[^\n]*\n"
            r"(.*)"          # greedy — same fix as file blocks
            r"\n```",
            chunk,
            re.IGNORECASE | re.DOTALL,
        )
        if bash_match:
            content = bash_match.group(1).strip()
            content = _strip_nested_fences(content)
            # Strip trailing prose that leaked in via greedy regex
            clean_lines = []
            for line in content.splitlines():
                stripped = line.strip()
                if stripped and re.match(r"^[A-Z][a-z]", stripped) and not any(
                    c in stripped for c in ("&&", "||", "|", ">", "<", "$", "=", "/", "\\", "-")
                ):
                    break
                clean_lines.append(line)
            content = "\n".join(clean_lines).strip()
            if content:
                lines = content.splitlines()
                label = (lines[0] if lines else "shell command")[:80]
                actions.append(Action(kind="bash", label=label, content=content, agent_name=agent_name))

    return actions


def _diff_stats(old: str, new: str) -> tuple[int, int, int]:
    """Return (added, removed, changed_lines) between old and new content."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    added = removed = 0
    for line in difflib.unified_diff(old_lines, new_lines, lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def _show_diff(old: str, new: str, path: str):
    """Print a colour-coded unified diff for a file change."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"  {path} (current)",
        tofile=f"  {path} (proposed)",
        lineterm="",
    ))
    if not diff:
        console.print("  [dim](no textual changes detected)[/dim]")
        return
    text = Text()
    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            text.append(line + "\n", style="dim")
        elif line.startswith("@@"):
            text.append(line + "\n", style="cyan dim")
        elif line.startswith("+"):
            text.append(line + "\n", style="green")
        elif line.startswith("-"):
            text.append(line + "\n", style="red")
        else:
            text.append(line + "\n", style="dim")
    console.print(text)


def _show_bash_action(action: Action):
    syntax = Syntax(action.content, "bash", theme="monokai")
    console.print(
        Panel(
            syntax,
            title="[bold]Run command[/bold]",
            border_style="yellow",
        )
    )


def run_health_check(cmd: str, cwd: Path) -> tuple[bool, str]:
    """
    Run a health-check command (e.g. import check or pytest --collect-only).
    Returns (passed, output_text).
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Health check timed out after 60 seconds."
    except Exception as e:
        return False, f"Health check error: {e}"


# ── Surgical edit execution ────────────────────────────────────────────
# EXEC:edit supports three operations per line:
#   DELETE <line_number>
#   REPLACE <line_number>: <new_content>
#   INSERT <line_number>: <new_content>       (inserts BEFORE the line)
#   REPLACE_STRING: <old_string> -> <new_string>  (search & replace)

def _apply_edit(action: Action, project_dir: Path, auto_mode: bool) -> str:
    """Apply surgical line edits to a file. Returns an outcome string."""
    dest = (project_dir / action.label).resolve()
    project_root = str(project_dir.resolve()).rstrip("\\/").lower()

    # Sandbox check
    if not str(dest).lower().startswith(project_root):
        console.print(
            f"  [red]✗ BLOCKED[/red]  [cyan]{action.label}[/cyan]  "
            "[dim](path escapes project directory)[/dim]"
        )
        return f"EDIT BLOCKED: {action.label} — escapes project directory." + _ANTI_HALLUCINATION_FOOTER

    if not dest.exists():
        console.print(
            f"  [red]✗ EDIT FAILED[/red]  [cyan]{action.label}[/cyan]  "
            "[dim](file does not exist)[/dim]"
        )
        return f"EDIT FAILED: {action.label} — file does not exist. Use EXEC:file to create new files."

    try:
        original = dest.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"EDIT FAILED: {action.label} — could not read file: {e}"

    lines = original.splitlines()
    edits_applied = 0
    errors = []

    for instruction in action.content.splitlines():
        instruction = instruction.strip()
        if not instruction:
            continue

        # REPLACE_STRING: old -> new
        if instruction.upper().startswith("REPLACE_STRING:"):
            parts = instruction[len("REPLACE_STRING:"):].strip()
            arrow_idx = parts.find("->")
            if arrow_idx == -1:
                errors.append(f"Bad REPLACE_STRING syntax: {instruction[:60]}")
                continue
            old_str = parts[:arrow_idx].strip()
            new_str = parts[arrow_idx + 2:].strip()
            new_content = "\n".join(lines)
            if old_str in new_content:
                new_content = new_content.replace(old_str, new_str, 1)
                lines = new_content.splitlines()
                edits_applied += 1
            else:
                errors.append(f"String not found: {old_str[:40]}")
            continue

        # DELETE <line_number>
        if instruction.upper().startswith("DELETE"):
            try:
                line_num = int(instruction.split()[1])
                if 1 <= line_num <= len(lines):
                    lines.pop(line_num - 1)
                    edits_applied += 1
                else:
                    errors.append(f"Line {line_num} out of range (file has {len(lines)} lines)")
            except (IndexError, ValueError):
                errors.append(f"Bad DELETE syntax: {instruction[:60]}")
            continue

        # REPLACE <line_number>: <content>
        if instruction.upper().startswith("REPLACE"):
            try:
                rest = instruction[len("REPLACE"):].strip()
                colon_idx = rest.index(":")
                line_num = int(rest[:colon_idx].strip())
                new_line = rest[colon_idx + 1:].strip()
                if 1 <= line_num <= len(lines):
                    lines[line_num - 1] = new_line
                    edits_applied += 1
                else:
                    errors.append(f"Line {line_num} out of range")
            except (ValueError, IndexError):
                errors.append(f"Bad REPLACE syntax: {instruction[:60]}")
            continue

        # INSERT <line_number>: <content>
        if instruction.upper().startswith("INSERT"):
            try:
                rest = instruction[len("INSERT"):].strip()
                colon_idx = rest.index(":")
                line_num = int(rest[:colon_idx].strip())
                new_line = rest[colon_idx + 1:].strip()
                if 1 <= line_num <= len(lines) + 1:
                    lines.insert(line_num - 1, new_line)
                    edits_applied += 1
                else:
                    errors.append(f"Line {line_num} out of range")
            except (ValueError, IndexError):
                errors.append(f"Bad INSERT syntax: {instruction[:60]}")
            continue

    if edits_applied == 0:
        msg = f"EDIT FAILED: {action.label} — no edits applied"
        if errors:
            msg += f". Errors: {'; '.join(errors)}"
        console.print(f"  [red]✗ EDIT FAILED[/red]  [cyan]{action.label}[/cyan]  [dim]({'; '.join(errors)})[/dim]")
        return msg

    # Show summary and apply
    console.print(
        f"  [green]✏ EDIT[/green]  [cyan]{action.label}[/cyan]  "
        f"[dim]{edits_applied} edit(s) applied[/dim]"
        + (f"  [yellow]{len(errors)} error(s)[/yellow]" if errors else "")
    )

    if auto_mode:
        console.print("[dim green]  ⚡ Auto-approved (auto mode)[/dim green]")
    else:
        approved = console.input("  Apply edit? [y/N] ").strip().lower() in ("y", "yes")
        if not approved:
            return f"EDIT SKIPPED: {action.label}"

    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"EDIT APPLIED: {action.label} — {edits_applied} edit(s)"


def prompt_and_execute(
    actions: list[Action],
    project_dir: Path,
    tdd_health_cmd: str | None = None,
    tdd_cwd: Path | None = None,
    normalize_dirs: list[Path] | None = None,
    auto_mode: bool = False,
) -> list[str]:
    """
    File changes: show a compact summary with diff stats, one 'apply all?' prompt.
    If the user types 'd' at the prompt, the full diff is shown before re-asking.
    Bash commands: confirmed individually (higher risk).

    auto_mode: when True, file writes and safe bash commands are auto-approved.
    Destructive bash commands (rm -rf, DROP TABLE, etc.) always require confirmation.

    Returns outcome strings fed back to the agent pipeline.
    """
    if not actions:
        return []

    outcomes: list[str] = []
    edit_actions = [a for a in actions if a.kind == "edit"]
    file_actions = [a for a in actions if a.kind == "file"]
    bash_actions  = [a for a in actions if a.kind == "bash"]

    # ── Surgical edits — apply line-level changes (low token cost) ──
    if edit_actions:
        for a in edit_actions:
            result = _apply_edit(a, project_dir, auto_mode)
            outcomes.append(result)
        console.print()

    # ── File changes — one collective prompt ─────────────────────────
    if file_actions:
        console.print()

        # ── Sandbox check: block file writes that escape the project dir ──
        project_root = str(project_dir.resolve()).rstrip("\\/").lower()
        safe_file_actions = []
        for a in file_actions:
            dest = (project_dir / a.label).resolve()
            if not str(dest).lower().startswith(project_root):
                console.print(
                    f"  [red]✗ BLOCKED[/red]  [cyan]{a.label}[/cyan]  "
                    "[dim](path escapes project directory)[/dim]"
                )
                outcomes.append(f"FILE BLOCKED: {a.label} — escapes project directory." + _ANTI_HALLUCINATION_FOOTER)
                continue
            # Auto-clean markdown artifacts before checking — strip
            # trailing prose and fences that agents accidentally include.
            a.content, was_cleaned = _auto_clean_markdown_artifacts(Path(a.label), a.content)
            if was_cleaned:
                console.print(
                    f"  [yellow]⚠ AUTO-CLEANED[/yellow]  [cyan]{a.label}[/cyan]  "
                    "[dim](stripped trailing markdown/prose artifacts)[/dim]"
                )
            md_warning = _has_markdown_artifacts(Path(a.label), a.content)
            if md_warning:
                console.print(
                    f"  [bold red]✗ REJECTED[/bold red]  [cyan]{a.label}[/cyan]  "
                    f"[dim]({md_warning})[/dim]"
                )
                outcomes.append(
                    f"FILE REJECTED — NOT WRITTEN TO DISK: {a.label} — {md_warning}. "
                    "The file on disk is UNCHANGED — your new content was discarded. "
                    "You MUST rewrite this file using EXEC:file with ONLY valid code. "
                    "Do NOT wrap the code in ```python or ```jsx fences — the EXEC: "
                    "block already provides the delimiters. Write raw code only, "
                    "no markdown fences, no prose instructions."
                    + _ANTI_HALLUCINATION_FOOTER
                )
                continue
            safe_file_actions.append(a)
        file_actions = safe_file_actions
        if not file_actions and not bash_actions:
            return outcomes

        agents_involved = sorted({a.agent_name for a in file_actions})
        agent_str = " & ".join(f"[bold yellow]{n}[/bold yellow]" for n in agents_involved)
        n = len(file_actions)
        console.print(
            f"{agent_str} want{'s' if len(agents_involved) == 1 else ''} to write "
            f"[bold]{n}[/bold] file{'s' if n > 1 else ''} to [cyan]{project_dir}[/cyan]:"
        )

        # Compact file table with diff stats
        table = Table(show_header=False, box=None, padding=(0, 1, 0, 0))
        table.add_column("icon", style="dim", no_wrap=True)
        table.add_column("path", style="cyan", no_wrap=True)
        table.add_column("stats", no_wrap=True)
        table.add_column("preview", style="dim")

        file_states: dict[str, dict] = {}  # label → {is_new, old_content, added, removed}
        for a in file_actions:
            dest = (project_dir / a.label).resolve()
            is_new = not dest.exists()
            old_content = ""
            added = removed = 0
            if not is_new:
                try:
                    old_content = dest.read_text(encoding="utf-8", errors="replace")
                    added, removed = _diff_stats(old_content, a.content)
                except Exception:
                    is_new = True  # treat as new if unreadable
            else:
                added = len(a.content.splitlines())

            file_states[a.label] = {
                "is_new": is_new,
                "old_content": old_content,
                "added": added,
                "removed": removed,
            }

            if is_new:
                stats = Text("NEW", style="bold green")
                stats.append(f"  +{added}", style="green")
            else:
                stats = Text()
                if added:
                    stats.append(f"+{added} ", style="green")
                if removed:
                    stats.append(f"-{removed}", style="red")
                if not added and not removed:
                    stats.append("unchanged", style="dim")

            lines = a.content.splitlines()
            preview = (lines[0][:50].strip() + "…") if lines and len(lines[0]) > 50 else (lines[0].strip() if lines else "")
            icon = "✨" if is_new else "✏ "
            table.add_row(icon, a.label, stats, preview)

        console.print(table)

        if auto_mode:
            # Auto-approve: skip the interactive prompt
            console.print("[dim green]  ⚡ Auto-approved (auto mode)[/dim green]")
            approved = True
        else:
            console.print("[dim]  d = show diff · y = apply · N = skip[/dim]")

            while True:
                raw = console.input(
                    f"\n  Apply {'all ' if n > 1 else ''}{'change' if n == 1 else 'changes'}? [d/y/N] "
                ).strip().lower()
                if raw == "d":
                    # Show diffs for all changed (non-new) files
                    console.print()
                    for a in file_actions:
                        state = file_states[a.label]
                        if state["is_new"]:
                            suffix = Path(a.label).suffix.lstrip(".") or "text"
                            console.print(f"\n[bold green]✨ NEW[/bold green]  [cyan]{a.label}[/cyan]")
                            console.print(Syntax(a.content[:3000], suffix, theme="monokai", line_numbers=True))
                        else:
                            console.print(f"\n[bold yellow]✏  DIFF[/bold yellow]  [cyan]{a.label}[/cyan]")
                            _show_diff(state["old_content"], a.content, a.label)
                    console.print()
                    console.print("[dim]  d = show diff again · y = apply · N = skip[/dim]")
                    continue
                approved = raw in ("y", "yes")
                break

        if approved:
            console.print()
            for a in file_actions:
                dest = (project_dir / a.label).resolve()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(a.content, encoding="utf-8")
                state = file_states[a.label]
                if state["is_new"]:
                    console.print(f"  [green]✓[/green]  {a.label}  [dim green](new)[/dim green]")
                else:
                    console.print(
                        f"  [green]✓[/green]  {a.label}  "
                        f"[green]+{state['added']}[/green] [red]-{state['removed']}[/red]"
                    )
                outcomes.append(f"FILE WRITTEN: {a.label}")
            console.print()

            # ── TDD health check — runs automatically after every approved write ──
            if tdd_health_cmd:
                check_dir = tdd_cwd or project_dir
                console.print(
                    f"[dim cyan]🧪 TDD health check running…[/dim cyan]  "
                    f"[dim]{tdd_health_cmd[:80]}[/dim]"
                )
                passed, output = run_health_check(tdd_health_cmd, check_dir)
                if passed:
                    console.print("  [bold green]✓ Health check passed[/bold green]\n")
                    outcomes.append("HEALTH_CHECK: PASSED")
                else:
                    console.print("  [bold red]✗ Health check FAILED[/bold red]")
                    # Show last 20 lines of output — enough for the agent to diagnose
                    lines = output.splitlines()
                    snippet = "\n".join(lines[-20:]) if len(lines) > 20 else output
                    console.print(Text(snippet + "\n", style="dim red"))
                    outcomes.append(f"HEALTH_CHECK: FAILED\n{snippet}")
        else:
            console.print("  [dim]Changes skipped.[/dim]\n")
            for a in file_actions:
                outcomes.append(f"FILE SKIPPED: {a.label}")

    # ── Bash commands — individual prompts ───────────────────────────
    # Deduplicate: if two agents emit the same command, run it once and
    # share the outcome. Agents within a phase run in parallel and often
    # independently decide to run the same test/build command.
    _bash_seen: dict[str, str] = {}  # normalized command → outcome string
    for action in bash_actions:
        cmd_key = action.content.strip().lower()
        if cmd_key in _bash_seen:
            console.print(
                f"\n[dim]{action.agent_name} also requested: {action.label} "
                f"— already ran (dedup)[/dim]"
            )
            outcomes.append(_bash_seen[cmd_key])
            continue

        console.print()
        console.print(f"[bold yellow]{action.agent_name}[/bold yellow] wants to run:")
        _show_bash_action(action)

        # Sandbox check: block commands that reference paths outside the project
        if is_path_escape_bash(action.content, project_dir):
            console.print(
                "[bold red]  ✗ BLOCKED — command references paths outside the project directory[/bold red]"
            )
            outcomes.append(
                f"BASH BLOCKED: {action.label} — references paths outside the project directory. "
                f"Only use relative paths or paths inside {project_dir}."
                + _ANTI_HALLUCINATION_FOOTER
            )
            continue

        # Auto-correct commands that start interactive/watch processes.
        # Instead of blocking and hoping the agent retries correctly,
        # replace the command with the safe alternative and run it.
        if is_blocking_bash(action.content):
            fixed_cmd = _auto_fix_blocking_command(action.content)
            if fixed_cmd:
                console.print(
                    f"[yellow]  ⚠ AUTO-FIXED[/yellow]  [dim]interactive command → "
                    f"non-interactive alternative[/dim]"
                )
                console.print(f"  [dim]Original:  {action.content.strip()[:100]}[/dim]")
                console.print(f"  [dim]Fixed:     {fixed_cmd.strip()[:100]}[/dim]")
                action.content = fixed_cmd
            else:
                console.print(
                    "[bold red]  ✗ BLOCKED — this command starts an interactive process "
                    "that never exits[/bold red]"
                )
                console.print(
                    "[dim]  Use a non-interactive alternative:\n"
                    "  • Jest:    set CI=true && npm test -- --verbose\n"
                    r"  • Vitest:  node_modules\.bin\vitest run --reporter=verbose"
                    "\n"
                    r"  • Vite:    node_modules\.bin\vite build"
                    "\n"
                    "  • uvicorn: import the app in Python and check it starts\n"
                    "  • Flask:   python -c \"from app import create_app; create_app()\"[/dim]"
                )
                outcomes.append(
                    f"BASH BLOCKED: {action.label} — starts an interactive/watch process that never exits. "
                    "Use CI=true npm test, vitest run, or vite build instead."
                    + _ANTI_HALLUCINATION_FOOTER
                )
                continue

        if auto_mode and not is_destructive_bash(action.content):
            # Auto-approve safe bash commands
            console.print("[dim green]  ⚡ Auto-approved (auto mode)[/dim green]")
            approved = True
        elif auto_mode and is_destructive_bash(action.content):
            # Destructive commands ALWAYS require manual confirmation
            console.print("[bold yellow]  ⚠ Destructive command detected — manual approval required[/bold yellow]")
            approved = Confirm.ask("  Allow?", default=False)
        else:
            approved = Confirm.ask("  Allow?", default=False)

        if approved:
            console.print(f"  [dim]Running… {_ts()}[/dim]")
            # Normalize absolute paths to relative — prevents WinError 206
            # on long OneDrive paths where cmd.exe exceeds MAX_PATH.
            safe_cmd = normalize_bash_command(action.content, project_dir, normalize_dirs)

            # ── Stream output live ───────────────────────────────────────
            # _run_bash_streaming prints every line as it arrives so the
            # user can see progress (or recognise a stuck/watch process)
            # without waiting for the full timeout.
            returncode, output, timed_out = _run_bash_streaming(
                safe_cmd, project_dir, BASH_TIMEOUT_SECONDS, console
            )

            console.print()  # blank line after streamed output

            if timed_out:
                console.print(f"  [red]✗ Timed out after {BASH_TIMEOUT_SECONDS}s[/red]\n")
                # Auto-diagnose: scan the output we did collect for stuck-patterns
                hint = _diagnose_timeout(output)
                if not hint and not output:
                    hint = (
                        "No output was produced before the timeout. "
                        "The process likely started in watch/interactive mode or is waiting for input. "
                        f"Check if '{action.content.split()[0]}' requires a non-interactive flag."
                    )
                if hint:
                    console.print(f"  [bold yellow]Diagnosis:[/bold yellow] [dim]{hint}[/dim]\n")

                outcome_parts = [
                    f"BASH FAILED (timed out after {BASH_TIMEOUT_SECONDS}s): {action.label}",
                ]
                if output:
                    snippet = output[-2000:] if len(output) > 2000 else output
                    outcome_parts.append(f"LAST OUTPUT BEFORE TIMEOUT:\n{snippet}")
                if hint:
                    outcome_parts.append(f"DIAGNOSTIC HINT: {hint}")
                outcomes.append("\n".join(outcome_parts))
                continue

            if returncode == 0:
                console.print("  [green]✓ Done[/green]  (exit 0)\n")
                snippet = _smart_truncate(output)
                _outcome = (
                    f"BASH OK: {action.label}\nOUTPUT:\n{snippet}" if snippet
                    else f"BASH OK: {action.label}"
                )
            else:
                console.print(f"  [red]✗ Exited {returncode}[/red]\n")
                snippet = _smart_truncate(output, budget=5000)  # more budget for errors
                _outcome = (
                    f"BASH FAILED (exit {returncode}): {action.label}\nOUTPUT:\n{snippet}"
                    if snippet
                    else f"BASH FAILED (exit {returncode}): {action.label}"
                )
            outcomes.append(_outcome)
            _bash_seen[cmd_key] = _outcome  # cache for dedup
        else:
            console.print("  [dim]Skipped.[/dim]")
            outcomes.append(f"BASH SKIPPED: {action.label}")

    return outcomes
