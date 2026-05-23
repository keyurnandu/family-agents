import sqlite3
from pathlib import Path
from datetime import datetime


class DBManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project ON messages(project_name)"
        )
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                name TEXT PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                category TEXT NOT NULL,
                action_type TEXT NOT NULL,
                command_or_file TEXT,
                exit_code INTEGER,
                error_snippet TEXT,
                user_request TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_failures_project ON failures(project_name)"
        )
        self.conn.commit()

    def ensure_project(self, project_name: str, description: str = ""):
        self.conn.execute(
            "INSERT OR IGNORE INTO projects (name, description) VALUES (?, ?)",
            (project_name, description),
        )
        self.conn.commit()

    def save_message(self, project_name: str, role: str, content: str):
        self.conn.execute(
            "INSERT INTO messages (project_name, role, content) VALUES (?, ?, ?)",
            (project_name, role, content),
        )
        self.conn.commit()

    def load_history(self, project_name: str, limit: int = 20) -> list:
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            """SELECT role, content, timestamp FROM messages
               WHERE project_name = ? ORDER BY id DESC LIMIT ?""",
            (project_name, limit),
        ).fetchall()
        self.conn.row_factory = None
        return [dict(r) for r in reversed(rows)]

    def get_project(self, project_name: str) -> dict | None:
        self.conn.row_factory = sqlite3.Row
        row = self.conn.execute(
            """SELECT m.project_name as name,
                      COUNT(*) as message_count,
                      MAX(m.timestamp) as last_active,
                      p.description
               FROM messages m
               LEFT JOIN projects p ON p.name = m.project_name
               WHERE m.project_name = ?
               GROUP BY m.project_name""",
            (project_name,),
        ).fetchone()
        self.conn.row_factory = None
        return dict(row) if row else None

    def list_projects(self) -> list:
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            """SELECT m.project_name as name,
                      COUNT(*) as message_count,
                      MAX(m.timestamp) as last_active,
                      p.description
               FROM messages m
               LEFT JOIN projects p ON p.name = m.project_name
               GROUP BY m.project_name
               ORDER BY last_active DESC"""
        ).fetchall()
        self.conn.row_factory = None
        return [dict(r) for r in rows]

    # ── Failure logging ────────────────────────────────────────────────

    def log_failure(
        self,
        project_name: str,
        agent_name: str,
        category: str,
        action_type: str,
        command_or_file: str,
        exit_code: int | None,
        error_snippet: str,
        user_request: str,
    ):
        """Record an execution failure for later analysis."""
        self.conn.execute(
            """INSERT INTO failures
               (project_name, agent_name, category, action_type,
                command_or_file, exit_code, error_snippet, user_request)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_name, agent_name, category, action_type,
             command_or_file, exit_code, error_snippet, user_request),
        )
        self.conn.commit()

    def get_failures(
        self,
        project_name: str,
        limit: int = 20,
        category: str | None = None,
    ) -> list[dict]:
        """Retrieve recent failures, newest first. Optionally filter by category."""
        self.conn.row_factory = sqlite3.Row
        if category:
            rows = self.conn.execute(
                """SELECT * FROM failures
                   WHERE project_name = ? AND category = ?
                   ORDER BY id DESC LIMIT ?""",
                (project_name, category, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM failures
                   WHERE project_name = ?
                   ORDER BY id DESC LIMIT ?""",
                (project_name, limit),
            ).fetchall()
        self.conn.row_factory = None
        return [dict(r) for r in rows]

    def delete_project_messages(self, project_name: str):
        self.conn.execute(
            "DELETE FROM messages WHERE project_name = ?", (project_name,)
        )
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
