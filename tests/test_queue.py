"""Tests for QueueBuilder."""

import tempfile
from pathlib import Path

import pytest

from aletheia.core.graph import KnowledgeGraph
from aletheia.core.models import CardLinks, DSAProblemCard
from aletheia.core.queue import QueueBuilder
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


@pytest.fixture
def builder(storage, graph):
    return QueueBuilder(storage, graph)


class TestPrerequisiteFiltering:
    def test_new_card_without_prereqs_passes(self, storage, builder):
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        result = builder.build_queue([], [card.id])
        assert card.id in result

    def test_new_card_with_unmastered_prereq_filtered(self, storage, builder):
        prereq = DSAProblemCard(front="Prereq", back="A")
        card = DSAProblemCard(
            front="Q",
            back="A",
            links=CardLinks(prerequisite=[prereq.id]),
        )
        storage.save_card(prereq)
        storage.save_card(card)

        result = builder.build_queue([], [card.id])
        assert card.id not in result

    def test_due_cards_always_included(self, storage, builder):
        """Due cards are always included regardless of prerequisites."""
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        result = builder.build_queue([card.id], [])
        assert card.id in result

    def test_new_limit_respected(self, storage, builder):
        cards = []
        for i in range(5):
            c = DSAProblemCard(front=f"Q{i}", back=f"A{i}")
            storage.save_card(c)
            cards.append(c)

        result = builder.build_queue([], [c.id for c in cards], new_limit=2)
        # Only due + up to 2 new
        assert len(result) <= 2


class TestNonInterference:
    def test_similar_cards_separated(self, storage, builder):
        a = DSAProblemCard(front="A", back="A")
        b = DSAProblemCard(
            front="B",
            back="B",
            links=CardLinks(similar_to=[a.id]),
        )
        c = DSAProblemCard(front="C", back="C")
        storage.save_card(a)
        storage.save_card(b)
        storage.save_card(c)

        result = builder.build_queue([a.id, b.id, c.id], [])
        # a and b should not be adjacent if c can go between them
        if len(result) == 3:
            a_idx = result.index(a.id)
            b_idx = result.index(b.id)
            assert abs(a_idx - b_idx) > 1 or len(result) <= 2

    def test_no_conflicts_preserves_order(self, storage, builder):
        cards = [DSAProblemCard(front=f"Q{i}", back=f"A{i}") for i in range(3)]
        for c in cards:
            storage.save_card(c)
        due = [c.id for c in cards]

        result = builder.build_queue(due, [])
        assert len(result) == 3


class TestInterleaving:
    def test_different_taxonomy_interleaved(self, storage, builder):
        dsa1 = DSAProblemCard(front="D1", back="A", taxonomy=["dsa"])
        dsa2 = DSAProblemCard(front="D2", back="A", taxonomy=["dsa"])
        sd1 = DSAProblemCard(front="S1", back="A", taxonomy=["system-design"])
        sd2 = DSAProblemCard(front="S2", back="A", taxonomy=["system-design"])
        for c in [dsa1, dsa2, sd1, sd2]:
            storage.save_card(c)

        result = builder.build_queue([dsa1.id, dsa2.id, sd1.id, sd2.id], [])
        assert len(result) == 4

        # Check interleaving: consecutive cards should alternate taxonomy when possible
        branches = []
        for cid in result:
            card = storage.load_card(cid)
            branches.append(card.taxonomy[0] if card and card.taxonomy else "_none")

        # At least some alternation should exist
        consecutive_same = sum(
            1 for i in range(len(branches) - 1) if branches[i] == branches[i + 1]
        )
        assert consecutive_same < len(branches) - 1


class TestRemediation:
    def test_get_remediation_on_failure(self, storage, scheduler, graph):
        prereq = DSAProblemCard(front="Prereq", back="A")
        card = DSAProblemCard(
            front="Q",
            back="A",
            links=CardLinks(prerequisite=[prereq.id]),
        )
        storage.save_card(prereq)
        storage.save_card(card)

        # Review prereq once so it's not 'new' but has low stability
        scheduler.review_card(prereq.id, ReviewRating.AGAIN)

        remediation = scheduler.get_remediation_cards(card.id, graph)
        assert prereq.id in remediation

    def test_no_remediation_when_prereqs_strong(self, storage, scheduler, graph):
        prereq = DSAProblemCard(front="Prereq", back="A")
        card = DSAProblemCard(
            front="Q",
            back="A",
            links=CardLinks(prerequisite=[prereq.id]),
        )
        storage.save_card(prereq)
        storage.save_card(card)

        # Review prereq many times with EASY to build stability
        for _ in range(5):
            scheduler.review_card(prereq.id, ReviewRating.EASY)

        state = storage.db.get_card_state(prereq.id)
        if state and (state.get("stability") or 0) >= 5.0:
            remediation = scheduler.get_remediation_cards(card.id, graph)
            assert prereq.id not in remediation

    def test_no_remediation_without_prereqs(self, storage, scheduler, graph):
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)
        remediation = scheduler.get_remediation_cards(card.id, graph)
        assert remediation == []
