"""Tests for memory dedup logic in MemoryManager.save_project_memory."""
from utils.memory_manager import MemoryManager


class TestMemoryDedup:
    def test_exact_duplicate_rejected(self, base_dir):
        mm = MemoryManager(base_dir, "test-proj")
        assert mm.save_project_memory("Use PostgreSQL for the database", "decision", "customer") is True
        assert mm.save_project_memory("Use PostgreSQL for the database", "decision", "customer") is False

    def test_case_insensitive_duplicate_rejected(self, base_dir):
        mm = MemoryManager(base_dir, "test-proj")
        mm.save_project_memory("Deploy to AWS", "decision", "customer")
        assert mm.save_project_memory("deploy to aws", "decision", "customer") is False

    def test_different_content_accepted(self, base_dir):
        mm = MemoryManager(base_dir, "test-proj")
        mm.save_project_memory("Use React for frontend", "decision", "customer")
        assert mm.save_project_memory("Use Vue for frontend", "decision", "customer") is True

    def test_no_false_positive_on_common_prefix(self, base_dir):
        """The old [:60] substring check would false-positive when two different
        entries share the same first 60 characters."""
        mm = MemoryManager(base_dir, "test-proj")
        # Both entries share the identical first 60 chars:
        # "foo bar baz foo bar baz foo bar baz foo bar baz foo bar baz "
        prefix = "foo bar baz " * 5  # exactly 60 chars
        mm.save_project_memory(prefix + "UNIQUE ENDING ALPHA", "decision", "customer")
        result = mm.save_project_memory(prefix + "UNIQUE ENDING BETA", "decision", "customer")
        assert result is True, "Should not false-positive on shared 60-char prefix"

    def test_no_false_negative_on_short_content(self, base_dir):
        """Short entries with the same content should still be deduped."""
        mm = MemoryManager(base_dir, "test-proj")
        mm.save_project_memory("Use Docker", "technical", "lead")
        assert mm.save_project_memory("Use Docker", "technical", "lead") is False

    def test_whitespace_normalization(self, base_dir):
        """Leading/trailing whitespace should not bypass dedup."""
        mm = MemoryManager(base_dir, "test-proj")
        mm.save_project_memory("Use Redis for caching", "technical", "lead")
        assert mm.save_project_memory("  Use Redis for caching  ", "technical", "lead") is False
