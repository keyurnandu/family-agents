"""Tests for Agent._prompt_cache size cap."""
from agents.agent import Agent


class TestPromptCacheCap:
    def setup_method(self):
        Agent._prompt_cache.clear()

    def test_cache_has_max_size_constant(self):
        assert hasattr(Agent, "_PROMPT_CACHE_MAX")
        assert Agent._PROMPT_CACHE_MAX == 20

    @staticmethod
    def _fill_cache(n):
        """Insert n entries and run eviction after each (simulating _build_system_prompt)."""
        for i in range(n):
            key = (f"role_{i}", f"project_{i}", f"hash_{i}", "None")
            Agent._prompt_cache[key] = (f"prompt_{i}", "None")
            if len(Agent._prompt_cache) > Agent._PROMPT_CACHE_MAX:
                oldest = next(iter(Agent._prompt_cache))
                del Agent._prompt_cache[oldest]

    def test_cache_evicts_oldest_when_full(self):
        """When cache exceeds max size, oldest entries should be evicted."""
        Agent._prompt_cache.clear()
        self._fill_cache(25)
        assert len(Agent._prompt_cache) <= Agent._PROMPT_CACHE_MAX

    def test_recent_entries_preserved(self):
        """The most recent entries should survive eviction."""
        Agent._prompt_cache.clear()
        self._fill_cache(25)
        last_key = ("role_24", "project_24", "hash_24", "None")
        assert last_key in Agent._prompt_cache

    def test_oldest_entries_evicted(self):
        """The earliest entries should be evicted when cache is full."""
        Agent._prompt_cache.clear()
        self._fill_cache(25)

        # The first entry should have been evicted
        first_key = ("role_0", "project_0", "hash_0", "None")
        assert first_key not in Agent._prompt_cache
