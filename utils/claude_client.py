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
from typing import Optional

# In-process session stats (reset on process start, not persisted)
_session_stats: dict = {"calls": 0, "input_chars": 0, "output_chars": 0}

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

    _session_stats["input_chars"] += len(prompt) + len(system_prompt or "")

    # Write system prompt to a temp file — avoids putting thousands of
    # chars on the command line which triggers WinError 206 on Windows
    # when the OneDrive path + system prompt exceed 32k chars.
    sp_file = None
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

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"claude CLI exit {result.returncode}: {stderr}")

    output = result.stdout.strip()
    _session_stats["output_chars"] += len(output)
    _session_stats["calls"] += 1
    return output


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
