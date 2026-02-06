"""Tests for FTS5 search functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from aletheia.core.models import (
    DSAConceptCard,
    DSAProblemCard,
    SystemDesignCard,
)
from aletheia.core.storage import AletheiaStorage, ReviewDatabase
from aletheia.web.app import create_app
from fastapi.testclient import TestClient


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
def review_db(temp_dir):
    """Create a ReviewDatabase instance for tests."""
    return ReviewDatabase(temp_dir / ".aletheia" / "aletheia.db")


@pytest.fixture
def client(temp_dir):
    """Create a test client with mocked storage."""
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


def _make_problem(**kwargs) -> DSAProblemCard:
    """Helper to create a DSAProblemCard with defaults."""
    defaults = {"front": "Q", "back": "A"}
    defaults.update(kwargs)
    return DSAProblemCard(**defaults)


def _make_concept(**kwargs) -> DSAConceptCard:
    """Helper to create a DSAConceptCard with defaults."""
    defaults = {"name": "Concept", "front": "Q", "back": "A"}
    defaults.update(kwargs)
    return DSAConceptCard(**defaults)


def _make_sysdesign(**kwargs) -> SystemDesignCard:
    """Helper to create a SystemDesignCard with defaults."""
    defaults = {"name": "Design", "front": "Q", "back": "A"}
    defaults.update(kwargs)
    return SystemDesignCard(**defaults)


# ============================================================================
# FTS5 Indexing
# ============================================================================


class TestFTS5Indexing:
    """Tests for card indexing into the FTS5 search index."""

    def test_card_indexed_on_save(self, storage):
        """Saving a card indexes it in FTS5."""
        card = _make_problem(front="Binary search question", back="Use divide and conquer")
        storage.save_card(card)

        results = storage.db.search_cards("binary")
        assert card.id in results

    def test_front_field_searchable(self, storage):
        """Front field is searchable."""
        card = _make_problem(front="Explain monotonic stack")
        storage.save_card(card)

        results = storage.db.search_cards("monotonic")
        assert card.id in results

    def test_back_field_searchable(self, storage):
        """Back field is searchable."""
        card = _make_problem(front="Q", back="Use a hashmap for O(1) lookup")
        storage.save_card(card)

        results = storage.db.search_cards("hashmap")
        assert card.id in results

    def test_intuition_field_searchable(self, storage):
        """Intuition field is indexed and searchable."""
        card = _make_problem(
            front="Q",
            back="A",
            intuition="Each position water level is min of max left and max right",
        )
        storage.save_card(card)

        results = storage.db.search_cards("water level")
        assert card.id in results

    def test_patterns_field_searchable(self, storage):
        """Patterns list is indexed and searchable."""
        card = _make_problem(
            front="Q",
            back="A",
            patterns=["two-pointers", "sliding-window"],
        )
        storage.save_card(card)

        # FTS5 treats hyphens as token separators, so "pointers" should match
        results = storage.db.search_cards("pointers")
        assert card.id in results

    def test_data_structures_field_searchable(self, storage):
        """Data structures list is indexed and searchable."""
        card = _make_problem(
            front="Q",
            back="A",
            data_structures=["array", "hashmap"],
        )
        storage.save_card(card)

        results = storage.db.search_cards("hashmap")
        assert card.id in results

    def test_definition_field_searchable(self, storage):
        """Definition field is indexed and searchable."""
        card = _make_concept(
            name="Stack",
            front="Q",
            back="A",
            definition="LIFO data structure that supports push and pop",
        )
        storage.save_card(card)

        results = storage.db.search_cards("LIFO")
        assert card.id in results

    def test_extra_catch_all_searchable(self, storage):
        """Extra catch-all field (edge_cases, when_to_use, etc.) is searchable."""
        card = _make_concept(
            name="BFS",
            front="Q",
            back="A",
            when_to_use="Unweighted shortest path in a graph",
        )
        storage.save_card(card)

        results = storage.db.search_cards("unweighted")
        assert card.id in results

    def test_tags_searchable(self, storage):
        """Tags are searchable."""
        card = _make_problem(front="Q", back="A", tags=["#interview-classic"])
        storage.save_card(card)

        results = storage.db.search_cards("interview")
        assert card.id in results

    def test_name_searchable(self, storage):
        """Name field is searchable for concept/design cards."""
        card = _make_concept(name="Monotonic Stack")
        storage.save_card(card)

        results = storage.db.search_cards("Monotonic")
        assert card.id in results

    def test_system_design_fields_searchable(self, storage):
        """System design specific fields are indexed."""
        card = _make_sysdesign(
            name="Leader Election",
            definition="Distributed protocol for choosing a leader",
            how_it_works="Nodes vote and highest ID wins",
            use_cases=["Database failover", "Cluster coordination"],
            anti_patterns=["Single point of failure"],
        )
        storage.save_card(card)

        assert card.id in storage.db.search_cards("distributed")
        assert card.id in storage.db.search_cards("failover")
        assert card.id in storage.db.search_cards("single point")

    def test_reindex_rebuilds_index(self, storage):
        """reindex_all() rebuilds index from all cards on disk."""
        card1 = _make_problem(front="First card about arrays")
        card2 = _make_concept(name="Graphs", front="Second card about graphs")
        storage.save_card(card1)
        storage.save_card(card2)

        # Verify initial indexing works
        assert len(storage.db.search_cards("arrays")) == 1

        # Clear the index manually
        with storage.db._connection() as conn:
            conn.execute("DELETE FROM card_search")
        assert len(storage.db.search_cards("arrays")) == 0

        # Reindex
        count = storage.reindex_all()
        assert count == 2
        assert len(storage.db.search_cards("arrays")) == 1
        assert len(storage.db.search_cards("graphs")) == 1


# ============================================================================
# FTS5 Search
# ============================================================================


class TestFTS5Search:
    """Tests for FTS5 search behavior."""

    def test_exact_match(self, storage):
        """Exact word match returns the card."""
        card = _make_problem(front="What is a binary search tree?")
        storage.save_card(card)

        results = storage.search("binary")
        assert len(results) == 1
        assert results[0].id == card.id

    def test_prefix_match(self, storage):
        """Simple queries use prefix matching (mono -> monotonic)."""
        card = _make_problem(front="Explain monotonic stack")
        storage.save_card(card)

        results = storage.search("mono")
        assert len(results) == 1
        assert results[0].id == card.id

    def test_multi_word_search(self, storage):
        """Multi-word queries match cards containing all words."""
        card1 = _make_problem(front="Binary search on sorted array")
        card2 = _make_problem(front="Linear search on linked list")
        storage.save_card(card1)
        storage.save_card(card2)

        results = storage.search("binary search")
        assert len(results) == 1
        assert results[0].id == card1.id

    def test_no_results_returns_empty(self, storage):
        """Query with no matches returns empty list."""
        card = _make_problem(front="Binary search")
        storage.save_card(card)

        results = storage.search("quantum")
        assert results == []

    def test_empty_query_returns_empty(self, storage):
        """Empty query returns empty list."""
        card = _make_problem(front="Binary search")
        storage.save_card(card)

        results = storage.search("")
        assert results == []
        results = storage.search("   ")
        assert results == []


# ============================================================================
# FTS5 Query Handling
# ============================================================================


class TestFTS5QueryHandling:
    """Tests for query preprocessing and error handling."""

    def test_simple_terms_get_prefix_wildcard(self, review_db):
        """Simple terms without FTS5 operators get * appended."""
        # We test indirectly: "binar" should match "binary" via prefix
        card = _make_problem(front="Binary search algorithm")
        review_db.index_card(card)

        results = review_db.search_cards("binar")
        assert card.id in results

    def test_fts5_operators_preserved(self, review_db):
        """FTS5 operators (AND, OR, NOT, quotes) are not modified."""
        card1 = _make_problem(front="Binary search tree")
        card2 = _make_problem(front="Binary heap structure")
        review_db.index_card(card1)
        review_db.index_card(card2)

        # Explicit AND — both words must appear
        results = review_db.search_cards("binary AND tree")
        assert card1.id in results
        assert card2.id not in results

    def test_quoted_phrase_preserved(self, review_db):
        """Quoted phrases are passed through unchanged."""
        card = _make_problem(front="Binary search tree traversal")
        review_db.index_card(card)

        results = review_db.search_cards('"binary search"')
        assert card.id in results

    def test_malformed_query_returns_empty(self, review_db):
        """Malformed FTS5 query doesn't crash, returns empty list."""
        card = _make_problem(front="Test card")
        review_db.index_card(card)

        # Intentionally malformed FTS5 syntax
        results = review_db.search_cards("AND OR NOT")
        assert results == []

    def test_special_characters_dont_crash(self, review_db):
        """Queries with special characters don't crash."""
        card = _make_problem(front="O(n log n) complexity")
        review_db.index_card(card)

        # Parentheses could be problematic for FTS5
        results = review_db.search_cards("O(n)")
        assert isinstance(results, list)


