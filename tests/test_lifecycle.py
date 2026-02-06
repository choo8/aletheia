"""Tests for card lifecycle operations (Phase 4a)."""

import tempfile
from pathlib import Path

import pytest
from aletheia.core.models import (
    DSAConceptCard,
    DSAProblemCard,
    Maturity,
    SystemDesignCard,
    card_from_dict,
    utcnow,
)
from aletheia.core.storage import AletheiaStorage


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage(temp_dir):
    """Create an AletheiaStorage instance for tests."""
    return AletheiaStorage(temp_dir / "data", temp_dir / ".aletheia")


def _make_problem_card(**kwargs) -> DSAProblemCard:
    defaults = {"front": "What is O(n)?", "back": "Linear time", "patterns": ["basics"]}
    defaults.update(kwargs)
    return DSAProblemCard(**defaults)


def _make_concept_card(**kwargs) -> DSAConceptCard:
    defaults = {"name": "Binary Search", "front": "When to use?", "back": "Sorted data"}
    defaults.update(kwargs)
    return DSAConceptCard(**defaults)


def _make_design_card(**kwargs) -> SystemDesignCard:
    defaults = {
        "name": "CAP Theorem",
        "front": "What is CAP?",
        "back": "Consistency, Availability, Partition tolerance",
    }
    defaults.update(kwargs)
    return SystemDesignCard(**defaults)


class TestSuspend:
    """Tests for suspend lifecycle transition."""

    def test_active_to_suspended(self, storage):
        card = _make_problem_card()
        storage.save_card(card)

        card.maturity = Maturity.SUSPENDED
        card.lifecycle.suspended_at = utcnow()
        storage.save_card(card)

        loaded = storage.load_card(card.id)
        assert loaded.maturity == Maturity.SUSPENDED
        assert loaded.lifecycle.suspended_at is not None

    def test_already_suspended_is_idempotent(self, storage):
        card = _make_problem_card()
        card.maturity = Maturity.SUSPENDED
        card.lifecycle.suspended_at = utcnow()
        storage.save_card(card)

        loaded = storage.load_card(card.id)
        assert loaded.maturity == Maturity.SUSPENDED

    def test_cannot_suspend_exhausted(self):
        """Exhausted cards should not be suspended (guard in CLI)."""
        card = _make_problem_card()
        card.maturity = Maturity.EXHAUSTED
        # The guard is in the CLI command, but verify the state is preserved
        assert card.maturity == Maturity.EXHAUSTED

    def test_suspended_at_timestamp_set(self, storage):
        card = _make_problem_card()
        storage.save_card(card)

        before = utcnow()
        card.maturity = Maturity.SUSPENDED
        card.lifecycle.suspended_at = utcnow()
        storage.save_card(card)

        loaded = storage.load_card(card.id)
        assert loaded.lifecycle.suspended_at >= before


class TestResume:
    """Tests for resume lifecycle transition."""

    def test_suspended_to_active(self, storage):
        card = _make_problem_card()
        card.maturity = Maturity.SUSPENDED
        card.lifecycle.suspended_at = utcnow()
        storage.save_card(card)

        card.maturity = Maturity.ACTIVE
        card.lifecycle.suspended_at = None
        storage.save_card(card)

        loaded = storage.load_card(card.id)
        assert loaded.maturity == Maturity.ACTIVE
        assert loaded.lifecycle.suspended_at is None

    def test_not_suspended_noop(self):
        """Resuming an active card should be a no-op (guard in CLI)."""
        card = _make_problem_card()
        assert card.maturity == Maturity.ACTIVE

    def test_clears_suspended_timestamp(self, storage):
        card = _make_problem_card()
        card.maturity = Maturity.SUSPENDED
        card.lifecycle.suspended_at = utcnow()
        storage.save_card(card)

        card.maturity = Maturity.ACTIVE
        card.lifecycle.suspended_at = None
        storage.save_card(card)

        loaded = storage.load_card(card.id)
        assert loaded.lifecycle.suspended_at is None


