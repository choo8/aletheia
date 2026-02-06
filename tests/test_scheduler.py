"""Tests for the FSRS scheduler."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from aletheia.core.models import DSAProblemCard
from aletheia.core.scheduler import AletheiaScheduler, CardState, ReviewRating, ReviewResult
from aletheia.core.storage import AletheiaStorage
from fsrs import State


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage(temp_dir):
    """Create an AletheiaStorage instance for tests."""
    return AletheiaStorage(temp_dir / "data", temp_dir / ".aletheia")


@pytest.fixture
def scheduler(storage):
    """Create an AletheiaScheduler instance for tests."""
    return AletheiaScheduler(storage.db)


class TestReviewRating:
    """Tests for ReviewRating enum."""

    def test_rating_values(self):
        """Test rating enum values."""
        assert ReviewRating.AGAIN == 1
        assert ReviewRating.HARD == 2
        assert ReviewRating.GOOD == 3
        assert ReviewRating.EASY == 4

    def test_rating_from_int(self):
        """Test creating rating from int."""
        assert ReviewRating(1) == ReviewRating.AGAIN
        assert ReviewRating(3) == ReviewRating.GOOD


class TestCardState:
    """Tests for CardState StrEnum."""

    def test_state_values(self):
        """Test state enum string values."""
        assert CardState.NEW == "new"
        assert CardState.LEARNING == "learning"
        assert CardState.REVIEW == "review"
        assert CardState.RELEARNING == "relearning"

    def test_state_is_str(self):
        """Test that CardState values work as strings."""
        # StrEnum values can be used directly as strings
        assert f"State: {CardState.LEARNING}" == "State: learning"
        assert CardState.REVIEW in ["review", "learning"]

    def test_from_fsrs(self):
        """Test conversion from FSRS State enum."""
        assert CardState.from_fsrs(State.Learning) == CardState.LEARNING
        assert CardState.from_fsrs(State.Review) == CardState.REVIEW
        assert CardState.from_fsrs(State.Relearning) == CardState.RELEARNING

    def test_to_fsrs(self):
        """Test conversion to FSRS State enum."""
        assert CardState.NEW.to_fsrs() == State.Learning
        assert CardState.LEARNING.to_fsrs() == State.Learning
        assert CardState.REVIEW.to_fsrs() == State.Review
        assert CardState.RELEARNING.to_fsrs() == State.Relearning

    def test_roundtrip(self):
        """Test roundtrip conversion FSRS -> CardState -> FSRS."""
        for fsrs_state in [State.Learning, State.Review, State.Relearning]:
            card_state = CardState.from_fsrs(fsrs_state)
            assert card_state.to_fsrs() == fsrs_state


class TestAletheiaScheduler:
    """Tests for AletheiaScheduler."""

    def test_get_new_cards_empty(self, scheduler):
        """Test getting new cards when none exist."""
        new_cards = scheduler.get_new_cards()
        assert new_cards == []

    def test_get_due_cards_empty(self, scheduler):
        """Test getting due cards when none exist."""
        due_cards = scheduler.get_due_cards()
        assert due_cards == []

    def test_new_card_appears_in_new_cards(self, storage, scheduler):
        """Test that a newly saved card appears in new cards list."""
        card = DSAProblemCard(front="What is O(1)?", back="Constant time")
        storage.save_card(card)

        new_cards = scheduler.get_new_cards()
        assert card.id in new_cards

    def test_review_new_card(self, storage, scheduler):
        """Test reviewing a new card."""
        card = DSAProblemCard(front="What is O(n)?", back="Linear time")
        storage.save_card(card)

        result = scheduler.review_card(card.id, ReviewRating.GOOD)

        assert isinstance(result, ReviewResult)
        assert result.card_id == card.id
        assert result.rating == ReviewRating.GOOD
        assert result.state == CardState.LEARNING
        assert result.stability > 0
        assert result.due_next > datetime.now(UTC)

    def test_review_creates_log_entry(self, storage, scheduler):
        """Test that reviewing creates a log entry."""
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        scheduler.review_card(card.id, ReviewRating.GOOD)

        stats = storage.db.get_stats()
        assert stats["total_reviews"] == 1

    def test_review_updates_card_state(self, storage, scheduler):
        """Test that reviewing updates the card state in database."""
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        # Initial state
        state_before = scheduler.get_card_state(card.id)
        assert state_before["state"] == "new"
        assert state_before["reps"] == 0

        # Review
        scheduler.review_card(card.id, ReviewRating.GOOD)

        # Updated state
        state_after = scheduler.get_card_state(card.id)
        assert state_after["state"] == "learning"
        assert state_after["reps"] == 1
        assert state_after["stability"] > 0

    def test_multiple_reviews(self, storage, scheduler):
        """Test multiple reviews of the same card."""
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        # First review
        result1 = scheduler.review_card(card.id, ReviewRating.GOOD)

        # Second review
        result2 = scheduler.review_card(card.id, ReviewRating.GOOD)

        # State should have updated
        state = scheduler.get_card_state(card.id)
        assert state["reps"] == 2
        assert result2.stability >= result1.stability

    def test_review_with_again_rating(self, storage, scheduler):
        """Test reviewing with AGAIN rating."""
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        result = scheduler.review_card(card.id, ReviewRating.AGAIN)

        assert result.rating == ReviewRating.AGAIN
        # Card should be due soon (in learning)

    def test_review_with_easy_rating(self, storage, scheduler):
        """Test reviewing with EASY rating."""
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        result = scheduler.review_card(card.id, ReviewRating.EASY)

        assert result.rating == ReviewRating.EASY
        # Easy cards typically have longer intervals
        assert result.stability > 0

    def test_card_removed_from_new_after_review(self, storage, scheduler):
        """Test that a reviewed card is no longer in new cards list."""
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        # Should be in new cards initially
        assert card.id in scheduler.get_new_cards()

        # Review the card
        scheduler.review_card(card.id, ReviewRating.GOOD)

        # Should no longer be in new cards
        assert card.id not in scheduler.get_new_cards()

    def test_get_due_cards_limit(self, storage, scheduler):
        """Test that get_due_cards respects limit parameter."""
        # Create multiple cards
        for i in range(10):
            card = DSAProblemCard(front=f"Q{i}", back=f"A{i}")
            storage.save_card(card)

        # All should be due (new cards are due immediately)
        due_cards = scheduler.get_due_cards(limit=3)
        assert len(due_cards) <= 3

    def test_desired_retention_parameter(self, storage):
        """Test that desired_retention parameter is accepted."""
        scheduler = AletheiaScheduler(storage.db, desired_retention=0.85)
        assert scheduler.fsrs.desired_retention == 0.85
