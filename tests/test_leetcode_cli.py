"""Tests for LeetCode CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from aletheia.cli.main import app
from aletheia.core.models import DSAProblemCard, LeetcodeSource
from aletheia.core.storage import AletheiaStorage
from aletheia.leetcode.auth import LeetCodeAuthError, LeetCodeCredentials, save_credentials
from aletheia.leetcode.service import LeetCodeError, SubmissionResult, TestResult
from typer.testing import CliRunner

runner = CliRunner()

# Patch targets: these are the canonical module paths where the functions live.
# The CLI imports them lazily inside functions, so we patch at source.
_AUTH = "aletheia.leetcode.auth"
_SVC = "aletheia.leetcode.service"


@pytest.fixture()
def env_and_storage(tmp_path: Path):
    """Set up a temp storage environment and patch it into the CLI."""
    data_dir = tmp_path / "data"
    state_dir = tmp_path / ".aletheia"
    data_dir.mkdir()
    state_dir.mkdir()

    env = {
        "ALETHEIA_DATA_DIR": str(data_dir),
        "ALETHEIA_STATE_DIR": str(state_dir),
    }

    with patch.dict("os.environ", env, clear=False):
        import aletheia.cli.main as cli_mod

        # Reset the global storage so it gets recreated with our temp dirs
        cli_mod._storage = None
        storage = cli_mod.get_storage()
        yield storage, state_dir
        cli_mod._storage = None


def _save_test_card(storage: AletheiaStorage, **overrides) -> DSAProblemCard:
    """Create and save a DSA problem card with defaults."""
    defaults = dict(
        front="How to trap rain water?",
        back="Two pointers",
        problem_source=LeetcodeSource(
            platform_id="42",
            title="Trapping Rain Water",
            url="https://leetcode.com/problems/trapping-rain-water/",
            difficulty="hard",
            language="python3",
        ),
        code_solution="class Solution:\n    def trap(self, height): pass",
    )
    defaults.update(overrides)
    card = DSAProblemCard(**defaults)
    storage.save_card(card)
    return card


class TestLogin:
    """Tests for the login command."""

    def test_login_browser_success(self, env_and_storage):
        """Test login via browser cookie extraction."""
        storage, state_dir = env_and_storage

        mock_service = MagicMock()
        mock_service.whoami.return_value = "testuser"

        with (
            patch(
                f"{_AUTH}.extract_browser_cookies",
                return_value=("csrf123", "session456"),
            ),
            patch(f"{_SVC}.LeetCodeService", return_value=mock_service),
            patch(f"{_AUTH}.save_credentials") as mock_save,
        ):
            result = runner.invoke(app, ["leetcode", "login"])

        assert result.exit_code == 0
        assert "testuser" in result.output
        mock_save.assert_called_once()

    def test_login_manual_fallback(self, env_and_storage):
        """Test login falls back to manual paste on browser failure."""
        storage, state_dir = env_and_storage

        mock_service = MagicMock()
        mock_service.whoami.return_value = "manualuser"

        with (
            patch(
                f"{_AUTH}.extract_browser_cookies",
                side_effect=LeetCodeAuthError("no browser"),
            ),
            patch(f"{_SVC}.LeetCodeService", return_value=mock_service),
            patch(f"{_AUTH}.save_credentials"),
        ):
            result = runner.invoke(app, ["leetcode", "login"], input="my_csrf\nmy_session\n")

        assert result.exit_code == 0
        assert "manualuser" in result.output

    def test_login_invalid_creds(self, env_and_storage):
        """Test login failure with invalid credentials."""
        storage, state_dir = env_and_storage

        with (
            patch(
                f"{_AUTH}.extract_browser_cookies",
                return_value=("bad_csrf", "bad_session"),
            ),
            patch(f"{_SVC}.LeetCodeService", side_effect=LeetCodeError("invalid")),
        ):
            result = runner.invoke(app, ["leetcode", "login"])

        assert result.exit_code == 1
        assert "failed" in result.output.lower()


class TestStatus:
    """Tests for the status command."""

    def test_status_logged_in(self, env_and_storage):
        """Test status when logged in."""
        storage, state_dir = env_and_storage

        mock_service = MagicMock()
        mock_service.whoami.return_value = "activeuser"

        creds = LeetCodeCredentials(
            csrftoken="c",
            leetcode_session="s",
            username="activeuser",
            stored_at="2025-01-01T00:00:00",
        )
        save_credentials(state_dir, creds)

        with patch(f"{_SVC}.LeetCodeService", return_value=mock_service):
            result = runner.invoke(app, ["leetcode", "status"])

        assert result.exit_code == 0
        assert "activeuser" in result.output

    def test_status_not_logged_in(self, env_and_storage):
        """Test status when not logged in."""
        storage, state_dir = env_and_storage

        result = runner.invoke(app, ["leetcode", "status"])

        assert result.exit_code == 0
        assert "Not logged in" in result.output

    def test_status_expired(self, env_and_storage):
        """Test status when session has expired."""
        storage, state_dir = env_and_storage

        creds = LeetCodeCredentials(
            csrftoken="c",
            leetcode_session="s",
            username="expireduser",
            stored_at="2025-01-01T00:00:00",
        )
        save_credentials(state_dir, creds)

        mock_service = MagicMock()
        mock_service.whoami.side_effect = LeetCodeError("expired")

        with patch(f"{_SVC}.LeetCodeService", return_value=mock_service):
            result = runner.invoke(app, ["leetcode", "status"])

        assert result.exit_code == 0
        assert "expired" in result.output.lower()


class TestSubmit:
    """Tests for the submit command."""

    def test_submit_full_flow(self, env_and_storage):
        """Test full submit flow: test passes -> confirm -> submit accepted."""
        storage, state_dir = env_and_storage
        card = _save_test_card(storage)

        creds = LeetCodeCredentials(
            csrftoken="c", leetcode_session="s", username="u", stored_at="now"
        )
        save_credentials(state_dir, creds)

        mock_service = MagicMock()
        mock_service.resolve_question_id.return_value = "317"
        mock_service.test_solution.return_value = TestResult(
            passed=True, total_cases=3, passed_cases=3
        )
        mock_service.submit_solution.return_value = SubmissionResult(
            status="Accepted",
            passed=True,
            runtime_ms=40,
            runtime_percentile=85.0,
            memory_kb=16000,
            memory_percentile=70.0,
        )

        with patch(f"{_SVC}.LeetCodeService", return_value=mock_service):
            result = runner.invoke(app, ["leetcode", "submit", card.id[:8]], input="y\n")

        assert result.exit_code == 0
        assert "Accepted" in result.output

    def test_submit_missing_source(self, env_and_storage):
        """Test submit with missing problem source."""
        storage, state_dir = env_and_storage
        card = _save_test_card(storage, problem_source=None)

        creds = LeetCodeCredentials(
            csrftoken="c", leetcode_session="s", username="u", stored_at="now"
        )
        save_credentials(state_dir, creds)

        result = runner.invoke(app, ["leetcode", "submit", card.id[:8]])
        assert result.exit_code == 1
        assert "problem_source" in result.output.lower()

    def test_submit_missing_solution(self, env_and_storage):
        """Test submit with missing code solution."""
        storage, state_dir = env_and_storage
        card = _save_test_card(storage, code_solution=None)

        creds = LeetCodeCredentials(
            csrftoken="c", leetcode_session="s", username="u", stored_at="now"
        )
        save_credentials(state_dir, creds)

        with patch(f"{_SVC}.LeetCodeService", return_value=MagicMock()):
            result = runner.invoke(app, ["leetcode", "submit", card.id[:8]])

        assert result.exit_code == 1
        assert "code_solution" in result.output.lower()

    def test_submit_test_failure_stops(self, env_and_storage):
        """Test that failing tests prevent submission."""
        storage, state_dir = env_and_storage
        card = _save_test_card(storage)

        creds = LeetCodeCredentials(
            csrftoken="c", leetcode_session="s", username="u", stored_at="now"
        )
        save_credentials(state_dir, creds)

        mock_service = MagicMock()
        mock_service.resolve_question_id.return_value = "317"
        mock_service.test_solution.return_value = TestResult(
            passed=False, total_cases=3, passed_cases=1
        )

        with patch(f"{_SVC}.LeetCodeService", return_value=mock_service):
            result = runner.invoke(app, ["leetcode", "submit", card.id[:8]])

        assert result.exit_code == 1
        assert "failed" in result.output.lower()
        mock_service.submit_solution.assert_not_called()


class TestSetSolution:
    """Tests for the set-solution command."""

    def test_set_solution_file(self, env_and_storage, tmp_path: Path):
        """Test setting solution from a file."""
        storage, state_dir = env_and_storage
        card = _save_test_card(storage)

        solution_file = tmp_path / "solution.py"
        solution_file.write_text("class Solution: pass")

        result = runner.invoke(
            app,
            ["leetcode", "set-solution", card.id[:8], "--file", str(solution_file)],
        )

        assert result.exit_code == 0
        assert "updated" in result.output.lower()

        # Verify card was updated
        updated = storage.load_card(card.id)
        assert str(solution_file.resolve()) in updated.code_solution

    def test_set_solution_with_language(self, env_and_storage, tmp_path: Path):
        """Test setting solution with --language flag."""
        storage, state_dir = env_and_storage
        card = _save_test_card(storage)

        solution_file = tmp_path / "solution.cpp"
        solution_file.write_text("class Solution {};")

        result = runner.invoke(
            app,
            [
                "leetcode",
                "set-solution",
                card.id[:8],
                "--file",
                str(solution_file),
                "--language",
                "cpp",
            ],
        )

        assert result.exit_code == 0
        updated = storage.load_card(card.id)
        assert updated.problem_source.language == "cpp"

    def test_set_solution_editor(self, env_and_storage):
        """Test setting solution via editor."""
        storage, state_dir = env_and_storage
        card = _save_test_card(storage)

        # Mock subprocess.run to simulate editor writing content
        def mock_editor(args, check=False):
            # Write content to the temp file the editor was given
            with open(args[1], "w") as f:
                f.write("def solve(): return 42")

        with patch("aletheia.cli.leetcode.subprocess.run", side_effect=mock_editor):
            result = runner.invoke(app, ["leetcode", "set-solution", card.id[:8]])

        assert result.exit_code == 0
        updated = storage.load_card(card.id)
        assert "def solve()" in updated.code_solution
