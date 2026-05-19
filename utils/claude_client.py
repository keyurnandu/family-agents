"""
Thin wrapper around `claude --print` so the rest of the system
never imports the anthropic SDK and needs no API key.
"""
import json
import re
import shutil
import subprocess
from typing import Optional


def _check_cli():
    if not shutil.which("claude"):
        raise RuntimeError(
            "claude CLI not found in PATH.\n"
            "Install Claude Code from https://claude.ai/code and log in once."
        )


def call_claude(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Call `claude --print` and return the response text."""
    _check_cli()

    cmd = ["claude", "--print"]

    if model:
        cmd += ["--model", model]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]

    cmd.append(prompt)

    result = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,   # never consume terminal stdin
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"claude CLI exit {result.returncode}: {stderr}")

    return result.stdout.strip()


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
