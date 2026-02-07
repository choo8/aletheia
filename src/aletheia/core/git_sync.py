"""Git sync helpers for Aletheia data repositories."""

import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path


class GitSyncError(Exception):
    """Raised when a git sync operation fails."""


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    try:
        return subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise GitSyncError("git is not installed or not on PATH")


def init_data_repo(path: Path) -> Path:
    """Initialize a new Aletheia data repository.

    Creates the directory structure, .gitignore, and initial commit.
    Returns the resolved absolute path.
    """
    path = path.resolve()

    if path.exists() and any(path.iterdir()):
        raise GitSyncError(f"Directory is not empty: {path}")

    # Create directory structure
    (path / "cards").mkdir(parents=True, exist_ok=True)
    (path / "cards" / ".gitkeep").touch()
    (path / ".aletheia").mkdir(exist_ok=True)

    # Write .gitignore (temp files only — NOT .aletheia/)
    gitignore = path / ".gitignore"
    gitignore.write_text("*.swp\n" "*.swo\n" "*~\n" ".DS_Store\n" "__pycache__/\n")

    # Initialize git repo
    result = _run_git(["init"], cwd=path)
    if result.returncode != 0:
        raise GitSyncError(f"git init failed: {result.stderr.strip()}")

    result = _run_git(["add", "-A"], cwd=path)
    if result.returncode != 0:
        raise GitSyncError(f"git add failed: {result.stderr.strip()}")

    result = _run_git(
        ["commit", "-m", "Initial Aletheia data repository"],
        cwd=path,
    )
    if result.returncode != 0:
        raise GitSyncError(f"git commit failed: {result.stderr.strip()}")

    return path


def _find_git_root(data_dir: Path) -> Path:
    """Find the git root for the given data directory."""
    result = _run_git(
        ["rev-parse", "--show-toplevel"],
        cwd=data_dir,
    )
    if result.returncode != 0:
        raise GitSyncError(
            f"Not a git repository: {data_dir}\n"
            "Run 'aletheia init <path>' to create a data repository."
        )
    return Path(result.stdout.strip())


def _has_remote(git_root: Path) -> bool:
    """Check if the git repo has any remotes configured."""
    result = _run_git(["remote"], cwd=git_root)
    return bool(result.stdout.strip())


def _build_sync_message(git_root: Path) -> str:
    """Build a descriptive commit message with date and counts."""
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")

    # Count JSON files in cards/
    cards_dir = git_root / "cards"
    card_count = 0
    if cards_dir.exists():
        card_count = len(list(cards_dir.rglob("*.json")))

    # Count reviews via raw sqlite3 if DB exists
    review_count = 0
    db_path = git_root / ".aletheia" / "aletheia.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT COUNT(*) FROM reviews")
            review_count = cursor.fetchone()[0]
            conn.close()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            pass

    return f"Sync: {date_str} ({card_count} cards, {review_count} reviews)"


def sync_data_repo(data_dir: Path, push: bool = True) -> str:
    """Commit all changes in the data repo and optionally push.

    Returns a summary string.
    """
    git_root = _find_git_root(data_dir)

    # Stage all changes
    result = _run_git(["add", "-A"], cwd=git_root)
    if result.returncode != 0:
        raise GitSyncError(f"git add failed: {result.stderr.strip()}")

    # Check if there's anything to commit
    result = _run_git(["diff", "--cached", "--quiet"], cwd=git_root)
    if result.returncode == 0:
        return "Nothing to sync"

    # Commit
    message = _build_sync_message(git_root)
    result = _run_git(["commit", "-m", message], cwd=git_root)
    if result.returncode != 0:
        raise GitSyncError(f"git commit failed: {result.stderr.strip()}")

    summary = f"Committed: {message}"

    # Push if remote exists
    if push and _has_remote(git_root):
        result = _run_git(["push"], cwd=git_root)
        if result.returncode != 0:
            raise GitSyncError(f"git push failed: {result.stderr.strip()}")
        summary += " (pushed)"

    return summary


def pull_data_repo(data_dir: Path) -> str:
    """Pull latest changes from the remote.

    Uses --ff-only for safety. Raises GitSyncError if non-fast-forward.
    Returns a summary string.
    """
    git_root = _find_git_root(data_dir)

    if not _has_remote(git_root):
        raise GitSyncError(
            "No remote configured. Add one with:\n"
            f"  cd {git_root}\n"
            "  git remote add origin <url>"
        )

    result = _run_git(["pull", "--ff-only"], cwd=git_root)
    if result.returncode != 0:
        raise GitSyncError(
            "Pull failed (non-fast-forward merge required).\n"
            "Resolve manually:\n"
            f"  cd {git_root}\n"
            "  git pull --rebase\n"
            "  # or: git merge origin/main"
        )

    output = result.stdout.strip()
    if "Already up to date" in output:
        return "Already up to date"
    return "Pulled latest changes"
