"""Tests for utils/claude_client.py and utils/llm_providers.py."""
from unittest.mock import patch

from utils.llm_providers import ClaudeCLIProvider


class TestCheckCliCache:
    """ClaudeCLIProvider._check_cli() should only call shutil.which() once."""

    def setup_method(self):
        self.provider = ClaudeCLIProvider()
        self.provider._cli_checked = False

    def test_which_called_once_across_multiple_checks(self):
        """shutil.which should be called exactly once even after multiple checks."""
        with patch("utils.llm_providers.shutil.which", return_value="/usr/bin/claude") as mock_which:
            self.provider._check_cli()
            self.provider._check_cli()
            self.provider._check_cli()
            assert mock_which.call_count == 1

    def test_raises_when_cli_not_found(self):
        """Should still raise RuntimeError when claude is not in PATH."""
        import pytest
        with patch("utils.llm_providers.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="claude CLI not found"):
                self.provider._check_cli()

    def test_cache_flag_is_set_after_success(self):
        """_cli_checked should be True after a successful check."""
        with patch("utils.llm_providers.shutil.which", return_value="/usr/bin/claude"):
            self.provider._check_cli()
            assert self.provider._cli_checked is True

    def test_cache_flag_not_set_after_failure(self):
        """_cli_checked should remain False after a failed check."""
        import pytest
        with patch("utils.llm_providers.shutil.which", return_value=None):
            with pytest.raises(RuntimeError):
                self.provider._check_cli()
            assert self.provider._cli_checked is False


class TestProviderAbstraction:
    """Test that the provider system works correctly."""

    def test_default_provider_is_claude_cli(self):
        from utils.claude_client import get_provider
        provider = get_provider()
        assert provider.name == "claude_cli"

    def test_set_provider_by_name(self):
        from utils.claude_client import set_provider_by_name, get_provider
        old = get_provider()
        try:
            provider = set_provider_by_name("claude_cli")
            assert provider.name == "claude_cli"
            assert get_provider() is provider
        finally:
            from utils.claude_client import set_provider
            set_provider(old)

    def test_unknown_provider_raises(self):
        import pytest
        from utils.llm_providers import create_provider
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider("nonexistent_provider")

    def test_all_providers_have_validate(self):
        from utils.llm_providers import PROVIDERS
        for name, cls in PROVIDERS.items():
            instance = cls()
            ok, msg = instance.validate()
            assert isinstance(ok, bool)
            assert isinstance(msg, str)
