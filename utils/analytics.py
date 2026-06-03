"""
LLM usage analytics — tracks every claude --print call with per-call
metrics: model, tokens, cost, duration, call type, agent role.

Data is persisted to the llm_calls table in conversations.db and
queryable via the /analytics CLI command.
"""
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# ── Anthropic pricing (per million tokens, USD) ───────────────────────
# Updated 2025-06. Check https://docs.anthropic.com/en/docs/about-claude/pricing
_PRICING = {
    "haiku": {"input": 0.25, "output": 1.25},
    "sonnet": {"input": 3.00, "output": 15.00},
    "opus": {"input": 15.00, "output": 75.00},
}
_DEFAULT_MODEL = "sonnet"


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for a single call."""
    rates = _PRICING.get(model, _PRICING[_DEFAULT_MODEL])
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


# ── Session ID — unique per CLI launch ────────────────────────────────
_session_id: str = uuid.uuid4().hex[:12]


def get_session_id() -> str:
    return _session_id


# ── DB schema ─────────────────────────────────────────────────────────

def init_analytics_table(conn: sqlite3.Connection) -> None:
    """Create the llm_calls table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            project_name TEXT,
            call_type TEXT NOT NULL,
            agent_role TEXT,
            model TEXT NOT NULL,
            input_chars INTEGER NOT NULL,
            output_chars INTEGER NOT NULL,
            input_tokens_est INTEGER NOT NULL,
            output_tokens_est INTEGER NOT NULL,
            estimated_cost_usd REAL NOT NULL,
            duration_ms INTEGER NOT NULL,
            success INTEGER NOT NULL DEFAULT 1,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_calls_project "
        "ON llm_calls(project_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_calls_session "
        "ON llm_calls(session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_calls_timestamp "
        "ON llm_calls(timestamp)"
    )
    conn.commit()


# ── Logging ───────────────────────────────────────────────────────────

