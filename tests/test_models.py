"""Tests for Aletheia models."""

import pytest
from aletheia.core.models import (
    CardType,
    Complexity,
    DSAConceptCard,
    DSAProblemCard,
    LeetcodeSource,
    Maturity,
    SystemDesignCard,
    card_from_dict,
)


class TestDSAProblemCard:
    """Tests for DSAProblemCard."""

    def test_create_minimal(self):
        """Test creating a minimal DSA problem card."""
        card = DSAProblemCard(
            front="What is the time complexity of binary search?",
            back="O(log n)",
        )
        assert card.type == CardType.DSA_PROBLEM
        assert card.front == "What is the time complexity of binary search?"
        assert card.back == "O(log n)"
        assert card.maturity == Maturity.ACTIVE
        assert card.id is not None

    def test_create_full(self):
        """Test creating a full DSA problem card."""
        card = DSAProblemCard(
            front="How do you trap rain water in O(n) time and O(1) space?",
            back="Use two pointers from both ends",
            problem_source=LeetcodeSource(
                platform_id="42",
                title="Trapping Rain Water",
                difficulty="hard",
            ),
            patterns=["two-pointers", "monotonic-stack"],
            data_structures=["array"],
            complexity=Complexity(time="O(n)", space="O(1)"),
            intuition="Process from the side with smaller max",
            edge_cases=["empty array", "single element"],
            tags=["#interview-classic"],
            taxonomy=["dsa", "arrays"],
        )
        assert card.patterns == ["two-pointers", "monotonic-stack"]
        assert card.complexity.time == "O(n)"
        assert card.problem_source.difficulty == "hard"

    def test_touch_updates_metadata(self):
        """Test that touch() updates lifecycle metadata."""
        card = DSAProblemCard(front="Q", back="A")
        original_count = card.lifecycle.edit_count
        card.touch()
        assert card.lifecycle.edit_count == original_count + 1


class TestDSAConceptCard:
    """Tests for DSAConceptCard."""

    def test_create(self):
        """Test creating a DSA concept card."""
        card = DSAConceptCard(
            name="Monotonic Stack",
            front="When would you use a monotonic stack?",
            back="For next greater/smaller element problems",
            definition="A stack that maintains elements in sorted order",
            common_patterns=["next greater element", "histogram"],
        )
        assert card.type == CardType.DSA_CONCEPT
        assert card.name == "Monotonic Stack"


class TestSystemDesignCard:
    """Tests for SystemDesignCard."""

    def test_create(self):
        """Test creating a system design card."""
        card = SystemDesignCard(
            name="Leader-Follower Replication",
            front="When to use leader-follower replication?",
            back="Read-heavy workloads with eventual consistency acceptable",
            use_cases=["read replicas", "reporting databases"],
            anti_patterns=["write-heavy workloads"],
        )
        assert card.type == CardType.SYSTEM_DESIGN
        assert card.name == "Leader-Follower Replication"


class TestCardFromDict:
    """Tests for card_from_dict factory function."""

    def test_dsa_problem(self):
        """Test loading DSA problem from dict."""
        data = {
            "type": "dsa-problem",
            "front": "Q",
            "back": "A",
            "patterns": ["two-pointers"],
        }
        card = card_from_dict(data)
        assert isinstance(card, DSAProblemCard)
        assert card.patterns == ["two-pointers"]

    def test_dsa_concept(self):
        """Test loading DSA concept from dict."""
        data = {
            "type": "dsa-concept",
            "name": "Binary Search",
            "front": "Q",
            "back": "A",
        }
        card = card_from_dict(data)
        assert isinstance(card, DSAConceptCard)
        assert card.name == "Binary Search"

    def test_system_design(self):
        """Test loading system design card from dict."""
        data = {
            "type": "system-design",
            "name": "CAP Theorem",
            "front": "Q",
            "back": "A",
        }
        card = card_from_dict(data)
        assert isinstance(card, SystemDesignCard)

    def test_unknown_type_raises(self):
        """Test that unknown type raises ValueError."""
        data = {"type": "unknown", "front": "Q", "back": "A"}
        with pytest.raises(ValueError, match="Unknown card type"):
            card_from_dict(data)


class TestLeetcodeSource:
    """Tests for LeetcodeSource with new leetcode integration fields."""

    def test_new_fields_round_trip(self):
        """Test language and internal_question_id serialize and deserialize."""
        source = LeetcodeSource(
            platform_id="42",
            title="Trapping Rain Water",
            difficulty="hard",
            language="python3",
            internal_question_id="317",
        )
        data = source.model_dump()
        restored = LeetcodeSource.model_validate(data)
        assert restored.language == "python3"
        assert restored.internal_question_id == "317"

    def test_backwards_compat_missing_new_fields(self):
        """Test that existing cards without new fields still parse."""
        data = {
            "type": "leetcode",
            "platform": "leetcode",
            "platform_id": "1",
            "title": "Two Sum",
            "difficulty": "easy",
        }
        source = LeetcodeSource.model_validate(data)
        assert source.language is None
        assert source.internal_question_id is None

    def test_new_fields_default_none(self):
        """Test that new fields default to None."""
        source = LeetcodeSource(platform_id="1", title="Two Sum")
        assert source.language is None
        assert source.internal_question_id is None

    def test_dsa_problem_card_with_new_source_fields(self):
        """Test DSAProblemCard with LeetcodeSource containing new fields."""
        card = DSAProblemCard(
            front="Q",
            back="A",
            problem_source=LeetcodeSource(
                platform_id="42",
                title="Trapping Rain Water",
                difficulty="hard",
                language="python3",
                internal_question_id="317",
            ),
        )
        data = card.model_dump()
        restored = card_from_dict(data)
        assert restored.problem_source.language == "python3"
        assert restored.problem_source.internal_question_id == "317"
