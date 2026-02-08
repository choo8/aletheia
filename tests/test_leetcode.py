"""Tests for the LeetCode integration module."""

from http.cookiejar import Cookie
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from aletheia.leetcode.auth import (
    LeetCodeAuthError,
    LeetCodeCredentials,
    clear_credentials,
    extract_browser_cookies,
    get_credentials,
    save_credentials,
)


class TestCredentials:
    """Tests for credential save/load/clear."""

    def test_save_and_load_round_trip(self, tmp_path: Path):
        """Test saving and loading credentials."""
        creds = LeetCodeCredentials(
            csrftoken="token123",
            leetcode_session="session456",
            username="testuser",
            stored_at="2025-01-01T00:00:00+00:00",
        )
        save_credentials(tmp_path, creds)
        loaded = get_credentials(tmp_path)

        assert loaded is not None
        assert loaded.csrftoken == "token123"
        assert loaded.leetcode_session == "session456"
        assert loaded.username == "testuser"
        assert loaded.stored_at == "2025-01-01T00:00:00+00:00"

    def test_save_creates_directory(self, tmp_path: Path):
        """Test that save creates the state directory if needed."""
        nested = tmp_path / "nested" / "dir"
        creds = LeetCodeCredentials(
            csrftoken="t", leetcode_session="s", username="u", stored_at="now"
        )
        path = save_credentials(nested, creds)
        assert path.exists()
        assert nested.exists()

    def test_load_missing_file_returns_none(self, tmp_path: Path):
        """Test that missing file returns None."""
        result = get_credentials(tmp_path)
        assert result is None

    def test_load_corrupt_file_raises(self, tmp_path: Path):
        """Test that corrupt JSON raises LeetCodeAuthError."""
        (tmp_path / "leetcode_auth.json").write_text("not json")
        with pytest.raises(LeetCodeAuthError, match="Corrupt credentials file"):
            get_credentials(tmp_path)

    @patch.dict(
        "os.environ",
        {"LEETCODE_CSRFTOKEN": "env_csrf", "LEETCODE_SESSION": "env_session"},
    )
    def test_env_var_override(self, tmp_path: Path):
        """Test that env vars take precedence over file."""
        # Save file creds
        creds = LeetCodeCredentials(
            csrftoken="file_csrf",
            leetcode_session="file_session",
            username="fileuser",
            stored_at="2025-01-01T00:00:00+00:00",
        )
        save_credentials(tmp_path, creds)

        loaded = get_credentials(tmp_path)
        assert loaded is not None
        assert loaded.csrftoken == "env_csrf"
        assert loaded.leetcode_session == "env_session"
        assert loaded.username == "env"

    @patch.dict("os.environ", {"LEETCODE_CSRFTOKEN": "only_csrf"}, clear=False)
    def test_env_var_partial_does_not_override(self, tmp_path: Path):
        """Test that partial env vars (only CSRF) fall through to file."""
        import os

        os.environ.pop("LEETCODE_SESSION", None)

        creds = LeetCodeCredentials(
            csrftoken="file_csrf",
            leetcode_session="file_session",
            username="fileuser",
            stored_at="2025-01-01T00:00:00+00:00",
        )
        save_credentials(tmp_path, creds)

        loaded = get_credentials(tmp_path)
        assert loaded is not None
        assert loaded.csrftoken == "file_csrf"

    def test_clear_credentials(self, tmp_path: Path):
        """Test clearing credentials."""
        creds = LeetCodeCredentials(
            csrftoken="t", leetcode_session="s", username="u", stored_at="now"
        )
        save_credentials(tmp_path, creds)
        assert (tmp_path / "leetcode_auth.json").exists()

        result = clear_credentials(tmp_path)
        assert result is True
        assert not (tmp_path / "leetcode_auth.json").exists()

    def test_clear_missing_returns_false(self, tmp_path: Path):
        """Test clearing when no credentials exist."""
        result = clear_credentials(tmp_path)
        assert result is False


def _make_cookie(name: str, value: str) -> Cookie:
    """Create a minimal Cookie object for testing."""
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain="leetcode.com",
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
    )


class TestBrowserExtraction:
    """Tests for browser cookie extraction.

    rookiepy is lazily imported inside extract_browser_cookies(), so we mock
    it via sys.modules rather than patching a module-level attribute.
    """

    def _mock_rookiepy(self, cookies):
        """Create a mock rookiepy module that returns the given cookies."""
        mock_rookiepy = MagicMock()
        mock_jar = MagicMock()
        mock_jar.__iter__ = MagicMock(return_value=iter(cookies))
        mock_rookiepy.load.return_value = [{"raw": "data"}]
        mock_rookiepy.to_cookiejar.return_value = mock_jar
        return mock_rookiepy

    def test_extract_success(self):
        """Test successful cookie extraction."""
        mock_rookiepy = self._mock_rookiepy(
            [
                _make_cookie("csrftoken", "csrf_value"),
                _make_cookie("LEETCODE_SESSION", "session_value"),
            ]
        )
        with patch.dict("sys.modules", {"rookiepy": mock_rookiepy}):
            csrf, session = extract_browser_cookies()
        assert csrf == "csrf_value"
        assert session == "session_value"

    def test_extract_not_installed(self):
        """Test error when rookiepy is not installed."""
        with patch.dict("sys.modules", {"rookiepy": None}):
            with pytest.raises(LeetCodeAuthError, match="rookiepy not installed"):
                extract_browser_cookies()

    def test_extract_missing_csrf(self):
        """Test error when csrftoken cookie is missing."""
        mock_rookiepy = self._mock_rookiepy(
            [
                _make_cookie("LEETCODE_SESSION", "session_value"),
            ]
        )
        with patch.dict("sys.modules", {"rookiepy": mock_rookiepy}):
            with pytest.raises(LeetCodeAuthError, match="Missing cookies.*csrftoken"):
                extract_browser_cookies()

    def test_extract_missing_session(self):
        """Test error when LEETCODE_SESSION cookie is missing."""
        mock_rookiepy = self._mock_rookiepy(
            [
                _make_cookie("csrftoken", "csrf_value"),
            ]
        )
        with patch.dict("sys.modules", {"rookiepy": mock_rookiepy}):
            with pytest.raises(LeetCodeAuthError, match="Missing cookies.*LEETCODE_SESSION"):
                extract_browser_cookies()

    def test_extract_rookiepy_failure(self):
        """Test error when rookiepy.load raises."""
        mock_rookiepy = MagicMock()
        mock_rookiepy.load.side_effect = RuntimeError("No browser DB found")
        with patch.dict("sys.modules", {"rookiepy": mock_rookiepy}):
            with pytest.raises(LeetCodeAuthError, match="Failed to extract"):
                extract_browser_cookies()
