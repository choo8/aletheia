"""Tests for the LLM module."""

from unittest.mock import patch

import pytest
from aletheia.llm import LLMError, LLMService, QualityFeedback, QualityIssue
from aletheia.llm.prompts import (
    DOMAIN_TEMPLATES,
    get_edit_extraction_prompt,
    get_extraction_prompt,
    get_quality_prompt,
)


class TestPrompts:
    """Tests for system prompts."""

    def test_domain_templates_exist(self):
        """Test that domain templates are defined."""
        assert "dsa-problem" in DOMAIN_TEMPLATES
        assert "dsa-concept" in DOMAIN_TEMPLATES
        assert "system-design" in DOMAIN_TEMPLATES
        assert "math" in DOMAIN_TEMPLATES
        assert "research" in DOMAIN_TEMPLATES

    def test_get_extraction_prompt_contains_domain_template(self):
        """Test that extraction prompt includes domain-specific template."""
        prompt = get_extraction_prompt("dsa-problem")
        assert "key insight" in prompt.lower()
        assert "JSON" in prompt

    def test_get_extraction_prompt_fallback(self):
        """Test that unknown domains fall back to dsa-problem."""
        prompt = get_extraction_prompt("unknown-domain")
        assert "key insight" in prompt.lower()

    def test_get_quality_prompt_contains_criteria(self):
        """Test that quality prompt includes evaluation criteria."""
        prompt = get_quality_prompt()
        assert "Focused" in prompt
        assert "Precise" in prompt
        assert "Consistent" in prompt
        assert "JSON" in prompt


class TestLLMService:
    """Tests for LLMService."""

    @patch.dict("os.environ", {}, clear=False)
    def test_init_default_model(self):
        """Test default model initialization."""
        import os

        os.environ.pop("ALETHEIA_LLM_MODEL", None)
        service = LLMService()
        assert service.model == "gemini/gemini-3-flash-preview"

    def test_init_custom_model(self):
        """Test custom model initialization."""
        service = LLMService(model="gpt-4")
        assert service.model == "gpt-4"

    @patch.dict("os.environ", {"ALETHEIA_LLM_MODEL": "custom-model"})
    def test_init_from_env(self):
        """Test model from environment variable."""
        service = LLMService()
        assert service.model == "custom-model"

    def test_guided_extraction_success(self):
        """Test successful guided extraction."""
        service = LLMService()

        with patch.object(
            service,
            "_get_completion",
            return_value='["What is the key insight?", "Why does this work?"]',
        ):
            questions = service.guided_extraction("Solved two-sum with hash map", "dsa-problem")

        assert len(questions) == 2
        assert "key insight" in questions[0].lower()

    def test_guided_extraction_handles_markdown(self):
        """Test that markdown code fences are stripped."""
        service = LLMService()

        with patch.object(
            service,
            "_get_completion",
            return_value='```json\n["Question 1?", "Question 2?"]\n```',
        ):
            questions = service.guided_extraction("context", "dsa-problem")

        assert len(questions) == 2
        assert questions[0] == "Question 1?"

    def test_guided_extraction_invalid_json(self):
        """Test error handling for invalid JSON response."""
        service = LLMService()

        with patch.object(service, "_get_completion", return_value="not valid json"):
            with pytest.raises(LLMError, match="Failed to parse"):
                service.guided_extraction("context", "dsa-problem")

    def test_quality_feedback_success(self):
        """Test successful quality feedback."""
        service = LLMService()

        mock_response = """{
            "overall_quality": "needs_work",
            "strengths": ["Good specificity"],
            "issues": [
                {
                    "type": "too_vague",
                    "description": "Question is too broad",
                    "suggestion": "Be more specific"
                }
            ],
            "suggested_front": "Better question?",
            "suggested_back": null
        }"""

        with patch.object(service, "_get_completion", return_value=mock_response):
            feedback = service.quality_feedback(
                "Explain two pointers", "Two pointers explanation", "dsa-problem"
            )

        assert isinstance(feedback, QualityFeedback)
        assert feedback.overall_quality == "needs_work"
        assert len(feedback.strengths) == 1
        assert len(feedback.issues) == 1
        assert feedback.issues[0].type == "too_vague"
        assert feedback.suggested_front == "Better question?"

    def test_quality_feedback_good_card(self):
        """Test quality feedback for a good card."""
        service = LLMService()

        mock_response = """{
            "overall_quality": "good",
            "strengths": ["Specific", "Atomic", "Clear answer"],
            "issues": []
        }"""

        with patch.object(service, "_get_completion", return_value=mock_response):
            feedback = service.quality_feedback(
                "What invariant does two-pointers maintain in Trapping Rain Water?",
                "left_max[i] >= height[i] and right_max[i] >= height[i]",
                "dsa-problem",
            )

        assert feedback.overall_quality == "good"
        assert len(feedback.issues) == 0

    def test_api_error_handling(self):
        """Test error handling for API failures."""
        service = LLMService()

        with patch.object(service, "_get_completion", side_effect=LLMError("API rate limited")):
            with pytest.raises(LLMError, match="API rate limited"):
                service.guided_extraction("context", "dsa-problem")


