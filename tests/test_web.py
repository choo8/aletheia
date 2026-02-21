"""Tests for the web application."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from aletheia.core.models import DSAProblemCard
from aletheia.core.storage import AletheiaStorage
from aletheia.web.app import create_app


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
def client(temp_dir):
    """Create a test client with mocked storage."""
    # Patch the storage path environment variables
    with patch.dict(
        "os.environ",
        {
            "ALETHEIA_DATA_DIR": str(temp_dir / "data"),
            "ALETHEIA_STATE_DIR": str(temp_dir / ".aletheia"),
        },
    ):
        # Clear the lru_cache to pick up new paths
        from aletheia.web import dependencies

        dependencies.get_storage.cache_clear()
        dependencies.get_scheduler.cache_clear()
        dependencies.get_templates.cache_clear()

        app = create_app()
        yield TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client):
        """Test health endpoint returns ok."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestHomeRedirect:
    """Tests for home page redirect."""

    def test_home_redirects_to_review(self, client):
        """Test that home page redirects to review."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/review"


class TestReviewSession:
    """Tests for review session endpoints."""

    def test_review_session_empty(self, client):
        """Test review session with no cards."""
        response = client.get("/review")
        assert response.status_code == 200
        assert "No cards due for review" in response.text

    def test_review_session_with_cards(self, client, temp_dir):
        """Test review session with cards."""
        # Create a card using the storage
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

            card = DSAProblemCard(front="Test question?", back="Test answer")
            storage.save_card(card)

        response = client.get("/review")
        assert response.status_code == 200
        assert "Test question?" in response.text
        assert "Reveal Answer" in response.text

    def test_reveal_answer(self, client, temp_dir):
        """Test revealing card answer."""
        # Create a card
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

            card = DSAProblemCard(front="Question", back="The answer is 42")
            storage.save_card(card)

        # Reveal the answer
        response = client.post(f"/review/reveal/{card.id}")
        assert response.status_code == 200
        assert "The answer is 42" in response.text
        assert "Again" in response.text  # Rating buttons should appear
        assert "Good" in response.text

    def test_rate_card(self, client, temp_dir):
        """Test rating a card."""
        # Create a card
        with patch.dict(
            "os.environ",
            {
                "ALETHEIA_DATA_DIR": str(temp_dir / "data"),
                "ALETHEIA_STATE_DIR": str(temp_dir / ".aletheia"),
            },
        ):
            from aletheia.web.dependencies import get_scheduler, get_storage

            get_storage.cache_clear()
            get_scheduler.cache_clear()
            storage = get_storage()

            card = DSAProblemCard(front="Q1", back="A1")
            storage.save_card(card)

        # Rate the card
        response = client.post(f"/review/rate/{card.id}", data={"rating": 3})
        assert response.status_code == 200

        # Should show completion message (since only one card)
        assert "Session complete" in response.text or "No cards" in response.text

    def test_rate_card_shows_next(self, client, temp_dir):
        """Test that rating shows next card when more cards exist."""
        # Create multiple cards
        with patch.dict(
            "os.environ",
            {
                "ALETHEIA_DATA_DIR": str(temp_dir / "data"),
                "ALETHEIA_STATE_DIR": str(temp_dir / ".aletheia"),
            },
        ):
            from aletheia.web.dependencies import get_scheduler, get_storage

            get_storage.cache_clear()
            get_scheduler.cache_clear()
            storage = get_storage()

            card1 = DSAProblemCard(front="First question", back="A1")
            card2 = DSAProblemCard(front="Second question", back="A2")
            storage.save_card(card1)
            storage.save_card(card2)

        # Rate the first card
        response = client.post(f"/review/rate/{card1.id}", data={"rating": 3})
        assert response.status_code == 200

        # Should show the next card (either card2 or completion if card1 became due again)
        assert "question" in response.text.lower()


class TestKaTexRendering:
    """Tests for KaTeX rendering in templates."""

    def test_latex_in_card_content(self, client, temp_dir):
        """Test that LaTeX in card content is processed."""
        # Create a card with LaTeX
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

            card = DSAProblemCard(
                front="What is $x^2 + y^2 = r^2$?",
                back="The equation of a circle",
            )
            storage.save_card(card)

        response = client.get("/review")
        assert response.status_code == 200
        # The LaTeX should be present (either rendered or as placeholder)
        assert "x^2" in response.text or "katex" in response.text.lower()
