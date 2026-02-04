"""Tests for Aletheia storage."""

import tempfile
from pathlib import Path

import pytest

from aletheia.core.models import CardType, DSAConceptCard, DSAProblemCard, SystemDesignCard
from aletheia.core.storage import AletheiaStorage, CardStorage, ReviewDatabase


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def card_storage(temp_dir):
    """Create a CardStorage instance for tests."""
    return CardStorage(temp_dir / "data")


@pytest.fixture
def review_db(temp_dir):
    """Create a ReviewDatabase instance for tests."""
    return ReviewDatabase(temp_dir / ".aletheia" / "aletheia.db")


@pytest.fixture
def storage(temp_dir):
    """Create an AletheiaStorage instance for tests."""
    return AletheiaStorage(temp_dir / "data", temp_dir / ".aletheia")


class TestCardStorage:
    """Tests for CardStorage."""

    def test_save_and_load(self, card_storage):
        """Test saving and loading a card."""
        card = DSAProblemCard(
            front="What is O(1)?",
            back="Constant time",
            patterns=["basics"],
        )

        path = card_storage.save(card)
        assert path.exists()

        loaded = card_storage.load(card.id)
        assert loaded is not None
        assert loaded.front == card.front
        assert loaded.back == card.back
        assert loaded.patterns == card.patterns

    def test_delete(self, card_storage):
        """Test deleting a card."""
        card = DSAProblemCard(front="Q", back="A")
        card_storage.save(card)

        assert card_storage.delete(card.id)
        assert card_storage.load(card.id) is None

    def test_list_all(self, card_storage):
        """Test listing all cards."""
        card1 = DSAProblemCard(front="Q1", back="A1")
        card2 = DSAConceptCard(name="Concept", front="Q2", back="A2")
        card3 = SystemDesignCard(name="Design", front="Q3", back="A3")

        card_storage.save(card1)
        card_storage.save(card2)
        card_storage.save(card3)

        all_cards = card_storage.list_all()
        assert len(all_cards) == 3

    def test_list_by_type(self, card_storage):
        """Test filtering by card type."""
        card1 = DSAProblemCard(front="Q1", back="A1")
        card2 = DSAConceptCard(name="Concept", front="Q2", back="A2")

        card_storage.save(card1)
        card_storage.save(card2)

        dsa_problems = card_storage.list_all(card_type=CardType.DSA_PROBLEM)
        assert len(dsa_problems) == 1
        assert dsa_problems[0].type == CardType.DSA_PROBLEM

    def test_list_by_tag(self, card_storage):
        """Test filtering by tag."""
        card1 = DSAProblemCard(front="Q1", back="A1", tags=["#important"])
        card2 = DSAProblemCard(front="Q2", back="A2", tags=["#optional"])

        card_storage.save(card1)
        card_storage.save(card2)

        important = card_storage.list_all(tags=["#important"])
        assert len(important) == 1

    def test_search(self, card_storage):
        """Test simple search."""
        card1 = DSAProblemCard(front="Binary search question", back="A1")
        card2 = DSAProblemCard(front="Linked list question", back="A2")

        card_storage.save(card1)
        card_storage.save(card2)

        results = card_storage.search("binary")
        assert len(results) == 1
        assert "binary" in results[0].front.lower()


class TestReviewDatabase:
    """Tests for ReviewDatabase."""

    def test_card_state_upsert_and_get(self, review_db):
        """Test upserting and getting card state."""
        review_db.upsert_card_state(
            card_id="test-123",
            stability=1.5,
            difficulty=5.0,
            due=None,
            last_review=None,
            reps=0,
            lapses=0,
            state="new",
        )

        state = review_db.get_card_state("test-123")
        assert state is not None
        assert state["stability"] == 1.5
        assert state["difficulty"] == 5.0
        assert state["state"] == "new"

    def test_review_log(self, review_db):
        """Test logging a review."""
        review_db.log_review(
            card_id="test-123",
            rating=3,
            elapsed_days=5.0,
            scheduled_days=4.0,
            stability_before=1.0,
            stability_after=2.0,
            difficulty_before=5.0,
            difficulty_after=4.8,
            state_before="review",
            state_after="review",
        )

        stats = review_db.get_stats()
        assert stats["total_reviews"] == 1

    def test_get_stats(self, review_db):
        """Test getting statistics."""
        stats = review_db.get_stats()
        assert "total_cards" in stats
        assert "total_reviews" in stats
        assert "due_today" in stats
        assert "new_cards" in stats


class TestAletheiaStorage:
    """Tests for combined AletheiaStorage."""

    def test_save_initializes_fsrs_state(self, storage):
        """Test that saving a card initializes FSRS state."""
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        state = storage.db.get_card_state(card.id)
        assert state is not None
        assert state["state"] == "new"

    def test_full_workflow(self, storage):
        """Test a full workflow: create, list, load, delete."""
        # Create
        card = DSAProblemCard(
            front="Test question",
            back="Test answer",
            tags=["#test"],
        )
        storage.save_card(card)

        # List
        cards = storage.list_cards()
        assert len(cards) == 1

        # Load
        loaded = storage.load_card(card.id)
        assert loaded is not None
        assert loaded.front == card.front

        # Delete
        assert storage.delete_card(card.id)
        assert storage.load_card(card.id) is None
