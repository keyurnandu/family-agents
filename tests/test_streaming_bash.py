"""Tests for _run_bash_streaming — live output streaming with idle detection."""
import time
import pytest
from rich.console import Console
from utils.action_executor import _run_bash_streaming, _IDLE_WARNING_SECS


# Use a null console so tests don't pollute stdout
_NULL_CONSOLE = Console(quiet=True)
_CWD = "."


class TestStreamingBashNormal:
    """Commands that finish normally."""

    def test_exit_zero_returns_correct_returncode(self):
        rc, output, timed_out = _run_bash_streaming(
            'python -c "print(42)"', _CWD, 30, _NULL_CONSOLE
        )
        assert rc == 0
        assert timed_out is False

    def test_output_is_captured(self):
        rc, output, timed_out = _run_bash_streaming(
            'python -c "print(\'hello streaming\')"', _CWD, 30, _NULL_CONSOLE
        )
        assert "hello streaming" in output

    def test_nonzero_exit_captured(self):
        rc, output, timed_out = _run_bash_streaming(
            'python -c "raise SystemExit(42)"', _CWD, 30, _NULL_CONSOLE
        )
        assert rc == 42
        assert timed_out is False

    def test_stderr_is_captured(self):
        rc, output, timed_out = _run_bash_streaming(
            'python -c "import sys; sys.stderr.write(\'err line\\n\')"',
            _CWD, 30, _NULL_CONSOLE,
        )
        assert "err line" in output

    def test_multiline_output(self):
        rc, output, timed_out = _run_bash_streaming(
            'python -c "for i in range(5): print(i)"', _CWD, 30, _NULL_CONSOLE
        )
        assert rc == 0
        for i in range(5):
            assert str(i) in output


class TestStreamingBashTimeout:
    """Commands that exceed the timeout ceiling."""

    def test_timeout_sets_timed_out_flag(self):
        rc, output, timed_out = _run_bash_streaming(
            'python -c "import time; time.sleep(60)"', _CWD, 3, _NULL_CONSOLE
        )
        assert timed_out is True
        assert rc is None  # killed, no returncode

    def test_partial_output_captured_before_timeout(self):
        # Use -u (unbuffered) so the print() is flushed to the pipe before
        # we sleep — otherwise Python's default pipe buffering holds the
        # line until the process exits (which never happens before the kill).
        rc, output, timed_out = _run_bash_streaming(
            'python -u -c "print(\'before sleep\'); import time; time.sleep(60)"',
            _CWD, 3, _NULL_CONSOLE,
        )
        assert timed_out is True
        assert "before sleep" in output

    def test_timeout_respects_ceiling(self):
        start = time.monotonic()
        _run_bash_streaming(
            'python -c "import time; time.sleep(60)"', _CWD, 2, _NULL_CONSOLE
        )
        elapsed = time.monotonic() - start
        # Should finish within ceiling + 5s grace (process kill + wait)
        assert elapsed < 10, f"Took {elapsed:.1f}s — timeout not enforced"
