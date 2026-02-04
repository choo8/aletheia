"""Storage layer for cards (JSON files) and operational data (SQLite)."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from aletheia.core.models import AnyCard, CardType, card_from_dict


class CardStorage:
    """Manages card storage as JSON files."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.cards_dir = data_dir / "cards"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        for card_type in CardType:
            type_dir = self.cards_dir / card_type.value.replace("-", "/")
            type_dir.mkdir(parents=True, exist_ok=True)

    def _get_card_path(self, card: AnyCard) -> Path:
        """Get the file path for a card."""
        type_dir = self.cards_dir / card.type.value.replace("-", "/")
        return type_dir / f"{card.id}.json"

    def _get_card_path_by_id(self, card_id: str, card_type: CardType | None = None) -> Path | None:
        """Find card path by ID, optionally filtering by type."""
        if card_type:
            type_dir = self.cards_dir / card_type.value.replace("-", "/")
            path = type_dir / f"{card_id}.json"
            return path if path.exists() else None

        # Search all directories
        for type_dir in self.cards_dir.rglob("*.json"):
            if type_dir.stem == card_id:
                return type_dir
        return None

    def save(self, card: AnyCard) -> Path:
        """Save a card to a JSON file."""
        card.touch()
        path = self._get_card_path(card)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(card.model_dump(mode="json"), f, indent=2, default=str)

        return path

    def load(self, card_id: str, card_type: CardType | None = None) -> AnyCard | None:
        """Load a card by ID."""
        path = self._get_card_path_by_id(card_id, card_type)
        if path is None or not path.exists():
            return None

        with open(path) as f:
            data = json.load(f)

        return card_from_dict(data)

    def delete(self, card_id: str) -> bool:
        """Delete a card by ID."""
        path = self._get_card_path_by_id(card_id)
        if path is None or not path.exists():
            return False

        path.unlink()
        return True

    def list_all(
        self,
        card_type: CardType | None = None,
        taxonomy: list[str] | None = None,
        tags: list[str] | None = None,
        maturity: str | None = None,
    ) -> list[AnyCard]:
        """List all cards, optionally filtered."""
        cards = []

        if card_type:
            search_dirs = [self.cards_dir / card_type.value.replace("-", "/")]
        else:
            search_dirs = [self.cards_dir]

        for search_dir in search_dirs:
            for path in search_dir.rglob("*.json"):
                with open(path) as f:
                    data = json.load(f)

                card = card_from_dict(data)

                # Apply filters
                if taxonomy and not all(t in card.taxonomy for t in taxonomy):
                    continue
                if tags and not any(t in card.tags for t in tags):
                    continue
                if maturity and card.maturity.value != maturity:
                    continue

                cards.append(card)

        return cards

    def search(self, query: str) -> list[AnyCard]:
        """Simple search across card content."""
        query = query.lower()
        results = []

        for path in self.cards_dir.rglob("*.json"):
            with open(path) as f:
                data = json.load(f)

            # Search in front, back, and common fields
            # Use 'or ""' to handle None values
            searchable = " ".join(
                [
                    data.get("front") or "",
                    data.get("back") or "",
                    data.get("name") or "",
                    data.get("intuition") or "",
                    " ".join(data.get("tags") or []),
                    " ".join(data.get("taxonomy") or []),
                ]
            ).lower()

            if query in searchable:
                results.append(card_from_dict(data))

        return results