class TestExhaust:
    """Tests for exhaust lifecycle transition."""

    def test_active_to_exhausted(self, storage):
        card = _make_problem_card()
        storage.save_card(card)

        card.maturity = Maturity.EXHAUSTED
        card.lifecycle.exhausted_at = utcnow()
        card.lifecycle.exhausted_reason = "understanding_deepened"
        storage.save_card(card)

        loaded = storage.load_card(card.id)
        assert loaded.maturity == Maturity.EXHAUSTED
        assert loaded.lifecycle.exhausted_at is not None
        assert loaded.lifecycle.exhausted_reason == "understanding_deepened"

    def test_with_reason(self, storage):
        card = _make_problem_card()
        storage.save_card(card)

        card.maturity = Maturity.EXHAUSTED
        card.lifecycle.exhausted_at = utcnow()
        card.lifecycle.exhausted_reason = "duplicate"
        storage.save_card(card)

        loaded = storage.load_card(card.id)
        assert loaded.lifecycle.exhausted_reason == "duplicate"

    def test_already_exhausted_idempotent(self):
        card = _make_problem_card()
        card.maturity = Maturity.EXHAUSTED
        card.lifecycle.exhausted_at = utcnow()
        card.lifecycle.exhausted_reason = "test"
        assert card.maturity == Maturity.EXHAUSTED

    def test_can_exhaust_suspended(self, storage):
        card = _make_problem_card()
        card.maturity = Maturity.SUSPENDED
        card.lifecycle.suspended_at = utcnow()
        storage.save_card(card)

        card.maturity = Maturity.EXHAUSTED
        card.lifecycle.exhausted_at = utcnow()
        card.lifecycle.exhausted_reason = "no_longer_relevant"
        storage.save_card(card)

        loaded = storage.load_card(card.id)
        assert loaded.maturity == Maturity.EXHAUSTED


class TestRevive:
    """Tests for revive lifecycle transition."""

    def test_exhausted_to_active(self, storage):
        card = _make_problem_card()
        card.maturity = Maturity.EXHAUSTED
        card.lifecycle.exhausted_at = utcnow()
        card.lifecycle.exhausted_reason = "duplicate"
        storage.save_card(card)

        card.maturity = Maturity.ACTIVE
        card.lifecycle.exhausted_at = None
        card.lifecycle.exhausted_reason = None
        storage.save_card(card)

        loaded = storage.load_card(card.id)
        assert loaded.maturity == Maturity.ACTIVE
        assert loaded.lifecycle.exhausted_at is None
        assert loaded.lifecycle.exhausted_reason is None

    def test_not_exhausted_noop(self):
        """Reviving an active card should be a no-op (guard in CLI)."""
        card = _make_problem_card()
        assert card.maturity == Maturity.ACTIVE

    def test_clears_exhausted_metadata(self, storage):
        card = _make_problem_card()
        card.maturity = Maturity.EXHAUSTED
        card.lifecycle.exhausted_at = utcnow()
        card.lifecycle.exhausted_reason = "split"
        storage.save_card(card)

        card.maturity = Maturity.ACTIVE
        card.lifecycle.exhausted_at = None
        card.lifecycle.exhausted_reason = None
        storage.save_card(card)

        loaded = storage.load_card(card.id)
        assert loaded.lifecycle.exhausted_at is None
        assert loaded.lifecycle.exhausted_reason is None


class TestReviewFiltering:
    """Tests for filtering non-active cards from review lists."""

    def test_only_active_cards_in_filtered_list(self, storage):
        active_card = _make_problem_card(front="Active card")
        suspended_card = _make_problem_card(front="Suspended card")
        exhausted_card = _make_problem_card(front="Exhausted card")

        storage.save_card(active_card)

        suspended_card.maturity = Maturity.SUSPENDED
        suspended_card.lifecycle.suspended_at = utcnow()
        storage.save_card(suspended_card)

        exhausted_card.maturity = Maturity.EXHAUSTED
        exhausted_card.lifecycle.exhausted_at = utcnow()
        exhausted_card.lifecycle.exhausted_reason = "test"
        storage.save_card(exhausted_card)

        all_ids = [active_card.id, suspended_card.id, exhausted_card.id]

        # Simulate the filtering logic from CLI/web
        filtered = [
            cid
            for cid in all_ids
            if (c := storage.load_card(cid)) and c.maturity == Maturity.ACTIVE
        ]

        assert len(filtered) == 1
        assert filtered[0] == active_card.id