def log_call(
    conn: sqlite3.Connection,
    project_name: str | None,
    call_type: str,
    agent_role: str | None,
    model: str,
    input_chars: int,
    output_chars: int,
    duration_ms: int,
    success: bool = True,
) -> None:
    """Record a single LLM call to the analytics table."""
    input_tokens = input_chars // 4
    output_tokens = output_chars // 4
    cost = estimate_cost(model, input_tokens, output_tokens)

    conn.execute(
        """INSERT INTO llm_calls
           (session_id, project_name, call_type, agent_role, model,
            input_chars, output_chars, input_tokens_est, output_tokens_est,
            estimated_cost_usd, duration_ms, success)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _session_id, project_name, call_type, agent_role, model,
            input_chars, output_chars, input_tokens, output_tokens,
            cost, duration_ms, 1 if success else 0,
        ),
    )
    conn.commit()


# ── Queries ───────────────────────────────────────────────────────────

def _rows_to_dicts(cursor) -> list[dict]:
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def summary_by_project(conn: sqlite3.Connection, days: int = 30) -> list[dict]:
    """Aggregate usage by project over the last N days."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    cur = conn.execute("""
        SELECT
            COALESCE(project_name, '(general)') AS project,
            COUNT(*) AS calls,
            SUM(input_tokens_est) AS input_tokens,
            SUM(output_tokens_est) AS output_tokens,
            SUM(input_tokens_est + output_tokens_est) AS total_tokens,
            ROUND(SUM(estimated_cost_usd), 4) AS total_cost_usd,
            ROUND(AVG(duration_ms)) AS avg_duration_ms
        FROM llm_calls
        WHERE timestamp >= ?
        GROUP BY project_name
        ORDER BY total_cost_usd DESC
    """, (since,))
    return _rows_to_dicts(cur)


def summary_by_model(conn: sqlite3.Connection, days: int = 30) -> list[dict]:
    """Aggregate usage by model over the last N days."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    cur = conn.execute("""
        SELECT
            model,
            COUNT(*) AS calls,
            SUM(input_tokens_est + output_tokens_est) AS total_tokens,
            ROUND(SUM(estimated_cost_usd), 4) AS total_cost_usd,
            ROUND(AVG(duration_ms)) AS avg_duration_ms
        FROM llm_calls
        WHERE timestamp >= ?
        GROUP BY model
        ORDER BY total_cost_usd DESC
    """, (since,))
    return _rows_to_dicts(cur)


def summary_by_agent(conn: sqlite3.Connection, days: int = 30) -> list[dict]:
    """Aggregate usage by agent role over the last N days."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    cur = conn.execute("""
        SELECT
            COALESCE(agent_role, 'system') AS agent,
            COUNT(*) AS calls,
            SUM(input_tokens_est + output_tokens_est) AS total_tokens,
            ROUND(SUM(estimated_cost_usd), 4) AS total_cost_usd,
            SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failures
        FROM llm_calls
        WHERE timestamp >= ?
        GROUP BY agent_role
        ORDER BY total_cost_usd DESC
    """, (since,))
    return _rows_to_dicts(cur)


def summary_by_call_type(conn: sqlite3.Connection, days: int = 30) -> list[dict]:
    """Aggregate usage by call type (routing, agent, synthesis, etc.)."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    cur = conn.execute("""
        SELECT
            call_type,
            COUNT(*) AS calls,
            SUM(input_tokens_est + output_tokens_est) AS total_tokens,
            ROUND(SUM(estimated_cost_usd), 4) AS total_cost_usd,
            ROUND(AVG(duration_ms)) AS avg_duration_ms
        FROM llm_calls
        WHERE timestamp >= ?
        GROUP BY call_type
        ORDER BY total_cost_usd DESC
    """, (since,))
    return _rows_to_dicts(cur)


def session_summary(conn: sqlite3.Connection, session_id: str | None = None) -> dict:
    """Get totals for a specific session (default: current)."""
    sid = session_id or _session_id
    cur = conn.execute("""
        SELECT
            COUNT(*) AS calls,
            SUM(input_tokens_est) AS input_tokens,
            SUM(output_tokens_est) AS output_tokens,
            SUM(input_tokens_est + output_tokens_est) AS total_tokens,
            ROUND(SUM(estimated_cost_usd), 4) AS total_cost_usd,
            ROUND(AVG(duration_ms)) AS avg_duration_ms,
            MIN(timestamp) AS started_at,
            MAX(timestamp) AS last_call_at
        FROM llm_calls
        WHERE session_id = ?
    """, (sid,))
    rows = _rows_to_dicts(cur)
    return rows[0] if rows else {}


def totals_all_time(conn: sqlite3.Connection) -> dict:
    """Get grand totals across all sessions."""
    cur = conn.execute("""
        SELECT
            COUNT(*) AS calls,
            SUM(input_tokens_est + output_tokens_est) AS total_tokens,
            ROUND(SUM(estimated_cost_usd), 4) AS total_cost_usd,
            COUNT(DISTINCT session_id) AS sessions,
            COUNT(DISTINCT project_name) AS projects,
            MIN(timestamp) AS first_call,
            MAX(timestamp) AS last_call
        FROM llm_calls
    """)
    rows = _rows_to_dicts(cur)
    return rows[0] if rows else {}


def daily_usage(conn: sqlite3.Connection, days: int = 14) -> list[dict]:
    """Daily token usage and cost for the last N days."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    cur = conn.execute("""
        SELECT
            DATE(timestamp) AS date,
            COUNT(*) AS calls,
            SUM(input_tokens_est + output_tokens_est) AS total_tokens,
            ROUND(SUM(estimated_cost_usd), 4) AS total_cost_usd
        FROM llm_calls
        WHERE timestamp >= ?
        GROUP BY DATE(timestamp)
        ORDER BY date
    """, (since,))
    return _rows_to_dicts(cur)
