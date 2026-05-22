"""Tests for utils/claude_client.py optimizations."""
from unittest.mock import patch

from utils.claude_client import _check_cli, _cli_checked


class TestCheckCliCache:
    """_check_cli() should only call shutil.which() once, then cache the result."""

    def setup_method(self):
        import utils.claude_client as mod
        mod._cli_checked = False

    def test_which_called_once_across_multiple_checks(self):
        """shutil.which should be called exactly once even after multiple _check_cli() calls."""
        import utils.claude_client as mod
        mod._cli_checked = False

        with patch("utils.claude_client.shutil.which", return_value="/usr/bin/claude") as mock_which:
            _check_cli()
            _check_cli()
            _check_cli()
            assert mock_which.call_count == 1

    def test_raises_when_cli_not_found(self):
        """Should still raise RuntimeError when claude is not in PATH."""
        import utils.claude_client as mod
        mod._cli_checked = False

        import pytest
        with patch("utils.claude_client.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="claude CLI not found"):
                _check_cli()

    def test_cache_flag_is_set_after_success(self):
        """_cli_checked should be True after a successful check."""
        import utils.claude_client as mod
        mod._cli_checked = False

        with patch("utils.claude_client.shutil.which", return_value="/usr/bin/claude"):
            _check_cli()
            assert mod._cli_checked is True

    def test_cache_flag_not_set_after_failure(self):
        """_cli_checked should remain False after a failed check (so retry is possible)."""
        import utils.claude_client as mod
        mod._cli_checked = False

        import pytest
        with patch("utils.claude_client.shutil.which", return_value=None):
            with pytest.raises(RuntimeError):
                _check_cli()
            assert mod._cli_checked is False
