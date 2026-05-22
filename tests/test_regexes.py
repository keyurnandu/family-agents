"""Tests for module-level regex constants in agent.py and orchestrator.py.

These test that the patterns match the same inputs as before, ensuring
the move from inline to module-level doesn't break matching behavior.
"""
import re


class TestAgentRegexes:
    """Regexes moved to module level in agents/agent.py."""

    def test_code_task_re_exists_at_module_level(self):
        from agents.agent import _CODE_TASK_RE
        assert isinstance(_CODE_TASK_RE, re.Pattern)

    def test_code_task_re_matches_implementation_words(self):
        from agents.agent import _CODE_TASK_RE
        assert _CODE_TASK_RE.search("implement the login feature")
        assert _CODE_TASK_RE.search("refactor the user module")
        assert _CODE_TASK_RE.search("fix the broken endpoint")
        assert _CODE_TASK_RE.search("read the config file")
        assert _CODE_TASK_RE.search("write tests for the API")
        assert _CODE_TASK_RE.search("work on epic E1")

    def test_code_task_re_no_match_on_generic(self):
        from agents.agent import _CODE_TASK_RE
        assert not _CODE_TASK_RE.search("hello how are you")
        assert not _CODE_TASK_RE.search("what is the weather")

    def test_impl_re_exists_at_module_level(self):
        from agents.agent import _IMPL_RE
        assert isinstance(_IMPL_RE, re.Pattern)

    def test_impl_re_matches_implementation_tasks(self):
        from agents.agent import _IMPL_RE
        assert _IMPL_RE.search("implement the payment system")
        assert _IMPL_RE.search("write the handler")
        assert _IMPL_RE.search("work on epic E2")
        assert _IMPL_RE.search("fix the broken auth")
        assert _IMPL_RE.search("create the database schema")
        assert _IMPL_RE.search("tackle sprint S3")

    def test_impl_re_no_match_on_read_only(self):
        from agents.agent import _IMPL_RE
        assert not _IMPL_RE.search("show me the docs")
        assert not _IMPL_RE.search("explain this pattern")

    def test_full_file_re_exists_at_module_level(self):
        from agents.agent import _FULL_FILE_RE
        assert isinstance(_FULL_FILE_RE, re.Pattern)

    def test_full_file_re_matches_full_intent(self):
        from agents.agent import _FULL_FILE_RE
        assert _FULL_FILE_RE.search("show me the full file")
        assert _FULL_FILE_RE.search("read the entire config")
        assert _FULL_FILE_RE.search("review the complete module")
        assert _FULL_FILE_RE.search("inspect the whole thing")
        assert _FULL_FILE_RE.search("examine all of the code")


class TestOrchestratorRegexes:
    """Regexes moved to module level in orchestrator.py."""

    def test_correction_re_exists_at_module_level(self):
        from orchestrator import _CORRECTION_RE
        assert isinstance(_CORRECTION_RE, re.Pattern)

    def test_correction_re_matches_corrections(self):
        from orchestrator import _CORRECTION_RE
        assert _CORRECTION_RE.search("stop doing that")
        assert _CORRECTION_RE.search("don't use uv on Windows")
        assert _CORRECTION_RE.search("never run rm -rf")
        assert _CORRECTION_RE.search("you should have used pytest")
        assert _CORRECTION_RE.search("that's wrong")
        assert _CORRECTION_RE.search("next time check imports first")

    def test_correction_re_no_match_on_regular(self):
        from orchestrator import _CORRECTION_RE
        assert not _CORRECTION_RE.search("build me a website")
        assert not _CORRECTION_RE.search("hello team")

    def test_code_request_re_exists_at_module_level(self):
        from orchestrator import _CODE_REQUEST_RE
        assert isinstance(_CODE_REQUEST_RE, re.Pattern)

    def test_code_request_re_matches(self):
        from orchestrator import _CODE_REQUEST_RE
        assert _CODE_REQUEST_RE.search("write a function to parse JSON")
        assert _CODE_REQUEST_RE.search("create a class for the user model")
        assert _CODE_REQUEST_RE.search("build an API endpoint")
        assert _CODE_REQUEST_RE.search("implement a service for auth")

    def test_codebase_intent_re_exists_at_module_level(self):
        from orchestrator import _CODEBASE_INTENT_RE
        assert isinstance(_CODEBASE_INTENT_RE, re.Pattern)

    def test_codebase_intent_re_matches(self):
        from orchestrator import _CODEBASE_INTENT_RE
        assert _CODEBASE_INTENT_RE.search("review the auth module")
        assert _CODEBASE_INTENT_RE.search("implement the feature")
        assert _CODEBASE_INTENT_RE.search("work on epic E1")
        assert _CODEBASE_INTENT_RE.search("look at the files")
        assert _CODEBASE_INTENT_RE.search("check the endpoint")

    def test_file_error_re_exists_at_module_level(self):
        from orchestrator import _FILE_ERROR_RE
        assert isinstance(_FILE_ERROR_RE, re.Pattern)

    def test_file_error_re_matches(self):
        from orchestrator import _FILE_ERROR_RE
        assert _FILE_ERROR_RE.match("I couldn't find the requested file")
        assert _FILE_ERROR_RE.match("No codebase is currently loaded")

    def test_file_error_re_no_match(self):
        from orchestrator import _FILE_ERROR_RE
        assert not _FILE_ERROR_RE.match("Here is the implementation")
        assert not _FILE_ERROR_RE.match("The file has been updated")
