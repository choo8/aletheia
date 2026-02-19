"""Tests for Phase 6: Implementation Cards + Enhanced LeetCode Integration."""

import json
from unittest.mock import patch

from aletheia.core.models import (
    DSAProblemCard,
    DSAProblemSubtype,
    card_from_dict,
)
from aletheia.llm.service import FailureClassification, FailureType, LLMService


class TestDSAProblemSubtype:
    def test_default_is_understanding(self):
        card = DSAProblemCard(front="Q", back="A")
        assert card.card_subtype == DSAProblemSubtype.UNDERSTANDING

    def test_implementation_subtype(self):
        card = DSAProblemCard(
            front="Implement merge sort",
            back="Code solution",
            card_subtype=DSAProblemSubtype.IMPLEMENTATION,
        )
        assert card.card_subtype == DSAProblemSubtype.IMPLEMENTATION

    def test_backward_compat_no_subtype_field(self):
        """Existing cards without card_subtype should deserialize with default."""
        data = {
            "type": "dsa-problem",
            "front": "Q",
            "back": "A",
        }
        card = card_from_dict(data)
        assert card.card_subtype == DSAProblemSubtype.UNDERSTANDING

    def test_subtype_round_trip(self):
        card = DSAProblemCard(
            front="Q",
            back="A",
            card_subtype=DSAProblemSubtype.IMPLEMENTATION,
        )
        data = card.model_dump(mode="json")
        restored = card_from_dict(data)
        assert restored.card_subtype == DSAProblemSubtype.IMPLEMENTATION

    def test_subtype_enum_values(self):
        assert DSAProblemSubtype.UNDERSTANDING == "understanding"
        assert DSAProblemSubtype.IMPLEMENTATION == "implementation"


class TestFailureType:
    def test_enum_values(self):
        assert FailureType.CONCEPTUAL == "conceptual"
        assert FailureType.TECHNIQUE == "technique"
        assert FailureType.MECHANICAL == "mechanical"
        assert FailureType.TRIVIAL == "trivial"


class TestFailureClassification:
    def test_create(self):
        fc = FailureClassification(
            failure_type=FailureType.MECHANICAL,
            explanation="Off-by-one error in loop",
            understanding_rating=3,
            implementation_rating=2,
        )
        assert fc.failure_type == FailureType.MECHANICAL
        assert fc.understanding_rating == 3
        assert fc.implementation_rating == 2


class TestClassifyFailure:
    def test_parses_response(self):
        mock_response = json.dumps(
            {
                "failure_type": "mechanical",
                "explanation": "Off-by-one in loop bound",
                "understanding_rating": 3,
                "implementation_rating": 2,
            }
        )

        with patch.object(LLMService, "_get_completion", return_value=mock_response):
            llm = LLMService()
            result = llm.classify_failure("Two Sum problem", "def twoSum(): pass", "Wrong Answer")

        assert result.failure_type == FailureType.MECHANICAL
        assert result.understanding_rating == 3
        assert result.implementation_rating == 2

    def test_conceptual_failure(self):
        mock_response = json.dumps(
            {
                "failure_type": "conceptual",
                "explanation": "Used brute force instead of hash map",
                "understanding_rating": 1,
                "implementation_rating": 1,
            }
        )

        with patch.object(LLMService, "_get_completion", return_value=mock_response):
            llm = LLMService()
            result = llm.classify_failure("Two Sum", "for i in range(n): for j", "TLE")

        assert result.failure_type == FailureType.CONCEPTUAL
        assert result.understanding_rating == 1

    def test_trivial_failure(self):
        mock_response = json.dumps(
            {
                "failure_type": "trivial",
                "explanation": "Missing return statement",
                "understanding_rating": 4,
                "implementation_rating": 3,
            }
        )

        with patch.object(LLMService, "_get_completion", return_value=mock_response):
            llm = LLMService()
            result = llm.classify_failure("Problem", "code", "SyntaxError")

        assert result.failure_type == FailureType.TRIVIAL
