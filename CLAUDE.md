# Aletheia

## Git Workflow

- **Never push directly to `main`**. All changes go through PRs.
- Always create feature branches from `main`: `git checkout -b <branch> main`
- This repo uses **squash merges only**. Use `gh pr merge --squash` for all PR merges. Never attempt merge commits.
- Delete local feature branches after merging.
- Commit messages use conventional commits (feat:, fix:, refactor:, docs:, test:, chore:).

## Code Quality

- Ruff v0.15.0 handles both linting and formatting (configured in `.pre-commit-config.yaml`).
- Line length limit is **100** characters (set in `pyproject.toml`).
- Pre-commit hooks run automatically on commit. If a commit fails due to hooks, fix the issues and create a **new** commit (don't amend).
- Run `.venv/bin/pytest tests/ -x -q` to verify tests pass before committing.

## Documentation

- When making changes, also update any affected:
  - `docs/` files (architecture, vision, implementation docs)
  - `README.md`
  - Function signatures, docstrings, and comments
- Keep docs and code in sync in the same PR — don't defer doc updates to follow-up work.

## Project Structure

- Source code: `src/aletheia/`
- Tests: `tests/` (pytest, class-based organization, temp dirs)
- CLI entry point: `src/aletheia/cli/main.py` (Typer-based)
- Storage: JSON files (cards) + SQLite (reviews, FSRS, search index)
