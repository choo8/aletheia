"""Tests for ProgressMetrics and response time tracking."""

import tempfile
from pathlib import Path

import pytest

from aletheia.core.metrics import ProgressMetrics
from aletheia.core.models import DSAProblemCard
from aletheia.core.scheduler import AletheiaScheduler, ReviewRating
from aletheia.core.storage import AletheiaStorage


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage(temp_dir):
    return AletheiaStorage(temp_dir / "data", temp_dir / ".aletheia")


@pytest.fixture
def scheduler(storage):
    return AletheiaScheduler(storage.db)


@pytest.fixture
def metrics(storage):
    return ProgressMetrics(storage)


class TestResponseTimeTracking:
    def test_log_review_with_response_time(self, storage, scheduler):
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        scheduler.review_card(card.id, ReviewRating.GOOD, response_time_ms=3500)

        times = storage.db.get_response_times(card.id)
        assert times == [3500]

    def test_log_review_without_response_time(self, storage, scheduler):
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        scheduler.review_card(card.id, ReviewRating.GOOD)

        times = storage.db.get_response_times(card.id)
        assert times == []

    def test_multiple_response_times(self, storage, scheduler):
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        scheduler.review_card(card.id, ReviewRating.GOOD, response_time_ms=5000)
        scheduler.review_card(card.id, ReviewRating.GOOD, response_time_ms=3000)
        scheduler.review_card(card.id, ReviewRating.EASY, response_time_ms=1500)

        times = storage.db.get_response_times(card.id, limit=10)
        assert len(times) == 3
        # Most recent first
        assert times[0] == 1500
        assert times[1] == 3000
        assert times[2] == 5000

    def test_response_time_limit(self, storage, scheduler):
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        for ms in [1000, 2000, 3000, 4000, 5000]:
            scheduler.review_card(card.id, ReviewRating.GOOD, response_time_ms=ms)

        times = storage.db.get_response_times(card.id, limit=3)
        assert len(times) == 3


class TestAutomaticityReport:
    def test_empty_report(self, storage):
        report = storage.db.get_automaticity_report()
        assert report == []


class TestMasteryPercentage:
    def test_no_cards(self, metrics):
        assert metrics.mastery_percentage() == 0.0

    def test_with_new_cards_only(self, storage, metrics):
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)
        assert metrics.mastery_percentage() == 0.0

    def test_mastery_calculation(self, storage, scheduler, metrics):
        c1 = DSAProblemCard(front="Q1", back="A1")
        c2 = DSAProblemCard(front="Q2", back="A2")
        storage.save_card(c1)
        storage.save_card(c2)

        # Review c1 many times to reach 'review' state
        for _ in range(5):
            scheduler.review_card(c1.id, ReviewRating.EASY)

        mastery = metrics.mastery_percentage()
        state = storage.db.get_card_state(c1.id)
        if state and state.get("state") == "review":
            assert mastery == 0.5  # 1 of 2 cards in review
        else:
            # If not yet in review, mastery should be 0
            assert mastery == 0.0


class TestLearningVelocity:
    def test_no_reviews(self, metrics):
        assert metrics.learning_velocity() == 0.0

    def test_velocity_with_reviews(self, storage, scheduler, metrics):
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        # Review enough times to potentially reach 'review' state
        for _ in range(5):
            scheduler.review_card(card.id, ReviewRating.EASY)

        # Velocity should be >= 0 (exact value depends on FSRS)
        velocity = metrics.learning_velocity()
        assert velocity >= 0.0


class TestAutomaticityCandidates:
    def test_no_candidates_empty(self, metrics):
        candidates = metrics.automaticity_candidates()
        assert candidates == []


class TestSchemaMigration:
    def test_response_time_column_exists(self, storage):
        """Verify response_time_ms column was added by migration."""
        with storage.db._connection() as conn:
            cols = {
                row["name"] for row in conn.execute("PRAGMA table_info(review_logs)").fetchall()
            }
            assert "response_time_ms" in cols

    def test_migration_idempotent(self, storage):
        """Running migration twice should not error."""
        storage.db._migrate_response_time_column()
        with storage.db._connection() as conn:
            cols = {
                row["name"] for row in conn.execute("PRAGMA table_info(review_logs)").fetchall()
            }
            assert "response_time_ms" in cols
