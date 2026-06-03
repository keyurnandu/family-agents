"""
LLM client — model-agnostic wrapper that routes all calls through
the active LLMProvider. The rest of the system calls call_claude()
and call_claude_json() without knowing which backend is active.

Provider is selected at startup from config/settings.yaml and can
be switched at runtime with /provider. Default: claude_cli.
"""
import json
import re
import time
from typing import Optional

from utils.llm_providers import LLMProvider, ClaudeCLIProvider, create_provider

# ── Active provider ───────────────────────────────────────────────────
_provider: LLMProvider = ClaudeCLIProvider()


def get_provider() -> LLMProvider:
    return _provider


def set_provider(provider: LLMProvider) -> None:
    global _provider
    _provider = provider


def set_provider_by_name(name: str, **kwargs) -> LLMProvider:
    """Create and activate a provider by name. Returns the instance."""
    global _provider
    _provider = create_provider(name, **kwargs)
    return _provider


# ── In-process session stats (reset on process start, not persisted) ──
_session_stats: dict = {"calls": 0, "input_chars": 0, "output_chars": 0}


def get_session_stats() -> dict:
    total_chars = _session_stats["input_chars"] + _session_stats["output_chars"]
    return {
        **_session_stats,
        "estimated_tokens": total_chars // 4,
    }


def snapshot_stats() -> dict:
    """Return a point-in-time copy of session stats for diffing."""
    return dict(_session_stats)


def reset_session_stats() -> None:
    _session_stats.update(calls=0, input_chars=0, output_chars=0)


# ── Analytics hook ────────────────────────────────────────────────────
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
    """Set context for the next LLM call (call_type, agent_role)."""
    _analytics_context["call_type"] = call_type
    _analytics_context["agent_role"] = agent_role


# ═══════════════════════════════════════════════════════════════════════
# Public API — unchanged signatures, agents/orchestrator call these
# ═══════════════════════════════════════════════════════════════════════

def call_claude(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Call the active LLM provider and return the response text."""
    input_chars = len(prompt) + len(system_prompt or "")
    _session_stats["input_chars"] += input_chars

    t_start = time.monotonic()
    try:
        output = _provider.complete(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
        )
    except Exception as e:
        duration_ms = int((time.monotonic() - t_start) * 1000)
        _log_to_analytics(model or "sonnet", input_chars, 0, duration_ms, success=False)
        raise

    duration_ms = int((time.monotonic() - t_start) * 1000)
    _session_stats["output_chars"] += len(output)
    _session_stats["calls"] += 1
    _log_to_analytics(model or "sonnet", input_chars, len(output), duration_ms, success=True)

    return output


def call_claude_json(
    prompt: str,
    schema: dict,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """Call the active LLM provider requesting JSON output."""
    input_chars = len(prompt) + len(system_prompt or "")
    _session_stats["input_chars"] += input_chars

    t_start = time.monotonic()
    try:
        result = _provider.complete_json(
            prompt=prompt,
            schema=schema,
            system_prompt=system_prompt,
            model=model,
        )
    except Exception as e:
        duration_ms = int((time.monotonic() - t_start) * 1000)
        _log_to_analytics(model or "sonnet", input_chars, 0, duration_ms, success=False)
        raise

    duration_ms = int((time.monotonic() - t_start) * 1000)
    # Estimate output chars from the JSON result
    output_chars = len(json.dumps(result))
    _session_stats["output_chars"] += output_chars
    _session_stats["calls"] += 1
    _log_to_analytics(model or "sonnet", input_chars, output_chars, duration_ms, success=True)

    return result


# ── Analytics logging ─────────────────────────────────────────────────

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
        _analytics_context.clear()