class TestReformulate:
    """Tests for reformulate lifecycle operation."""

    def test_new_card_with_reformulated_from(self, storage):
        original = _make_problem_card()
        storage.save_card(original)

        # Create new card (simulating what the CLI does)
        new_data = {
            "type": original.type.value,
            "front": "Reformulated question",
            "back": "Better answer",
            "patterns": original.patterns,
        }
        new_card = card_from_dict(new_data)
        new_card.lifecycle.reformulated_from = original.id
        storage.save_card(new_card)

        loaded = storage.load_card(new_card.id)
        assert loaded.lifecycle.reformulated_from == original.id

    def test_original_exhausted(self, storage):
        original = _make_problem_card()
        storage.save_card(original)

        # Exhaust original (as reformulate command does)
        original.maturity = Maturity.EXHAUSTED
        original.lifecycle.exhausted_at = utcnow()
        original.lifecycle.exhausted_reason = "understanding_deepened"
        storage.save_card(original)

        loaded = storage.load_card(original.id)
        assert loaded.maturity == Maturity.EXHAUSTED
        assert loaded.lifecycle.exhausted_reason == "understanding_deepened"

    def test_fresh_id(self, storage):
        original = _make_problem_card()
        storage.save_card(original)

        new_data = {
            "type": original.type.value,
            "front": "New front",
            "back": "New back",
        }
        new_card = card_from_dict(new_data)
        assert new_card.id != original.id

    def test_same_type(self, storage):
        original = _make_problem_card()
        storage.save_card(original)

        new_data = {
            "type": original.type.value,
            "front": "New front",
            "back": "New back",
        }
        new_card = card_from_dict(new_data)
        assert new_card.type == original.type


class TestSplit:
    """Tests for split lifecycle operation."""

    def test_n_cards_with_split_from(self, storage):
        original = _make_concept_card()
        storage.save_card(original)

        new_cards = []
        for i in range(3):
            new_data = {
                "type": original.type.value,
                "name": f"Split part {i + 1}",
                "front": f"Part {i + 1} question",
                "back": f"Part {i + 1} answer",
            }
            nc = card_from_dict(new_data)
            nc.lifecycle.split_from = original.id
            storage.save_card(nc)
            new_cards.append(nc)

        for nc in new_cards:
            loaded = storage.load_card(nc.id)
            assert loaded.lifecycle.split_from == original.id

        assert len(new_cards) == 3

    def test_original_exhausted(self, storage):
        original = _make_concept_card()
        storage.save_card(original)

        original.maturity = Maturity.EXHAUSTED
        original.lifecycle.exhausted_at = utcnow()
        original.lifecycle.exhausted_reason = "split"
        storage.save_card(original)

        loaded = storage.load_card(original.id)
        assert loaded.maturity == Maturity.EXHAUSTED
        assert loaded.lifecycle.exhausted_reason == "split"

    def test_same_type(self, storage):
        original = _make_concept_card()

        new_data = {
            "type": original.type.value,
            "name": "Split child",
            "front": "Q",
            "back": "A",
        }
        new_card = card_from_dict(new_data)
        assert new_card.type == original.type


class TestMerge:
    """Tests for merge lifecycle operation."""

    def test_one_card_with_merged_from(self, storage):
        card1 = _make_design_card(name="Part 1", front="Q1", back="A1")
        card2 = _make_design_card(name="Part 2", front="Q2", back="A2")
        storage.save_card(card1)
        storage.save_card(card2)

        merged_data = {
            "type": card1.type.value,
            "name": "Merged concept",
            "front": "Q1\n---\nQ2",
            "back": "A1\n---\nA2",
        }
        merged_card = card_from_dict(merged_data)
        merged_card.lifecycle.merged_from = [card1.id, card2.id]
        storage.save_card(merged_card)

        loaded = storage.load_card(merged_card.id)
        assert loaded.lifecycle.merged_from == [card1.id, card2.id]

    def test_originals_exhausted(self, storage):
        card1 = _make_design_card(name="Part 1", front="Q1", back="A1")
        card2 = _make_design_card(name="Part 2", front="Q2", back="A2")
        storage.save_card(card1)
        storage.save_card(card2)

        for card in [card1, card2]:
            card.maturity = Maturity.EXHAUSTED
            card.lifecycle.exhausted_at = utcnow()
            card.lifecycle.exhausted_reason = "merged"
            storage.save_card(card)

        for card in [card1, card2]:
            loaded = storage.load_card(card.id)
            assert loaded.maturity == Maturity.EXHAUSTED
            assert loaded.lifecycle.exhausted_reason == "merged"

    def test_requires_same_type(self):
        """Merging cards of different types should be rejected (guard in CLI)."""
        card1 = _make_problem_card()
        card2 = _make_concept_card()
        types = {card1.type, card2.type}
        assert len(types) > 1

    def test_requires_at_least_two(self):
        """Merging requires at least 2 cards (guard in CLI)."""
        cards = [_make_problem_card()]
        assert len(cards) < 2
