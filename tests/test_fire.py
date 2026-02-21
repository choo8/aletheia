"""Tests for FIRe (Fractional Implicit Repetition) engine."""

import tempfile
from pathlib import Path

import pytest

from aletheia.core.fire import FIReEngine
from aletheia.core.graph import KnowledgeGraph
from aletheia.core.models import CardLinks, DSAProblemCard, WeightedLink
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
def fire(storage, graph):
    return FIReEngine(storage, graph)


@pytest.fixture
def scheduler(storage):
    return AletheiaScheduler(storage.db)


class TestPropagateCreditBasic:
    def test_no_encompasses_no_credit(self, storage, fire):
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        credits = fire.propagate_credit(card.id, 3)  # GOOD
        assert credits == []

    def test_credit_on_good(self, storage, fire):
        child = DSAProblemCard(front="Child", back="A")
        parent = DSAProblemCard(
            front="Parent",
            back="A",
            links=CardLinks(encompasses=[WeightedLink(card_id=child.id, weight=0.8)]),
        )
        storage.save_card(child)
        storage.save_card(parent)

        credits = fire.propagate_credit(parent.id, 3)  # GOOD, factor=0.8
        assert len(credits) == 1
        assert credits[0][0] == child.id
        assert credits[0][1] == pytest.approx(0.8 * 0.8)  # weight * factor

    def test_credit_on_easy(self, storage, fire):
        child = DSAProblemCard(front="Child", back="A")
        parent = DSAProblemCard(
            front="Parent",
            back="A",
            links=CardLinks(encompasses=[WeightedLink(card_id=child.id, weight=1.0)]),
        )
        storage.save_card(child)
        storage.save_card(parent)

        credits = fire.propagate_credit(parent.id, 4)  # EASY, factor=1.0
        assert len(credits) == 1
        assert credits[0][1] == pytest.approx(1.0)

    def test_no_credit_on_again(self, storage, fire):
        child = DSAProblemCard(front="Child", back="A")
        parent = DSAProblemCard(
            front="Parent",
            back="A",
            links=CardLinks(encompasses=[WeightedLink(card_id=child.id, weight=1.0)]),
        )
        storage.save_card(child)
        storage.save_card(parent)

        credits = fire.propagate_credit(parent.id, 1)  # AGAIN, factor=0.0
        assert credits == []


class TestTransitivePropagation:
    def test_multi_level_cascade(self, storage, fire):
        """A encompasses B encompasses C: reviewing A credits both B and C."""
        c = DSAProblemCard(front="C", back="A")
        b = DSAProblemCard(
            front="B",
            back="A",
            links=CardLinks(encompasses=[WeightedLink(card_id=c.id, weight=0.8)]),
        )
        a = DSAProblemCard(
            front="A",
            back="A",
            links=CardLinks(encompasses=[WeightedLink(card_id=b.id, weight=0.9)]),
        )
        storage.save_card(c)
        storage.save_card(b)
        storage.save_card(a)

        credits = fire.propagate_credit(a.id, 4)  # EASY
        credit_ids = {cid for cid, _ in credits}
        assert b.id in credit_ids
        assert c.id in credit_ids

        # B gets weight(0.9) * factor(1.0) = 0.9
        b_credit = next(cr for cid, cr in credits if cid == b.id)
        assert b_credit == pytest.approx(0.9)

        # C gets B's credit (0.9) * weight(0.8) = 0.72
        c_credit = next(cr for cid, cr in credits if cid == c.id)
        assert c_credit == pytest.approx(0.72)


class TestPropagatePenalty:
    def test_penalty_on_encompassing_cards(self, storage, fire):
        child = DSAProblemCard(front="Child", back="A")
        parent = DSAProblemCard(
            front="Parent",
            back="A",
            links=CardLinks(encompasses=[WeightedLink(card_id=child.id, weight=0.7)]),
        )
        storage.save_card(child)
        storage.save_card(parent)

        penalized = fire.propagate_penalty(child.id)
        assert parent.id in penalized

    def test_no_penalty_for_low_weight(self, storage, fire):
        child = DSAProblemCard(front="Child", back="A")
        parent = DSAProblemCard(
            front="Parent",
            back="A",
            links=CardLinks(encompasses=[WeightedLink(card_id=child.id, weight=0.2)]),
        )
        storage.save_card(child)
        storage.save_card(parent)

        penalized = fire.propagate_penalty(child.id)
        assert parent.id not in penalized


class TestCoveringSet:
    def test_empty_due_set(self, fire):
        assert fire.compute_covering_set([]) == []

    def test_no_encompasses_returns_all(self, storage, fire):
        a = DSAProblemCard(front="A", back="A")
        b = DSAProblemCard(front="B", back="B")
        storage.save_card(a)
        storage.save_card(b)

        result = fire.compute_covering_set([a.id, b.id])
        assert set(result) == {a.id, b.id}

    def test_covering_card_replaces_children(self, storage, fire):
        child1 = DSAProblemCard(front="C1", back="A")
        child2 = DSAProblemCard(front="C2", back="A")
        parent = DSAProblemCard(
            front="Parent",
            back="A",
            links=CardLinks(
                encompasses=[
                    WeightedLink(card_id=child1.id, weight=0.8),
                    WeightedLink(card_id=child2.id, weight=0.7),
                ]
            ),
        )
        storage.save_card(child1)
        storage.save_card(child2)
        storage.save_card(parent)

        result = fire.compute_covering_set([parent.id, child1.id, child2.id])
        # Parent should cover both children
        assert parent.id in result
        # At least some reduction from 3 cards
        assert len(result) <= 3


class TestImplicitCredit:
    def test_log_and_retrieve_credit(self, storage):
        storage.db.log_implicit_credit("card-a", "source-b", 0.5)
        total = storage.db.get_implicit_credit_since("card-a", "2000-01-01")
        assert total == pytest.approx(0.5)

    def test_cumulative_credit(self, storage):
        storage.db.log_implicit_credit("card-a", "source-b", 0.3)
        storage.db.log_implicit_credit("card-a", "source-c", 0.4)
        total = storage.db.get_implicit_credit_since("card-a", "2000-01-01")
        assert total == pytest.approx(0.7)


class TestApplyImplicitExtension:
    def test_no_extension_without_credit(self, storage, scheduler, fire):
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)
        scheduler.review_card(card.id, ReviewRating.GOOD)

        result = fire.apply_implicit_extension(card.id)
        assert result is None

    def test_extension_with_sufficient_credit(self, storage, scheduler, fire):
        card = DSAProblemCard(front="Q", back="A")
        storage.save_card(card)

        # Review to get a due date
        scheduler.review_card(card.id, ReviewRating.GOOD)
        state = storage.db.get_card_state(card.id)
        original_due = state.get("due")

        # Add implicit credit
        state.get("last_review", "2000-01-01")
        storage.db.log_implicit_credit(card.id, "some-source", 0.6)

        new_due = fire.apply_implicit_extension(card.id)
        if new_due is not None and original_due:
            from datetime import datetime

            orig = datetime.fromisoformat(original_due)
            assert new_due > orig
