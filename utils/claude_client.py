"""
Thin wrapper around `claude --print` so the rest of the system
never imports the anthropic SDK and needs no API key.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Optional

# In-process session stats (reset on process start, not persisted)
_session_stats: dict = {"calls": 0, "input_chars": 0, "output_chars": 0}

# ── Analytics hook ────────────────────────────────────────────────────
# Set by the orchestrator at startup so every LLM call is logged
# without claude_client needing to import db_manager directly.
_analytics_conn = None          # sqlite3.Connection | None
_analytics_project: str = ""    # current project name
_analytics_context: dict = {}   # {"call_type": ..., "agent_role": ...}


def set_analytics(conn, project_name: str = "") -> None:
    """Wire up the analytics DB connection. Called once at startup."""
    global _analytics_conn, _analytics_project
    _analytics_conn = conn
    _analytics_project = project_name


def set_analytics_project(project_name: str) -> None:
    """Update the current project name (called on /switch)."""
    global _analytics_project
    _analytics_project = project_name


def set_analytics_context(call_type: str = "", agent_role: str = "") -> None:
    """Set context for the next LLM call (call_type, agent_role).
    Reset after each call so stale context doesn't leak."""
    _analytics_context["call_type"] = call_type
    _analytics_context["agent_role"] = agent_role

def get_session_stats() -> dict:
    total_chars = _session_stats["input_chars"] + _session_stats["output_chars"]
    return {
        **_session_stats,
        "estimated_tokens": total_chars // 4,
    }

def snapshot_stats() -> dict:
    """Return a point-in-time copy of session stats for diffing before/after an exchange."""
    return dict(_session_stats)

def reset_session_stats() -> None:
    _session_stats.update(calls=0, input_chars=0, output_chars=0)


_cli_checked = False

def _check_cli():
    global _cli_checked
    if _cli_checked:
        return
    if not shutil.which("claude"):
        raise RuntimeError(
            "claude CLI not found in PATH.\n"
            "Install Claude Code from https://claude.ai/code and log in once."
        )
    _cli_checked = True


def call_claude(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Call `claude --print` and return the response text.

    Both the system prompt and the user prompt are kept OFF the command line
    to avoid Windows' 32,767-char CreateProcess limit (WinError 206).
    - System prompt → temp file, passed via --system-prompt-file
    - User prompt → stdin
    """
    _check_cli()

    cmd = ["claude", "--print"]

    if model:
        cmd += ["--model", model]

    input_chars = len(prompt) + len(system_prompt or "")
    _session_stats["input_chars"] += input_chars

    # Write system prompt to a temp file — avoids putting thousands of
    # chars on the command line which triggers WinError 206 on Windows
    # when the OneDrive path + system prompt exceed 32k chars.
    sp_file = None
    t_start = time.monotonic()
    success = False
    output = ""
    try:
        if system_prompt:
            fd, sp_file = tempfile.mkstemp(suffix=".txt", prefix="claude_sp_")
            os.write(fd, system_prompt.encode("utf-8"))
            os.close(fd)
            cmd += ["--system-prompt-file", sp_file]

        result = subprocess.run(
            cmd,
            input=prompt,               # prompt → stdin (no size limit)
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    finally:
        if sp_file:
            try:
                os.unlink(sp_file)
            except OSError:
                pass

    duration_ms = int((time.monotonic() - t_start) * 1000)

    if result.returncode != 0:
        # Log failed call to analytics before raising
        _log_to_analytics(model or "sonnet", input_chars, 0, duration_ms, success=False)
        stderr = result.stderr.strip()
        raise RuntimeError(f"claude CLI exit {result.returncode}: {stderr}")

    output = result.stdout.strip()
    _session_stats["output_chars"] += len(output)
    _session_stats["calls"] += 1
    success = True

    # Log to analytics
    _log_to_analytics(model or "sonnet", input_chars, len(output), duration_ms, success=True)

    return output


def _log_to_analytics(
    model: str, input_chars: int, output_chars: int,
    duration_ms: int, success: bool,
) -> None:
    """Log a call to the analytics DB if connected. Never raises."""
    if not _analytics_conn:
        return
    try:
        from utils.analytics import log_call
        log_call(
            conn=_analytics_conn,
            project_name=_analytics_project or None,
            call_type=_analytics_context.get("call_type", "unknown"),
            agent_role=_analytics_context.get("agent_role"),
            model=model,
            input_chars=input_chars,
            output_chars=output_chars,
            duration_ms=duration_ms,
            success=success,
        )
    except Exception:
        pass  # analytics must never break the main flow
    finally:
        # Reset context so stale values don't leak to the next call
        _analytics_context.clear()


def call_claude_json(
    prompt: str,
    schema: dict,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """Call claude requesting JSON output matching `schema`."""
    schema_desc = json.dumps(schema, indent=2)
    json_system = (
        (system_prompt + "\n\n" if system_prompt else "")
        + "CRITICAL: Your response MUST be valid JSON only — no markdown, no explanation, "
        "no code fences. Output a single JSON object matching this schema exactly:\n"
        + schema_desc
    )
    json_prompt = prompt + "\n\nRespond with ONLY a JSON object. No other text."

    raw = call_claude(prompt=json_prompt, system_prompt=json_system, model=model)

    # Attempt 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Attempt 2: extract from code fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Attempt 3: find first {...} block in text
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise RuntimeError(f"Could not parse JSON from response:\n{raw[:400]}")