class ReviewDatabase:
    """SQLite database for review logs and FSRS state."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._connection() as conn:
            conn.executescript(
                """
                -- FSRS card states
                CREATE TABLE IF NOT EXISTS card_states (
                    card_id TEXT PRIMARY KEY,
                    stability REAL NOT NULL DEFAULT 0.0,
                    difficulty REAL NOT NULL DEFAULT 0.0,
                    due TEXT,
                    last_review TEXT,
                    reps INTEGER NOT NULL DEFAULT 0,
                    lapses INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                -- Review log (append-only for FSRS optimizer)
                CREATE TABLE IF NOT EXISTS review_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_id TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    elapsed_days REAL,
                    scheduled_days REAL,
                    stability_before REAL,
                    stability_after REAL,
                    difficulty_before REAL,
                    difficulty_after REAL,
                    state_before TEXT,
                    state_after TEXT
                );

                -- Card edit history
                CREATE TABLE IF NOT EXISTS edit_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_id TEXT NOT NULL,
                    edited_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    field_name TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT
                );

                -- Full-text search index
                CREATE VIRTUAL TABLE IF NOT EXISTS card_search USING fts5(
                    card_id,
                    front,
                    back,
                    name,
                    tags,
                    taxonomy,
                    content='',
                    contentless_delete=1
                );

                -- Create indexes
                CREATE INDEX IF NOT EXISTS idx_review_logs_card_id ON review_logs(card_id);
                CREATE INDEX IF NOT EXISTS idx_review_logs_reviewed_at ON review_logs(reviewed_at);
                CREATE INDEX IF NOT EXISTS idx_card_states_due ON card_states(due);
            """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_card_state(self, card_id: str) -> dict | None:
        """Get FSRS state for a card."""
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM card_states WHERE card_id = ?", (card_id,)).fetchone()
            return dict(row) if row else None

    def upsert_card_state(
        self,
        card_id: str,
        stability: float,
        difficulty: float,
        due: datetime | None,
        last_review: datetime | None,
        reps: int,
        lapses: int,
        state: str,
    ) -> None:
        """Insert or update FSRS state for a card."""
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO card_states (
                    card_id, stability, difficulty, due, last_review,
                    reps, lapses, state, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(card_id) DO UPDATE SET
                    stability = excluded.stability,
                    difficulty = excluded.difficulty,
                    due = excluded.due,
                    last_review = excluded.last_review,
                    reps = excluded.reps,
                    lapses = excluded.lapses,
                    state = excluded.state,
                    updated_at = CURRENT_TIMESTAMP
            """,
                (
                    card_id,
                    stability,
                    difficulty,
                    due.isoformat() if due else None,
                    last_review.isoformat() if last_review else None,
                    reps,
                    lapses,
                    state,
                ),
            )

    def log_review(
        self,
        card_id: str,
        rating: int,
        elapsed_days: float | None,
        scheduled_days: float | None,
        stability_before: float,
        stability_after: float,
        difficulty_before: float,
        difficulty_after: float,
        state_before: str,
        state_after: str,
    ) -> None:
        """Log a review for FSRS optimizer training."""
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO review_logs (
                    card_id, reviewed_at, rating, elapsed_days, scheduled_days,
                    stability_before, stability_after, difficulty_before, difficulty_after,
                    state_before, state_after
                ) VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    card_id,
                    rating,
                    elapsed_days,
                    scheduled_days,
                    stability_before,
                    stability_after,
                    difficulty_before,
                    difficulty_after,
                    state_before,
                    state_after,
                ),
            )

    def get_due_cards(self, limit: int = 20) -> list[str]:
        """Get card IDs that are due for review."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT card_id FROM card_states
                WHERE due IS NULL OR due <= datetime('now')
                ORDER BY due ASC NULLS FIRST
                LIMIT ?
            """,
                (limit,),
            ).fetchall()
            return [row["card_id"] for row in rows]

    def get_new_cards(self, limit: int = 10) -> list[str]:
        """Get card IDs that have never been reviewed."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT card_id FROM card_states
                WHERE state = 'new' AND reps = 0
                LIMIT ?
            """,
                (limit,),
            ).fetchall()
            return [row["card_id"] for row in rows]

    def index_card(self, card: AnyCard) -> None:
        """Add or update card in search index."""
        name = getattr(card, "name", "")
        with self._connection() as conn:
            # Delete existing entry
            conn.execute("DELETE FROM card_search WHERE card_id = ?", (card.id,))
            # Insert new entry
            conn.execute(
                """
                INSERT INTO card_search (card_id, front, back, name, tags, taxonomy)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    card.id,
                    card.front,
                    card.back,
                    name,
                    " ".join(card.tags),
                    " ".join(card.taxonomy),
                ),
            )

    def search_cards(self, query: str) -> list[str]:
        """Full-text search for cards."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT card_id FROM card_search
                WHERE card_search MATCH ?
                ORDER BY rank
            """,
                (query,),
            ).fetchall()
            return [row["card_id"] for row in rows]

    def get_stats(self) -> dict:
        """Get review statistics."""
        with self._connection() as conn:
            total_cards = conn.execute("SELECT COUNT(*) FROM card_states").fetchone()[0]
            total_reviews = conn.execute("SELECT COUNT(*) FROM review_logs").fetchone()[0]
            due_today = conn.execute(
                """
                SELECT COUNT(*) FROM card_states
                WHERE due IS NOT NULL AND date(due) <= date('now')
            """
            ).fetchone()[0]
            new_cards = conn.execute(
                "SELECT COUNT(*) FROM card_states WHERE state = 'new'"
            ).fetchone()[0]

            return {
                "total_cards": total_cards,
                "total_reviews": total_reviews,
                "due_today": due_today,
                "new_cards": new_cards,
            }


class AletheiaStorage:
    """Combined storage manager for Aletheia."""

    def __init__(self, data_dir: Path | None = None, state_dir: Path | None = None):
        # Default paths
        if data_dir is None:
            data_dir = Path.cwd() / "data"
        if state_dir is None:
            state_dir = Path.cwd() / ".aletheia"

        self.data_dir = data_dir
        self.state_dir = state_dir

        # Initialize storage backends
        self.cards = CardStorage(data_dir)
        self.db = ReviewDatabase(state_dir / "aletheia.db")

    def save_card(self, card: AnyCard) -> Path:
        """Save a card and index it."""
        path = self.cards.save(card)
        self.db.index_card(card)

        # Initialize FSRS state if new card
        if self.db.get_card_state(card.id) is None:
            self.db.upsert_card_state(
                card_id=card.id,
                stability=0.0,
                difficulty=0.0,
                due=None,
                last_review=None,
                reps=0,
                lapses=0,
                state="new",
            )

        return path

    def load_card(self, card_id: str) -> AnyCard | None:
        """Load a card by ID."""
        return self.cards.load(card_id)

    def delete_card(self, card_id: str) -> bool:
        """Delete a card."""
        return self.cards.delete(card_id)

    def list_cards(self, **filters) -> list[AnyCard]:
        """List cards with optional filters."""
        return self.cards.list_all(**filters)

    def search(self, query: str) -> list[AnyCard]:
        """Search cards."""
        # Try FTS first
        card_ids = self.db.search_cards(query)
        if card_ids:
            return [self.cards.load(cid) for cid in card_ids if self.cards.load(cid)]

        # Fall back to simple search
        return self.cards.search(query)
