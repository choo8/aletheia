"""Tests for CLI links subcommands and LLM link suggestion."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from aletheia.core.graph import KnowledgeGraph
from aletheia.core.models import CardLinks, DSAProblemCard, WeightedLink
from aletheia.core.storage import AletheiaStorage
from aletheia.llm.service import LinkSuggestion


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage(temp_dir):
    return AletheiaStorage(temp_dir / "data", temp_dir / ".aletheia")


@pytest.fixture
def graph(storage):
    return KnowledgeGraph(storage)


class TestLinkSuggestionModel:
    def test_create_suggestion(self):
        s = LinkSuggestion(
            source_id="a",
            target_id="b",
            link_type="prerequisite",
            rationale="A requires B",
        )
        assert s.source_id == "a"
        assert s.link_type == "prerequisite"
        assert s.weight is None

    def test_encompasses_with_weight(self):
        s = LinkSuggestion(
            source_id="a",
            target_id="b",
            link_type="encompasses",
            weight=0.7,
            rationale="A covers most of B",
        )
        assert s.weight == 0.7


class TestManualLinkManagement:
    def test_add_prerequisite(self, storage):
        a = DSAProblemCard(front="A", back="A")
        b = DSAProblemCard(front="B", back="B")
        storage.save_card(a)
        storage.save_card(b)

        # Simulate what links_add does
        a_loaded = storage.load_card(a.id)
        a_loaded.links.prerequisite.append(b.id)
        storage.save_card(a_loaded)

        reloaded = storage.load_card(a.id)
        assert b.id in reloaded.links.prerequisite

    def test_add_encompasses(self, storage):
        a = DSAProblemCard(front="A", back="A")
        b = DSAProblemCard(front="B", back="B")
        storage.save_card(a)
        storage.save_card(b)

        a_loaded = storage.load_card(a.id)
        a_loaded.links.encompasses.append(WeightedLink(card_id=b.id, weight=0.6))
        storage.save_card(a_loaded)

        reloaded = storage.load_card(a.id)
        assert len(reloaded.links.encompasses) == 1
        assert reloaded.links.encompasses[0].card_id == b.id
        assert reloaded.links.encompasses[0].weight == 0.6

    def test_remove_prerequisite(self, storage):
        b = DSAProblemCard(front="B", back="B")
        a = DSAProblemCard(front="A", back="A", links=CardLinks(prerequisite=[b.id]))
        storage.save_card(a)
        storage.save_card(b)

        a_loaded = storage.load_card(a.id)
        a_loaded.links.prerequisite.remove(b.id)
        storage.save_card(a_loaded)

        reloaded = storage.load_card(a.id)
        assert b.id not in reloaded.links.prerequisite

    def test_remove_encompasses(self, storage):
        b = DSAProblemCard(front="B", back="B")
        a = DSAProblemCard(
            front="A",
            back="A",
            links=CardLinks(encompasses=[WeightedLink(card_id=b.id, weight=0.5)]),
        )
        storage.save_card(a)
        storage.save_card(b)

        a_loaded = storage.load_card(a.id)
        a_loaded.links.encompasses = [wl for wl in a_loaded.links.encompasses if wl.card_id != b.id]
        storage.save_card(a_loaded)

        reloaded = storage.load_card(a.id)
        assert len(reloaded.links.encompasses) == 0


class TestGraphHealthCheck:
    def test_broken_links_detected(self, storage, graph):
        card = DSAProblemCard(
            front="Q",
            back="A",
            links=CardLinks(prerequisite=["nonexistent-id"]),
        )
        storage.save_card(card)

        all_cards = storage.list_cards()
        card_ids = {c.id for c in all_cards}
        broken = []
        for c in all_cards:
            for lid in c.links.prerequisite:
                if lid not in card_ids:
                    broken.append((c.id, lid))

        assert len(broken) == 1
        assert broken[0][1] == "nonexistent-id"

    def test_no_broken_links(self, storage, graph):
        a = DSAProblemCard(front="A", back="A")
        b = DSAProblemCard(front="B", back="B", links=CardLinks(prerequisite=[a.id]))
        storage.save_card(a)
        storage.save_card(b)

        all_cards = storage.list_cards()
        card_ids = {c.id for c in all_cards}
        broken = []
        for c in all_cards:
            for lid in c.links.prerequisite:
                if lid not in card_ids:
                    broken.append((c.id, lid))

        assert len(broken) == 0

    def test_self_reference_detected(self, storage):
        card = DSAProblemCard(front="Q", back="A")
        card.links.prerequisite.append(card.id)
        storage.save_card(card)

        reloaded = storage.load_card(card.id)
        assert reloaded.id in reloaded.links.prerequisite


class TestLinksHealthPartialIds:
    """Tests for partial ID detection and --fix in links health."""

    def test_health_distinguishes_partial_from_broken(self, storage):
        """Partial IDs are resolvable; truly broken are not."""
        target = DSAProblemCard(front="Target", back="T")
        storage.save_card(target)

        # Card with one partial ID and one truly broken ID
        card = DSAProblemCard(
            front="Q",
            back="A",
            links=CardLinks(
                prerequisite=[target.id[:8], "nonexistent-id"],
            ),
        )
        # Save with normalization disabled by writing JSON directly
        # so the partial ID persists
        storage.cards.save(card)
        storage.db.index_card(card)

        all_cards = storage.list_cards()
        card_ids = {c.id for c in all_cards}

        truly_broken = []
        partial_ids = []
        for c in all_cards:
            for lid in c.links.prerequisite:
                if lid not in card_ids:
                    resolved = storage.resolve_card_id(lid)
                    if resolved is not None:
                        partial_ids.append((c.id, lid, resolved))
                    else:
                        truly_broken.append((c.id, lid))

        assert len(partial_ids) == 1
        assert partial_ids[0][2] == target.id
        assert len(truly_broken) == 1
        assert truly_broken[0][1] == "nonexistent-id"

    def test_fix_resolves_partial_ids(self, storage):
        """Re-saving a card normalizes partial IDs to full UUIDs."""
        target = DSAProblemCard(front="Target", back="T")
        storage.save_card(target)

        card = DSAProblemCard(
            front="Q",
            back="A",
            links=CardLinks(prerequisite=[target.id[:8]]),
        )
        # Bypass normalization by writing directly
        storage.cards.save(card)
        storage.db.index_card(card)

        # Verify the partial ID persists
        before = storage.load_card(card.id)
        assert before.links.prerequisite == [target.id[:8]]

        # "Fix" by re-saving through AletheiaStorage
        storage.save_card(before)

        after = storage.load_card(card.id)
        assert after.links.prerequisite == [target.id]


class TestLLMSuggestLinksIntegration:
    def test_suggest_links_parses_response(self):
        """Test that suggest_links correctly parses LLM JSON response."""
        mock_response = """[
            {
                "target_id": "abc-123",
                "candidate_id": "abc-123",
                "link_type": "prerequisite",
                "weight": null,
                "rationale": "Card A requires B"
            }
        ]"""

        with patch("aletheia.llm.service.LLMService._get_completion", return_value=mock_response):
            from aletheia.llm.service import LLMService

            llm = LLMService()
            suggestions = llm.suggest_links(
                "Q",
                "A",
                "source-id",
                [{"id": "abc-123", "front": "Q2", "back": "A2", "type": "dsa-problem"}],
            )

        assert len(suggestions) == 1
        assert suggestions[0].link_type == "prerequisite"
        assert suggestions[0].source_id == "source-id"

    def test_suggest_links_empty_response(self):
        """Test handling of no suggestions."""
        with patch("aletheia.llm.service.LLMService._get_completion", return_value="[]"):
            from aletheia.llm.service import LLMService

            llm = LLMService()
            suggestions = llm.suggest_links("Q", "A", "source-id", [])

        assert suggestions == []