class TestQualityFeedback:
    """Tests for QualityFeedback dataclass."""

    def test_quality_feedback_creation(self):
        """Test creating QualityFeedback."""
        feedback = QualityFeedback(
            overall_quality="good",
            strengths=["Clear", "Specific"],
            issues=[],
        )
        assert feedback.overall_quality == "good"
        assert len(feedback.strengths) == 2
        assert feedback.suggested_front is None

    def test_quality_issue_creation(self):
        """Test creating QualityIssue."""
        issue = QualityIssue(
            type="too_vague",
            description="Question is too broad",
            suggestion="Add more context",
        )
        assert issue.type == "too_vague"
        assert "broad" in issue.description


class TestEditExtractionPrompts:
    """Tests for edit extraction prompts."""

    def test_edit_prompt_contains_refinement_language(self):
        """Test that edit prompt uses refinement/existing framing."""
        prompt = get_edit_extraction_prompt("dsa-problem")
        assert "refine" in prompt.lower()
        assert "existing" in prompt.lower()
        assert "delta" in prompt.lower()

    def test_edit_prompt_includes_domain_template(self):
        """Test that edit prompt includes domain-specific template."""
        prompt = get_edit_extraction_prompt("dsa-problem")
        assert "key insight" in prompt.lower()
        assert "JSON" in prompt

    def test_edit_prompt_unknown_domain_falls_back(self):
        """Test that unknown domains fall back to dsa-problem."""
        prompt = get_edit_extraction_prompt("unknown-domain")
        assert "key insight" in prompt.lower()


class TestGuidedEditExtraction:
    """Tests for guided_edit_extraction method."""

    def test_guided_edit_extraction_success(self):
        """Test successful guided edit extraction returns questions with correct user message."""
        service = LLMService()

        def mock_completion(system_prompt, user_message):
            # Verify user message contains both existing card and new context
            assert "EXISTING CARD:" in user_message
            assert "NEW CONTEXT:" in user_message
            assert "Two Sum" in user_message
            assert "learned about early termination" in user_message
            return '["How has your intuition changed?", "What new edge cases did you find?"]'

        with patch.object(service, "_get_completion", side_effect=mock_completion):
            questions = service.guided_edit_extraction(
                "Type: dsa-problem\nFront: Two Sum",
                "learned about early termination",
                "dsa-problem",
            )

        assert len(questions) == 2
        assert "intuition" in questions[0].lower()

    def test_guided_edit_extraction_handles_markdown(self):
        """Test that markdown code fences are stripped."""
        service = LLMService()

        with patch.object(
            service,
            "_get_completion",
            return_value='```json\n["Question 1?", "Question 2?"]\n```',
        ):
            questions = service.guided_edit_extraction("card content", "new context", "dsa-problem")

        assert len(questions) == 2
        assert questions[0] == "Question 1?"

    def test_guided_edit_extraction_invalid_json(self):
        """Test error handling for invalid JSON response."""
        service = LLMService()

        with patch.object(service, "_get_completion", return_value="not valid json"):
            with pytest.raises(LLMError, match="Failed to parse"):
                service.guided_edit_extraction("card content", "new context", "dsa-problem")

    def test_guided_edit_extraction_api_error(self):
        """Test error propagation from API failures."""
        service = LLMService()

        with patch.object(service, "_get_completion", side_effect=LLMError("API rate limited")):
            with pytest.raises(LLMError, match="API rate limited"):
                service.guided_edit_extraction("card content", "new context", "dsa-problem")


class TestLLMError:
    """Tests for LLMError exception."""

    def test_llm_error_message(self):
        """Test LLMError preserves message."""
        error = LLMError("API rate limited")
        assert str(error) == "API rate limited"

    def test_llm_error_can_be_raised(self):
        """Test LLMError can be raised and caught."""
        with pytest.raises(LLMError):
            raise LLMError("Test error")
