"""FSRS scheduler wrapper for Aletheia."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING

from fsrs import Card as FSRSCard
from fsrs import Rating, State
from fsrs import Scheduler as FSRSScheduler

from aletheia.core.storage import ReviewDatabase

if TYPE_CHECKING:
    from aletheia.core.graph import KnowledgeGraph


class ReviewRating(IntEnum):
    """Rating enum matching FSRS with friendlier names."""

    AGAIN = 1  # Forgot completely
    HARD = 2  # Remembered with significant difficulty
    GOOD = 3  # Remembered with some effort
    EASY = 4  # Remembered effortlessly


class CardState(StrEnum):
    """Card review state - a StrEnum wrapper around FSRS State.

    Inherits from StrEnum so values can be used directly as strings
    (e.g., in database storage) while providing type safety and
    conversion methods to/from the FSRS State enum.
    """

    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"

    @classmethod
    def from_fsrs(cls, state: State) -> CardState:
        """Convert from FSRS State enum."""
        mapping = {
            State.Learning: cls.LEARNING,
            State.Review: cls.REVIEW,
            State.Relearning: cls.RELEARNING,
        }
        return mapping.get(state, cls.LEARNING)

    def to_fsrs(self) -> State:
        """Convert to FSRS State enum."""
        mapping = {
            CardState.NEW: State.Learning,
            CardState.LEARNING: State.Learning,
            CardState.REVIEW: State.Review,
            CardState.RELEARNING: State.Relearning,
        }
        return mapping.get(self, State.Learning)


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
    state: CardState
    remediation_ids: list[str] = field(default_factory=list)


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

    def review_card(
        self,
        card_id: str,
        rating: ReviewRating,
        response_time_ms: int | None = None,
    ) -> ReviewResult:
        """Review a card and update its state.

        Args:
            card_id: The card's unique identifier
            rating: User's rating (AGAIN, HARD, GOOD, EASY)
            response_time_ms: Optional response time in milliseconds

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
        self._log_review(card_id, state, reviewed_card, rating.value, now, response_time_ms)

        # 7. Return result
        return ReviewResult(
            card_id=card_id,
            rating=rating,
            reviewed_at=now,
            due_next=reviewed_card.due,
            interval_days=interval_days,
            stability=reviewed_card.stability or 0.0,
            difficulty=reviewed_card.difficulty or 0.0,
            state=CardState.from_fsrs(reviewed_card.state),
        )

    def get_card_state(self, card_id: str) -> dict | None:
        """Get the current FSRS state for a card."""
        return self.db.get_card_state(card_id)

    def get_remediation_cards(self, failed_card_id: str, graph: KnowledgeGraph) -> list[str]:
        """Get prerequisite cards that need remediation after a failure.

        On AGAIN: find prerequisite cards that are overdue or have low
        stability, suggesting the user should review fundamentals.
        """
        prereqs = graph.get_prerequisites(failed_card_id)
        remediation = []
        now = datetime.now(UTC)
        for prereq in prereqs:
            state = self.db.get_card_state(prereq.id)
            if state is None:
                continue
            # Overdue?
            due_str = state.get("due")
            if due_str:
                due = datetime.fromisoformat(due_str)
                if due.tzinfo is None:
                    due = due.replace(tzinfo=UTC)
                if due <= now:
                    remediation.append(prereq.id)
                    continue
            # Low stability?
            stability = state.get("stability") or 0.0
            if stability < 5.0 and state.get("state") != "new":
                remediation.append(prereq.id)
        return remediation

    def _state_to_fsrs_card(self, state: dict | None) -> FSRSCard:
        """Convert DB state to FSRS Card object."""
        if state is None or state.get("state") == CardState.NEW:
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

        card_state = CardState(state.get("state", CardState.NEW))
        return FSRSCard(
            state=card_state.to_fsrs(),
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
            state=CardState.from_fsrs(fsrs_card.state),
        )

    def _log_review(
        self,
        card_id: str,
        state_before: dict | None,
        fsrs_card: FSRSCard,
        rating: int,
        reviewed_at: datetime,
        response_time_ms: int | None = None,
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
            state_before=state_before.get("state", CardState.NEW)
            if state_before
            else CardState.NEW,
            state_after=CardState.from_fsrs(fsrs_card.state),
            response_time_ms=response_time_ms,
        )