# ============================================================================
# Search Integration (AletheiaStorage.search)
# ============================================================================


class TestSearchIntegration:
    """Tests for the high-level AletheiaStorage.search() method."""

    def test_search_uses_fts(self, storage):
        """AletheiaStorage.search() uses FTS5 index."""
        card = _make_problem(front="Topological sort algorithm")
        storage.save_card(card)

        results = storage.search("topological")
        assert len(results) == 1
        assert results[0].id == card.id

    def test_no_double_load(self, storage):
        """search() loads each card exactly once (no double-load bug)."""
        card = _make_problem(front="Unique card for double load test")
        storage.save_card(card)

        # Track load calls
        original_load = storage.cards.load
        load_count = {"calls": 0}

        def counting_load(*args, **kwargs):
            load_count["calls"] += 1
            return original_load(*args, **kwargs)

        storage.cards.load = counting_load

        results = storage.search("unique")
        assert len(results) == 1
        assert load_count["calls"] == 1  # Exactly one load per card

    def test_fallback_to_simple_search(self, storage):
        """Falls back to simple search when FTS returns nothing."""
        card = _make_problem(front="Fallback test card")
        storage.save_card(card)

        # Clear FTS index so FTS returns nothing
        with storage.db._connection() as conn:
            conn.execute("DELETE FROM card_search")

        # Should still find via fallback
        results = storage.search("fallback")
        assert len(results) == 1
        assert results[0].id == card.id


