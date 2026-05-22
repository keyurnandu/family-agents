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
