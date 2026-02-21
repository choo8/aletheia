"""Tests for statistics features (Phase 4c)."""

import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from aletheia.core.models import DSAConceptCard, DSAProblemCard, SystemDesignCard
from aletheia.core.storage import AletheiaStorage, ReviewDatabase
from aletheia.web.app import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db(temp_dir):
    return ReviewDatabase(temp_dir / "aletheia.db")


@pytest.fixture
def storage(temp_dir):
    return AletheiaStorage(temp_dir / "data", temp_dir / ".aletheia")


@pytest.fixture
def client(temp_dir):
    with patch.dict(
        "os.environ",
        {
            "ALETHEIA_DATA_DIR": str(temp_dir / "data"),
            "ALETHEIA_STATE_DIR": str(temp_dir / ".aletheia"),
        },
    ):
        from aletheia.web import dependencies

        dependencies.get_storage.cache_clear()
        dependencies.get_scheduler.cache_clear()
        dependencies.get_templates.cache_clear()

        app = create_app()
        yield TestClient(app)


def _insert_review(db: ReviewDatabase, card_id: str, reviewed_at: str, rating: int = 3):
    """Helper to insert a review log at a specific timestamp."""
    with db._connection() as conn:
        conn.execute(
            """
            INSERT INTO review_logs (card_id, reviewed_at, rating,
                stability_before, stability_after,
                difficulty_before, difficulty_after,
                state_before, state_after)
            VALUES (?, ?, ?, 0, 0, 0, 0, 'new', 'learning')
            """,
            (card_id, reviewed_at, rating),
        )


# ---------------------------------------------------------------------------
# ReviewDatabase.get_review_heatmap
# ---------------------------------------------------------------------------


class TestReviewHeatmap:
    def test_empty(self, db):
        assert db.get_review_heatmap() == {}

    def test_counts_per_day(self, db):
        today = date.today().isoformat()
        _insert_review(db, "c1", f"{today} 10:00:00")
        _insert_review(db, "c2", f"{today} 11:00:00")
        _insert_review(db, "c1", f"{today} 12:00:00")

        heatmap = db.get_review_heatmap()
        assert heatmap[today] == 3

    def test_multiple_days(self, db):
        today = date.today()
        yesterday = (today - timedelta(days=1)).isoformat()
        today_str = today.isoformat()

        _insert_review(db, "c1", f"{today_str} 10:00:00")
        _insert_review(db, "c1", f"{yesterday} 10:00:00")
        _insert_review(db, "c2", f"{yesterday} 11:00:00")

        heatmap = db.get_review_heatmap()
        assert heatmap[today_str] == 1
        assert heatmap[yesterday] == 2


# ---------------------------------------------------------------------------
# ReviewDatabase.get_streak_info
# ---------------------------------------------------------------------------


class TestStreakInfo:
    def test_zero_streaks(self, db):
        info = db.get_streak_info()
        assert info == {"current_streak": 0, "longest_streak": 0}

    def test_single_day_today(self, db):
        today = date.today().isoformat()
        _insert_review(db, "c1", f"{today} 09:00:00")

        info = db.get_streak_info()
        assert info["current_streak"] == 1
        assert info["longest_streak"] == 1

    def test_single_day_yesterday(self, db):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _insert_review(db, "c1", f"{yesterday} 09:00:00")

        info = db.get_streak_info()
        assert info["current_streak"] == 1
        assert info["longest_streak"] == 1

    def test_multi_day_streak(self, db):
        today = date.today()
        for i in range(5):
            d = (today - timedelta(days=i)).isoformat()
            _insert_review(db, "c1", f"{d} 10:00:00")

        info = db.get_streak_info()
        assert info["current_streak"] == 5
        assert info["longest_streak"] == 5

    def test_broken_streak(self, db):
        today = date.today()
        # Current: today + yesterday = 2
        _insert_review(db, "c1", f"{today.isoformat()} 10:00:00")
        _insert_review(db, "c1", f"{(today - timedelta(days=1)).isoformat()} 10:00:00")
        # Gap on day -2
        # Old streak: days -3, -4, -5 = 3
        for i in [3, 4, 5]:
            d = (today - timedelta(days=i)).isoformat()
            _insert_review(db, "c1", f"{d} 10:00:00")

        info = db.get_streak_info()
        assert info["current_streak"] == 2
        assert info["longest_streak"] == 3


# ---------------------------------------------------------------------------
# ReviewDatabase.get_success_rate
# ---------------------------------------------------------------------------


class TestSuccessRate:
    def test_no_reviews(self, db):
        assert db.get_success_rate() == 0.0

    def test_all_good(self, db):
        today = date.today().isoformat()
        for i in range(5):
            _insert_review(db, f"c{i}", f"{today} 10:00:00", rating=3)

        assert db.get_success_rate() == 1.0

    def test_mixed_ratings(self, db):
        today = date.today().isoformat()
        # 2 good (rating >= 3), 2 bad (rating < 3)
        _insert_review(db, "c1", f"{today} 10:00:00", rating=4)
        _insert_review(db, "c2", f"{today} 10:00:00", rating=3)
        _insert_review(db, "c3", f"{today} 10:00:00", rating=2)
        _insert_review(db, "c4", f"{today} 10:00:00", rating=1)

        assert db.get_success_rate() == 0.5


# ---------------------------------------------------------------------------
# AletheiaStorage.get_full_stats
# ---------------------------------------------------------------------------


class TestFullStats:
    def test_includes_by_type_and_domain(self, storage):
        card1 = DSAProblemCard(front="Q1", back="A1", taxonomy=["dsa", "problems"])
        card2 = DSAConceptCard(name="BFS", front="Q2", back="A2", taxonomy=["dsa", "concepts"])
        card3 = SystemDesignCard(name="CAP", front="Q3", back="A3", taxonomy=["system-design"])
        storage.save_card(card1)
        storage.save_card(card2)
        storage.save_card(card3)

        stats = storage.get_full_stats()

        assert stats["total_cards"] == 3
        assert stats["by_type"]["dsa-problem"] == 1
        assert stats["by_type"]["dsa-concept"] == 1
        assert stats["by_type"]["system-design"] == 1
        assert stats["by_domain"]["dsa"] == 2
        assert stats["by_domain"]["system-design"] == 1
        assert "success_rate" in stats
        assert "current_streak" in stats
        assert "longest_streak" in stats
        assert "heatmap" in stats


# ---------------------------------------------------------------------------
# Web stats page
# ---------------------------------------------------------------------------


class TestWebStatsPage:
    def test_stats_page_ok(self, client):
        response = client.get("/stats")
        assert response.status_code == 200
        assert "Statistics" in response.text

    def test_stats_page_shows_summary(self, client, temp_dir):
        with patch.dict(
            "os.environ",
            {
                "ALETHEIA_DATA_DIR": str(temp_dir / "data"),
                "ALETHEIA_STATE_DIR": str(temp_dir / ".aletheia"),
            },
        ):
            from aletheia.web.dependencies import get_storage

            get_storage.cache_clear()
            storage = get_storage()

            card = DSAProblemCard(front="Q", back="A")
            storage.save_card(card)

        response = client.get("/stats")
        assert response.status_code == 200
        assert "Total Cards" in response.text
        assert "Success Rate" in response.text

    def test_stats_page_has_heatmap(self, client):
        response = client.get("/stats")
        assert response.status_code == 200
        assert "Review Activity" in response.text

    def test_nav_has_stats_link(self, client):
        response = client.get("/stats")
        assert response.status_code == 200
        assert 'href="/stats"' in response.text
