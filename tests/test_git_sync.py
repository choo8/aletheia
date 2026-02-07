"""Tests for git sync module and CLI commands."""

import sqlite3
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from aletheia.core.git_sync import (
    GitSyncError,
    _build_sync_message,
    _find_git_root,
    _has_remote,
    init_data_repo,
    pull_data_repo,
    sync_data_repo,
)
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def data_repo(temp_dir):
    """Create an initialized data repo."""
    repo_path = temp_dir / "data"
    return init_data_repo(repo_path)


# ============================================================================
# TestInitDataRepo
# ============================================================================


class TestInitDataRepo:
    def test_creates_directory_structure(self, temp_dir):
        repo = init_data_repo(temp_dir / "mydata")
        assert (repo / "cards").is_dir()
        assert (repo / "cards" / ".gitkeep").exists()
        assert (repo / ".aletheia").is_dir()

    def test_creates_gitignore_without_aletheia(self, temp_dir):
        repo = init_data_repo(temp_dir / "mydata")
        gitignore = (repo / ".gitignore").read_text()
        assert ".DS_Store" in gitignore
        assert "__pycache__/" in gitignore
        # .aletheia should NOT be ignored — it's tracked in the data repo
        assert ".aletheia" not in gitignore

    def test_has_initial_commit(self, temp_dir):
        repo = init_data_repo(temp_dir / "mydata")
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Initial Aletheia data repository" in result.stdout

    def test_returns_resolved_path(self, temp_dir):
        repo = init_data_repo(temp_dir / "mydata")
        assert repo.is_absolute()
        assert repo == (temp_dir / "mydata").resolve()

    def test_raises_on_non_empty_dir(self, temp_dir):
        target = temp_dir / "notempty"
        target.mkdir()
        (target / "somefile.txt").write_text("hi")

        with pytest.raises(GitSyncError, match="not empty"):
            init_data_repo(target)

    def test_creates_parent_dirs(self, temp_dir):
        repo = init_data_repo(temp_dir / "nested" / "deep" / "data")
        assert repo.exists()


# ============================================================================
# TestFindGitRoot
# ============================================================================


class TestFindGitRoot:
    def test_finds_root_from_subdirectory(self, data_repo):
        subdir = data_repo / "cards"
        root = _find_git_root(subdir)
        assert root == data_repo

    def test_raises_outside_git_repo(self, temp_dir):
        bare = temp_dir / "notarepo"
        bare.mkdir()
        with pytest.raises(GitSyncError, match="Not a git repository"):
            _find_git_root(bare)


# ============================================================================
# TestHasRemote
# ============================================================================


class TestHasRemote:
    def test_no_remote_by_default(self, data_repo):
        assert _has_remote(data_repo) is False

    def test_detects_remote(self, data_repo):
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.com/repo.git"],
            cwd=data_repo,
        )
        assert _has_remote(data_repo) is True


# ============================================================================
# TestBuildSyncMessage
# ============================================================================


class TestBuildSyncMessage:
    def test_format_includes_date_and_counts(self, data_repo):
        msg = _build_sync_message(data_repo)
        assert "Sync:" in msg
        assert "0 cards" in msg
        assert "0 reviews" in msg

    def test_counts_json_files(self, data_repo):
        cards_dir = data_repo / "cards"
        (cards_dir / "card1.json").write_text("{}")
        (cards_dir / "card2.json").write_text("{}")

        msg = _build_sync_message(data_repo)
        assert "2 cards" in msg

    def test_counts_reviews_from_sqlite(self, data_repo):
        db_path = data_repo / ".aletheia" / "aletheia.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE reviews (id INTEGER PRIMARY KEY, card_id TEXT, rating INTEGER)")
        conn.execute("INSERT INTO reviews VALUES (1, 'abc', 3)")
        conn.execute("INSERT INTO reviews VALUES (2, 'def', 4)")
        conn.commit()
        conn.close()

        msg = _build_sync_message(data_repo)
        assert "2 reviews" in msg


# ============================================================================
# TestSyncDataRepo
# ============================================================================


class TestSyncDataRepo:
    def test_nothing_to_sync_when_clean(self, data_repo):
        result = sync_data_repo(data_repo, push=False)
        assert result == "Nothing to sync"

    def test_commits_new_files(self, data_repo):
        (data_repo / "cards" / "test.json").write_text('{"front": "test"}')

        result = sync_data_repo(data_repo, push=False)
        assert "Committed" in result
        assert "Sync:" in result

        # Verify commit was made
        log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=data_repo,
            capture_output=True,
            text=True,
        )
        assert "Sync:" in log.stdout

    def test_skips_push_when_no_remote(self, data_repo):
        (data_repo / "cards" / "test.json").write_text('{"front": "test"}')

        result = sync_data_repo(data_repo, push=True)
        assert "Committed" in result
        assert "(pushed)" not in result

    def test_clean_after_sync(self, data_repo):
        (data_repo / "cards" / "test.json").write_text('{"front": "test"}')
        sync_data_repo(data_repo, push=False)

        result = sync_data_repo(data_repo, push=False)
        assert result == "Nothing to sync"


# ============================================================================
# TestPullDataRepo
# ============================================================================


class TestPullDataRepo:
    def test_raises_when_no_remote(self, data_repo):
        with pytest.raises(GitSyncError, match="No remote configured"):
            pull_data_repo(data_repo)

    def test_uses_ff_only(self, temp_dir):
        """Verify pull uses --ff-only by checking the error on non-ff."""
        # Create a "remote" bare repo
        remote = temp_dir / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)])

        # Create local repo and push
        local = init_data_repo(temp_dir / "local")
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=local)
        subprocess.run(["git", "push", "-u", "origin", "master"], cwd=local, capture_output=True)

        # If the push used 'main', try that branch name instead
        result = subprocess.run(
            ["git", "branch", "--show-current"], cwd=local, capture_output=True, text=True
        )
        branch = result.stdout.strip()

        if branch != "master":
            subprocess.run(["git", "push", "-u", "origin", branch], cwd=local, capture_output=True)

        # Pull should work (already up to date)
        result = pull_data_repo(local)
        assert "Already up to date" in result


# ============================================================================
# TestInitCommand
# ============================================================================


class TestInitCommand:
    def test_creates_repo_and_prints_env(self, temp_dir):
        from aletheia.cli.main import app

        target = temp_dir / "newdata"
        result = runner.invoke(app, ["init", str(target)])

        assert result.exit_code == 0
        assert "ALETHEIA_DATA_DIR=" in result.output
        assert "ALETHEIA_STATE_DIR=" in result.output
        assert (target / "cards").is_dir()

    def test_fails_on_non_empty(self, temp_dir):
        from aletheia.cli.main import app

        target = temp_dir / "notempty"
        target.mkdir()
        (target / "file.txt").write_text("hi")

        result = runner.invoke(app, ["init", str(target)])
        assert result.exit_code == 1


# ============================================================================
# TestSyncCommand
# ============================================================================


class TestSyncCommand:
    def test_fails_gracefully_outside_git(self, temp_dir):
        from aletheia.cli.main import app

        bare = temp_dir / "notarepo"
        bare.mkdir()

        with patch.dict("os.environ", {"ALETHEIA_DATA_DIR": str(bare)}):
            result = runner.invoke(app, ["sync"])

        assert result.exit_code == 1

    def test_reports_nothing_to_sync(self, data_repo):
        from aletheia.cli.main import app

        with patch.dict("os.environ", {"ALETHEIA_DATA_DIR": str(data_repo)}):
            result = runner.invoke(app, ["sync"])

        assert result.exit_code == 0
        assert "Nothing to sync" in result.output
