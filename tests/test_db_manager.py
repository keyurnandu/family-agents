"""Tests for utils/db_manager.py — persistent connection and all operations."""
import sqlite3

import pytest

from utils.db_manager import DBManager


class TestPersistentConnection:
    def test_connection_is_stored_on_instance(self, db_path):
        db = DBManager(db_path)
        assert hasattr(db, "conn")
        assert db.conn is not None
        assert isinstance(db.conn, sqlite3.Connection)
        db.close()

    def test_connection_reused_across_operations(self, db_path):
        db = DBManager(db_path)
        conn_before = db.conn
        db.ensure_project("test-proj")
        db.save_message("test-proj", "user", "hello")
        db.load_history("test-proj")
        conn_after = db.conn
        assert conn_before is conn_after
        db.close()

    def test_close_method_exists(self, db_path):
        db = DBManager(db_path)
        assert hasattr(db, "close")
        db.close()


class TestDBOperations:
    """Verify all DB operations still work correctly with persistent connection."""

    def test_ensure_project_and_get_project(self, db_path):
        db = DBManager(db_path)
        db.ensure_project("my-app", "A test project")
        db.save_message("my-app", "user", "hello")
        info = db.get_project("my-app")
        assert info is not None
        assert info["name"] == "my-app"
        assert info["message_count"] == 1
        db.close()

    def test_save_and_load_history(self, db_path):
        db = DBManager(db_path)
        db.ensure_project("proj")
        db.save_message("proj", "user", "first message")
        db.save_message("proj", "assistant", "first reply")
        db.save_message("proj", "user", "second message")
        history = db.load_history("proj", limit=10)
        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "first message"
        assert history[2]["content"] == "second message"
        db.close()

    def test_load_history_respects_limit(self, db_path):
        db = DBManager(db_path)
        db.ensure_project("proj")
        for i in range(20):
            db.save_message("proj", "user", f"msg {i}")
        history = db.load_history("proj", limit=5)
        assert len(history) == 5
        assert history[-1]["content"] == "msg 19"
        db.close()

    def test_list_projects(self, db_path):
        db = DBManager(db_path)
        db.ensure_project("alpha")
        db.ensure_project("beta")
        db.save_message("alpha", "user", "hello alpha")
        db.save_message("beta", "user", "hello beta")
        projects = db.list_projects()
        names = {p["name"] for p in projects}
        assert "alpha" in names
        assert "beta" in names
        db.close()

    def test_get_project_returns_none_for_missing(self, db_path):
        db = DBManager(db_path)
        assert db.get_project("nonexistent") is None
        db.close()

    def test_delete_project_messages(self, db_path):
        db = DBManager(db_path)
        db.ensure_project("deleteme")
        db.save_message("deleteme", "user", "temp")
        assert db.get_project("deleteme") is not None
        db.delete_project_messages("deleteme")
        assert db.get_project("deleteme") is None
        db.close()

    def test_delete_last_n_messages(self, db_path):
        """delete_last_n_messages should remove only the last N entries."""
        db = DBManager(db_path)
        db.ensure_project("proj")
        for i in range(10):
            db.save_message("proj", "user", f"msg {i}")
        deleted = db.delete_last_n_messages("proj", 3)
        assert deleted == 3
        history = db.load_history("proj", limit=100)
        # Should have 7 left, and the last 3 (msg 7,8,9) should be gone
        assert len(history) == 7
        assert history[-1]["content"] == "msg 6"
        db.close()

    def test_delete_last_n_more_than_exists(self, db_path):
        """Deleting more than exists should delete all, not error."""
        db = DBManager(db_path)
        db.ensure_project("proj")
        db.save_message("proj", "user", "only one")
        deleted = db.delete_last_n_messages("proj", 100)
        assert deleted == 1
        history = db.load_history("proj", limit=100)
        assert len(history) == 0
        db.close()

    def test_delete_last_n_zero(self, db_path):
        """Deleting 0 messages should be a no-op."""
        db = DBManager(db_path)
        db.ensure_project("proj")
        db.save_message("proj", "user", "keep me")
        deleted = db.delete_last_n_messages("proj", 0)
        assert deleted == 0
        history = db.load_history("proj", limit=100)
        assert len(history) == 1
        db.close()


# ── Failure logging ────────────────────────────────────────────────

class TestFailureLogging:
    """Tests for the failures table and log/query methods."""

    def test_failures_table_created(self, db_path):
        """The failures table should exist after DBManager init."""
        db = DBManager(db_path)
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='failures'"
        ).fetchall()
        assert len(tables) == 1
        db.close()

    def test_log_failure_stores_record(self, db_path):
        """log_failure() should insert a row with all fields."""
        db = DBManager(db_path)
        db.log_failure(
            project_name="my-app",
            agent_name="Sam",
            category="bash_error",
            action_type="bash",
            command_or_file="pytest tests/",
            exit_code=1,
            error_snippet="FAILED test_example.py",
            user_request="build the login page",
        )
        rows = db.get_failures("my-app")
        assert len(rows) == 1
        row = rows[0]
        assert row["agent_name"] == "Sam"
        assert row["category"] == "bash_error"
        assert row["action_type"] == "bash"
        assert row["command_or_file"] == "pytest tests/"
        assert row["exit_code"] == 1
        assert row["error_snippet"] == "FAILED test_example.py"
        assert row["user_request"] == "build the login page"
        assert "timestamp" in row
        db.close()

    def test_get_failures_filters_by_project(self, db_path):
        """get_failures() should only return failures for the requested project."""
        db = DBManager(db_path)
        db.log_failure("proj-a", "Sam", "bash_error", "bash", "cmd1", 1, "err1", "req1")
        db.log_failure("proj-b", "Sam", "bash_error", "bash", "cmd2", 1, "err2", "req2")
        rows = db.get_failures("proj-a")
        assert len(rows) == 1
        assert rows[0]["command_or_file"] == "cmd1"
        db.close()

    def test_get_failures_respects_limit(self, db_path):
        """get_failures() should return at most `limit` rows, newest first."""
        db = DBManager(db_path)
        for i in range(10):
            db.log_failure("proj", "Sam", "bash_error", "bash", f"cmd{i}", 1, f"err{i}", "req")
        rows = db.get_failures("proj", limit=3)
        assert len(rows) == 3
        # Newest first
        assert rows[0]["command_or_file"] == "cmd9"
        db.close()

    def test_get_failures_filters_by_category(self, db_path):
        """get_failures() with category filter should only return matching rows."""
        db = DBManager(db_path)
        db.log_failure("proj", "Sam", "bash_error", "bash", "cmd1", 1, "err", "req")
        db.log_failure("proj", "Sam", "bash_timeout", "bash", "cmd2", None, "timeout", "req")
        db.log_failure("proj", "Casey", "health_check_fail", "file", "app.py", None, "fail", "req")
        rows = db.get_failures("proj", category="bash_error")
        assert len(rows) == 1
        assert rows[0]["category"] == "bash_error"
        db.close()

    def test_log_failure_with_none_exit_code(self, db_path):
        """exit_code can be None (e.g. for timeouts or blocked commands)."""
        db = DBManager(db_path)
        db.log_failure("proj", "Sam", "bash_blocked", "bash", "find /", None, "blocked", "req")
        rows = db.get_failures("proj")
        assert len(rows) == 1
        assert rows[0]["exit_code"] is None
        db.close()

    def test_get_failures_returns_empty_list_when_none(self, db_path):
        """get_failures() should return [] when no failures exist."""
        db = DBManager(db_path)
        rows = db.get_failures("nonexistent-proj")
        assert rows == []
        db.close()
