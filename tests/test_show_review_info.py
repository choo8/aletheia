"""Tests for the show command's review scheduling display."""

import tempfile
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest
from aletheia.cli.main import _display_card, _format_review_info
from aletheia.core.models import DSAProblemCard
from aletheia.core.scheduler import AletheiaScheduler, ReviewRating
from aletheia.core.storage import AletheiaStorage
from rich.console import Console


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage(temp_dir):
    """Create an AletheiaStorage instance for tests."""
    return AletheiaStorage(temp_dir / "data", temp_dir / ".aletheia")


class TestFormatReviewInfo:
    """Tests for _format_review_info helper."""

    def test_none_state_shows_new_card(self):
        result = _format_review_info(None)
        assert "new card" in result
        assert "not yet reviewed" in result

    def test_overdue_card(self):
        past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        state = {"due": past, "state": "learning", "reps": 3, "lapses": 1}
        result = _format_review_info(state)
        assert "overdue" in result
        assert "Reviews: 3" in result
        assert "Lapses: 1" in result

    def test_due_in_days(self):
        future = (datetime.now(UTC) + timedelta(days=5, hours=12)).isoformat()
        state = {"due": future, "state": "review", "reps": 10, "lapses": 0}
        result = _format_review_info(state)
        assert "in 5 days" in result
        assert "review" in result

    def test_due_tomorrow(self):
        tomorrow = (datetime.now(UTC) + timedelta(days=1, hours=12)).isoformat()
        state = {"due": tomorrow, "state": "learning", "reps": 1, "lapses": 0}
        result = _format_review_info(state)
        assert "tomorrow" in result

    def test_due_in_hours(self):
        future = (datetime.now(UTC) + timedelta(hours=3, minutes=30)).isoformat()
        state = {"due": future, "state": "learning", "reps": 1, "lapses": 0}
        result = _format_review_info(state)
        assert "in 3h" in result

    def test_due_in_minutes(self):
        future = (datetime.now(UTC) + timedelta(minutes=15, seconds=30)).isoformat()
        state = {"due": future, "state": "learning", "reps": 1, "lapses": 0}
        result = _format_review_info(state)
        assert "in 15m" in result

    def test_state_and_counts_displayed(self):
        future = (datetime.now(UTC) + timedelta(days=3)).isoformat()
        state = {"due": future, "state": "review", "reps": 7, "lapses": 2}
        result = _format_review_info(state)
        assert "State: review" in result
        assert "Reviews: 7" in result
        assert "Lapses: 2" in result


class TestDisplayCardWithReviewState:
    """Tests for _display_card with review_state parameter."""

    def _capture_display(self, card, full=False, review_state=None) -> str:
        """Capture Rich console output from _display_card."""
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        # Temporarily replace the module-level console
        import aletheia.cli.main as cli_mod

        orig = cli_mod.console
        cli_mod.console = console
        try:
            _display_card(card, full=full, review_state=review_state)
        finally:
            cli_mod.console = orig
        return buf.getvalue()

    def test_no_review_info_without_full(self):
        card = DSAProblemCard(front="Q?", back="A.")
        output = self._capture_display(
            card,
            full=False,
            review_state={
                "due": "2099-01-01T00:00:00+00:00",
                "state": "review",
                "reps": 5,
                "lapses": 0,
            },
        )
        assert "Next review" not in output

    def test_review_info_shown_in_full_mode(self):
        card = DSAProblemCard(front="Q?", back="A.")
        future = (datetime.now(UTC) + timedelta(days=3)).isoformat()
        state = {"due": future, "state": "review", "reps": 5, "lapses": 1}
        output = self._capture_display(card, full=True, review_state=state)
        assert "Next review" in output
        assert "Reviews: 5" in output

    def test_new_card_message_when_no_state(self):
        card = DSAProblemCard(front="Q?", back="A.")
        output = self._capture_display(card, full=True, review_state=None)
        assert "new card" in output


class TestShowCommandIntegration:
    """Integration test: show command fetches review state from DB."""

    def test_show_after_review(self, storage):
        """After reviewing a card, get_card_state returns a due date."""
        card = DSAProblemCard(front="What is BFS?", back="Breadth-first search")
        storage.save_card(card)

        scheduler = AletheiaScheduler(storage.db)
        scheduler.review_card(card.id, ReviewRating.GOOD)

        state = storage.db.get_card_state(card.id)
        assert state is not None
        assert state["due"] is not None
        assert state["reps"] == 1

        result = _format_review_info(state)
        assert "Next review" in result
        assert "Reviews: 1" in result

    def test_show_unreviewed_card(self, storage):
        """An unreviewed card has state but no due date from scheduler."""
        card = DSAProblemCard(front="What is DFS?", back="Depth-first search")
        storage.save_card(card)

        # Card state is auto-created by save_card with state=new
        state = storage.db.get_card_state(card.id)
        # For a new card that has never been reviewed, state exists but due may be null
        result = _format_review_info(state)
        assert "Reviews:" in result or "new card" in result
