"""Tests for the KnowledgeGraph service."""

import tempfile
from pathlib import Path

import pytest

from aletheia.core.graph import KnowledgeGraph
from aletheia.core.models import (
    CardLinks,
    DSAConceptCard,
    DSAProblemCard,
    WeightedLink,
)
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
def graph(storage):
    return KnowledgeGraph(storage)


@pytest.fixture
def scheduler(storage):
    return AletheiaScheduler(storage.db)


def _make_card(front="Q", back="A", links=None, **kwargs):
    return DSAProblemCard(front=front, back=back, links=links or CardLinks(), **kwargs)


def _make_concept(name="Concept", front="Q", back="A", links=None, **kwargs):
    return DSAConceptCard(name=name, front=front, back=back, links=links or CardLinks(), **kwargs)


class TestGetPrerequisites:
    def test_no_prerequisites(self, storage, graph):
        card = _make_card()
        storage.save_card(card)
        assert graph.get_prerequisites(card.id) == []

    def test_direct_prerequisites(self, storage, graph):
        prereq = _make_card(front="Prereq")
        card = _make_card(links=CardLinks(prerequisite=[prereq.id]))
        storage.save_card(prereq)
        storage.save_card(card)

        result = graph.get_prerequisites(card.id)
        assert len(result) == 1
        assert result[0].id == prereq.id

    def test_missing_prerequisite_skipped(self, storage, graph):
        card = _make_card(links=CardLinks(prerequisite=["nonexistent-id"]))
        storage.save_card(card)
        assert graph.get_prerequisites(card.id) == []

    def test_nonexistent_card(self, graph):
        assert graph.get_prerequisites("nonexistent") == []


class TestGetTransitivePrerequisites:
    def test_chain(self, storage, graph):
        a = _make_card(front="A")
        b = _make_card(front="B", links=CardLinks(prerequisite=[a.id]))
        c = _make_card(front="C", links=CardLinks(prerequisite=[b.id]))
        storage.save_card(a)
        storage.save_card(b)
        storage.save_card(c)

        result = graph.get_transitive_prerequisites(c.id)
        result_ids = {r.id for r in result}
        assert result_ids == {a.id, b.id}

    def test_cycle_detection(self, storage, graph):
        """Cycles should not cause infinite loops."""
        a = _make_card(front="A")
        b = _make_card(front="B", links=CardLinks(prerequisite=[a.id]))
        # Create a cycle: A -> B -> A
        a.links.prerequisite = [b.id]
        storage.save_card(a)
        storage.save_card(b)

        # Should terminate without error
        result = graph.get_transitive_prerequisites(a.id)
        assert len(result) <= 2

    def test_diamond_dependency(self, storage, graph):
        """Diamond: D depends on B and C, both depend on A."""
        a = _make_card(front="A")
        b = _make_card(front="B", links=CardLinks(prerequisite=[a.id]))
        c = _make_card(front="C", links=CardLinks(prerequisite=[a.id]))
        d = _make_card(front="D", links=CardLinks(prerequisite=[b.id, c.id]))
        storage.save_card(a)
        storage.save_card(b)
        storage.save_card(c)
        storage.save_card(d)

        result = graph.get_transitive_prerequisites(d.id)
        result_ids = {r.id for r in result}
        assert result_ids == {a.id, b.id, c.id}


class TestGetEncompassed:
    def test_no_encompasses(self, storage, graph):
        card = _make_card()
        storage.save_card(card)
        assert graph.get_encompassed(card.id) == []

    def test_with_encompasses(self, storage, graph):
        child = _make_card(front="Child")
        parent = _make_card(
            front="Parent",
            links=CardLinks(encompasses=[WeightedLink(card_id=child.id, weight=0.7)]),
        )
        storage.save_card(child)
        storage.save_card(parent)

        result = graph.get_encompassed(parent.id)
        assert len(result) == 1
        assert result[0][0].id == child.id
        assert result[0][1] == 0.7


class TestGetEncompassing:
    def test_reverse_lookup(self, storage, graph):
        child = _make_card(front="Child")
        parent = _make_card(
            front="Parent",
            links=CardLinks(encompasses=[WeightedLink(card_id=child.id, weight=0.5)]),
        )
        storage.save_card(child)
        storage.save_card(parent)

        result = graph.get_encompassing(child.id)
        assert len(result) == 1
        assert result[0][0].id == parent.id
        assert result[0][1] == 0.5


