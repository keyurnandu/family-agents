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

    def delete_project_messages(self, project_name: str):
        self.conn.execute(
            "DELETE FROM messages WHERE project_name = ?", (project_name,)
        )
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
