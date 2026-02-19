"""LLM integration for Aletheia."""

from aletheia.llm.service import (
    FailureClassification,
    FailureType,
    LinkSuggestion,
    LLMError,
    LLMService,
    QualityFeedback,
    QualityIssue,
)

__all__ = [
    "FailureClassification",
    "FailureType",
    "LLMService",
    "LLMError",
    "LinkSuggestion",
    "QualityFeedback",
    "QualityIssue",
]