class TestGetDependents:
    def test_reverse_prerequisite_lookup(self, storage, graph):
        prereq = _make_card(front="Prereq")
        dependent = _make_card(links=CardLinks(prerequisite=[prereq.id]))
        storage.save_card(prereq)
        storage.save_card(dependent)

        result = graph.get_dependents(prereq.id)
        assert len(result) == 1
        assert result[0].id == dependent.id


class TestKnowledgeFrontier:
    def test_new_card_no_prereqs_on_frontier(self, storage, graph):
        card = _make_card()
        storage.save_card(card)
        frontier = graph.get_knowledge_frontier()
        assert any(c.id == card.id for c in frontier)

    def test_reviewed_card_not_on_frontier(self, storage, graph, scheduler):
        card = _make_card()
        storage.save_card(card)
        scheduler.review_card(card.id, ReviewRating.GOOD)

        frontier = graph.get_knowledge_frontier()
        assert not any(c.id == card.id for c in frontier)

    def test_prereq_not_mastered_blocks_frontier(self, storage, graph):
        prereq = _make_card(front="Prereq")
        card = _make_card(links=CardLinks(prerequisite=[prereq.id]))
        storage.save_card(prereq)
        storage.save_card(card)

        # prereq is still 'new', not mastered
        frontier = graph.get_knowledge_frontier()
        frontier_ids = {c.id for c in frontier}
        assert card.id not in frontier_ids

    def test_mastered_prereq_enables_frontier(self, storage, graph, scheduler):
        prereq = _make_card(front="Prereq")
        card = _make_card(links=CardLinks(prerequisite=[prereq.id]))
        storage.save_card(prereq)
        storage.save_card(card)

        # Review prereq multiple times to reach 'review' state with high stability
        for _ in range(5):
            scheduler.review_card(prereq.id, ReviewRating.EASY)

        state = storage.db.get_card_state(prereq.id)
        if state and state.get("state") == "review" and (state.get("stability") or 0) >= 5.0:
            frontier = graph.get_knowledge_frontier()
            frontier_ids = {c.id for c in frontier}
            assert card.id in frontier_ids


class TestPrerequisitesMastered:
    def test_no_prereqs_is_mastered(self, storage, graph):
        card = _make_card()
        storage.save_card(card)
        assert graph.prerequisites_mastered(card.id) is True

    def test_nonexistent_card(self, graph):
        assert graph.prerequisites_mastered("nonexistent") is False

    def test_unreviewed_prereq_not_mastered(self, storage, graph):
        prereq = _make_card(front="Prereq")
        card = _make_card(links=CardLinks(prerequisite=[prereq.id]))
        storage.save_card(prereq)
        storage.save_card(card)
        assert graph.prerequisites_mastered(card.id) is False


class TestGraphStats:
    def test_empty_graph(self, graph):
        stats = graph.get_graph_stats()
        assert stats["total_nodes"] == 0
        assert stats["total_edges"] == 0
        assert stats["orphans"] == 0
        assert stats["max_depth"] == 0

    def test_single_orphan(self, storage, graph):
        card = _make_card()
        storage.save_card(card)
        stats = graph.get_graph_stats()
        assert stats["total_nodes"] == 1
        assert stats["orphans"] == 1

    def test_linked_cards_not_orphans(self, storage, graph):
        a = _make_card(front="A")
        b = _make_card(front="B", links=CardLinks(prerequisite=[a.id]))
        storage.save_card(a)
        storage.save_card(b)

        stats = graph.get_graph_stats()
        assert stats["total_nodes"] == 2
        assert stats["total_edges"] == 1
        assert stats["orphans"] == 0

    def test_prereq_depth(self, storage, graph):
        a = _make_card(front="A")
        b = _make_card(front="B", links=CardLinks(prerequisite=[a.id]))
        c = _make_card(front="C", links=CardLinks(prerequisite=[b.id]))
        storage.save_card(a)
        storage.save_card(b)
        storage.save_card(c)

        stats = graph.get_graph_stats()
        assert stats["max_depth"] == 2