# ============================================================================
# Reindex
# ============================================================================


class TestReindex:
    """Tests for reindex_all()."""

    def test_reindex_all_indexes_all_cards(self, storage):
        """reindex_all() indexes every card from disk."""
        cards = [
            _make_problem(front="Card about arrays"),
            _make_concept(name="Stacks", front="Card about stacks"),
            _make_sysdesign(name="Caching", front="Card about caching"),
        ]
        for card in cards:
            storage.save_card(card)

        # Clear index
        with storage.db._connection() as conn:
            conn.execute("DELETE FROM card_search")

        count = storage.reindex_all()
        assert count == 3

        # All cards should be searchable again
        assert len(storage.db.search_cards("arrays")) == 1
        assert len(storage.db.search_cards("stacks")) == 1
        assert len(storage.db.search_cards("caching")) == 1

    def test_reindex_returns_correct_count(self, storage):
        """reindex_all() returns the number of cards indexed."""
        for i in range(5):
            storage.save_card(_make_problem(front=f"Card number {i}"))

        count = storage.reindex_all()
        assert count == 5

    def test_reindex_updates_stale_entries(self, storage):
        """reindex_all() updates entries that are out of date."""
        card = _make_problem(front="Original question")
        storage.save_card(card)

        assert len(storage.db.search_cards("original")) == 1

        # Modify card on disk without going through save_card
        card.front = "Modified question about algorithms"
        storage.cards.save(card)

        # FTS still has old content
        assert len(storage.db.search_cards("original")) == 1
        assert len(storage.db.search_cards("algorithms")) == 0

        # Reindex picks up changes
        storage.reindex_all()
        assert len(storage.db.search_cards("original")) == 0
        assert len(storage.db.search_cards("algorithms")) == 1


# ============================================================================
# Schema Migration
# ============================================================================


class TestSchemaMigration:
    """Tests for FTS5 schema migration."""

    def test_new_db_gets_full_schema(self, temp_dir):
        """A fresh database gets the full FTS5 schema with all columns."""
        db = ReviewDatabase(temp_dir / ".aletheia" / "aletheia.db")
        with db._connection() as conn:
            rows = conn.execute("PRAGMA table_xinfo(card_search)").fetchall()
            col_names = [r["name"] for r in rows]

        # Should have all expected columns
        for col in [
            "card_id",
            "front",
            "back",
            "name",
            "tags",
            "taxonomy",
            "intuition",
            "patterns",
            "data_structures",
            "definition",
            "extra",
        ]:
            assert col in col_names

    def test_migration_preserves_other_tables(self, temp_dir):
        """Migration doesn't affect non-FTS tables."""
        db = ReviewDatabase(temp_dir / ".aletheia" / "aletheia.db")

        # Insert some data into card_states
        db.upsert_card_state(
            card_id="test-123",
            stability=1.0,
            difficulty=5.0,
            due=None,
            last_review=None,
            reps=0,
            lapses=0,
            state="new",
        )

        # Re-create to trigger migration
        db2 = ReviewDatabase(temp_dir / ".aletheia" / "aletheia.db")
        state = db2.get_card_state("test-123")
        assert state is not None
        assert state["stability"] == 1.0


# ============================================================================
# Web Search
# ============================================================================


class TestWebSearch:
    """Tests for the web search endpoints."""

    def test_search_page_returns_200(self, client):
        """GET /search returns 200."""
        response = client.get("/search")
        assert response.status_code == 200
        assert "Search" in response.text

    def test_search_page_with_query(self, client, temp_dir):
        """GET /search?q=... returns matching cards."""
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

            card = _make_problem(front="Binary search on sorted array")
            storage.save_card(card)

        response = client.get("/search?q=binary")
        assert response.status_code == 200
        assert "binary" in response.text.lower()

    def test_search_results_partial(self, client, temp_dir):
        """GET /search/results?q=... returns HTMX partial with results."""
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

            card = _make_problem(
                front="Two sum problem",
                tags=["#interview-classic"],
            )
            storage.save_card(card)

        response = client.get("/search/results?q=two")
        assert response.status_code == 200
        assert "Two sum" in response.text

    def test_search_results_empty_query(self, client):
        """GET /search/results with empty query returns no results."""
        response = client.get("/search/results?q=")
        assert response.status_code == 200

    def test_search_results_no_match(self, client):
        """GET /search/results with non-matching query returns no results."""
        response = client.get("/search/results?q=xyznonexistent")
        assert response.status_code == 200
        assert "No cards found" in response.text or "0" not in response.text
