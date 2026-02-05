"""FSRS scheduler wrapper for Aletheia."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum

from fsrs import Card as FSRSCard
from fsrs import Rating, State
from fsrs import Scheduler as FSRSScheduler

from aletheia.core.storage import ReviewDatabase


class ReviewRating(IntEnum):
    """Rating enum matching FSRS with friendlier names."""

    AGAIN = 1  # Forgot completely
    HARD = 2  # Remembered with significant difficulty
    GOOD = 3  # Remembered with some effort
    EASY = 4  # Remembered effortlessly


@dataclass
class ReviewResult:
    """Result of reviewing a card."""

    card_id: str
    rating: ReviewRating
    reviewed_at: datetime
    due_next: datetime
    interval_days: float
    stability: float
    difficulty: float
    state: str  # 'learning', 'review', 'relearning'


class AletheiaScheduler:
    """Wraps py-fsrs Scheduler with Aletheia storage integration."""

    def __init__(self, db: ReviewDatabase, desired_retention: float = 0.9):
        """Initialize scheduler.

        Args:
            db: ReviewDatabase instance for state persistence
            desired_retention: Target probability of recall (default 0.9 = 90%)
        """
        self.db = db
        self.fsrs = FSRSScheduler(desired_retention=desired_retention)

    def get_due_cards(self, limit: int = 20) -> list[str]:
        """Get card IDs due for review, prioritizing overdue cards."""
        return self.db.get_due_cards(limit)

    def get_new_cards(self, limit: int = 10) -> list[str]:
        """Get card IDs that have never been reviewed."""
        return self.db.get_new_cards(limit)

    def review_card(self, card_id: str, rating: ReviewRating) -> ReviewResult:
        """Review a card and update its state.

        Args:
            card_id: The card's unique identifier
            rating: User's rating (AGAIN, HARD, GOOD, EASY)

        Returns:
            ReviewResult with updated scheduling information
        """
        now = datetime.now(UTC)

        # 1. Load current state from DB
        state = self.db.get_card_state(card_id)

        # 2. Create FSRS Card from state
        fsrs_card = self._state_to_fsrs_card(state)

        # 3. Process review with FSRS
        reviewed_card, _review_log = self.fsrs.review_card(fsrs_card, Rating(rating.value), now)

        # 4. Calculate interval
        interval_days = 0.0
        if reviewed_card.due and reviewed_card.last_review:
            delta = reviewed_card.due - reviewed_card.last_review
            interval_days = delta.total_seconds() / 86400

        # 5. Save updated state to DB
        self._save_card_state(card_id, reviewed_card, state)

        # 6. Log the review
        self._log_review(card_id, state, reviewed_card, rating.value, now)

        # 7. Return result
        return ReviewResult(
            card_id=card_id,
            rating=rating,
            reviewed_at=now,
            due_next=reviewed_card.due,
            interval_days=interval_days,
            stability=reviewed_card.stability or 0.0,
            difficulty=reviewed_card.difficulty or 0.0,
            state=self._state_name(reviewed_card.state),
        )

    def get_card_state(self, card_id: str) -> dict | None:
        """Get the current FSRS state for a card."""
        return self.db.get_card_state(card_id)

    def _state_to_fsrs_card(self, state: dict | None) -> FSRSCard:
        """Convert DB state to FSRS Card object."""
        if state is None or state.get("state") == "new":
            return FSRSCard()  # New card with default values

        # Parse timestamps
        due = None
        if state.get("due"):
            due = datetime.fromisoformat(state["due"])
            if due.tzinfo is None:
                due = due.replace(tzinfo=UTC)

        last_review = None
        if state.get("last_review"):
            last_review = datetime.fromisoformat(state["last_review"])
            if last_review.tzinfo is None:
                last_review = last_review.replace(tzinfo=UTC)

        return FSRSCard(
            state=State(self._state_value(state.get("state", "new"))),
            stability=state.get("stability", 0.0),
            difficulty=state.get("difficulty", 0.0),
            due=due,
            last_review=last_review,
            step=state.get("step"),
        )

    def _save_card_state(self, card_id: str, fsrs_card: FSRSCard, prev_state: dict | None) -> None:
        """Save FSRS Card state to database."""
        # Calculate reps and lapses
        prev_reps = prev_state.get("reps", 0) if prev_state else 0
        prev_lapses = prev_state.get("lapses", 0) if prev_state else 0

        # Increment reps
        reps = prev_reps + 1

        # Increment lapses if card went to relearning
        lapses = prev_lapses
        if fsrs_card.state == State.Relearning:
            lapses += 1

        self.db.upsert_card_state(
            card_id=card_id,
            stability=fsrs_card.stability or 0.0,
            difficulty=fsrs_card.difficulty or 0.0,
            due=fsrs_card.due,
            last_review=fsrs_card.last_review,
            reps=reps,
            lapses=lapses,
            state=self._state_name(fsrs_card.state),
        )

    def _log_review(
        self,
        card_id: str,
        state_before: dict | None,
        fsrs_card: FSRSCard,
        rating: int,
        reviewed_at: datetime,
    ) -> None:
        """Log review for FSRS optimizer training."""
        # Calculate elapsed days since last review
        elapsed_days = None
        scheduled_days = None

        if state_before and state_before.get("last_review"):
            last = datetime.fromisoformat(state_before["last_review"])
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            elapsed_days = (reviewed_at - last).total_seconds() / 86400

            # Calculate scheduled days (original interval)
            if state_before.get("due"):
                due = datetime.fromisoformat(state_before["due"])
                if due.tzinfo is None:
                    due = due.replace(tzinfo=UTC)
                scheduled_days = (due - last).total_seconds() / 86400

        self.db.log_review(
            card_id=card_id,
            rating=rating,
            elapsed_days=elapsed_days,
            scheduled_days=scheduled_days,
            stability_before=state_before.get("stability", 0.0) if state_before else 0.0,
            stability_after=fsrs_card.stability or 0.0,
            difficulty_before=(state_before.get("difficulty", 0.0) if state_before else 0.0),
            difficulty_after=fsrs_card.difficulty or 0.0,
            state_before=state_before.get("state", "new") if state_before else "new",
            state_after=self._state_name(fsrs_card.state),
        )

    @staticmethod
    def _state_name(state: State) -> str:
        """Convert FSRS State enum to string name."""
        mapping = {
            State.Learning: "learning",
            State.Review: "review",
            State.Relearning: "relearning",
        }
        return mapping.get(state, "learning")

    @staticmethod
    def _state_value(name: str) -> int:
        """Convert state name to FSRS State value."""
        mapping = {
            "new": State.Learning.value,
            "learning": State.Learning.value,
            "review": State.Review.value,
            "relearning": State.Relearning.value,
        }
        return mapping.get(name, State.Learning.value)
