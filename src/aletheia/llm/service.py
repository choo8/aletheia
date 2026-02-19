"""LLM service for Aletheia using litellm."""

import json
import os
from dataclasses import dataclass, field
from enum import StrEnum

from aletheia.llm.prompts import (
    get_edit_extraction_prompt,
    get_extraction_prompt,
    get_link_suggestion_prompt,
    get_quality_prompt,
)


class FailureType(StrEnum):
    """Types of LeetCode submission failure."""

    CONCEPTUAL = "conceptual"  # wrong approach entirely
    TECHNIQUE = "technique"  # right approach, wrong technique
    MECHANICAL = "mechanical"  # right everything, coding bug
    TRIVIAL = "trivial"  # typo/syntax error


@dataclass
class FailureClassification:
    """Result of classifying a LeetCode submission failure."""

    failure_type: FailureType
    explanation: str
    understanding_rating: int  # suggested rating for understanding card (1-4)
    implementation_rating: int  # suggested rating for implementation card (1-4)


@dataclass
class LinkSuggestion:
    """A suggested link between two cards."""

    source_id: str
    target_id: str
    link_type: str
    weight: float | None = None
    rationale: str = ""


@dataclass
class QualityIssue:
    """A quality issue found in a card."""

    type: str
    description: str
    suggestion: str


@dataclass
class QualityFeedback:
    """Feedback on card quality."""

    overall_quality: str  # "good", "needs_work", "poor"
    strengths: list[str] = field(default_factory=list)
    issues: list[QualityIssue] = field(default_factory=list)
    suggested_front: str | None = None
    suggested_back: str | None = None


class LLMService:
    """LLM service for guided extraction and quality feedback."""

    def __init__(self, model: str | None = None):
        """Initialize the LLM service.

        Args:
            model: Model identifier (e.g., "gemini/gemini-3-flash-preview", "gpt-4").
                   Defaults to ALETHEIA_LLM_MODEL env var or gemini/gemini-3-flash-preview.
        """
        self.model = model or os.environ.get("ALETHEIA_LLM_MODEL", "gemini/gemini-3-flash-preview")

    def _get_completion(self, system_prompt: str, user_message: str) -> str:
        """Get a completion from the LLM.

        Args:
            system_prompt: The system prompt
            user_message: The user message

        Returns:
            The assistant's response text

        Raises:
            LLMError: If the API call fails
        """
        try:
            from litellm import completion

            response = completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.7,
            )
            return response.choices[0].message.content
        except ImportError as e:
            raise LLMError("litellm not installed. Install with: pip install aletheia[llm]") from e
        except Exception as e:
            raise LLMError(f"LLM API error: {e}") from e

    def guided_extraction(self, context: str, domain: str) -> list[str]:
        """Generate Socratic questions for guided extraction.

        Args:
            context: User's description of what they learned
            domain: Card domain (dsa-problem, dsa-concept, system-design, etc.)

        Returns:
            List of Socratic questions to ask the user

        Raises:
            LLMError: If the API call fails or response is invalid
        """
        system_prompt = get_extraction_prompt(domain)
        response = self._get_completion(system_prompt, context)

        # Parse JSON response
        try:
            # Handle potential markdown code blocks
            text = response.strip()
            if text.startswith("```"):
                # Remove markdown code fence
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            questions = json.loads(text)
            if not isinstance(questions, list):
                raise LLMError("Expected a list of questions")
            return [str(q) for q in questions]
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse LLM response as JSON: {e}") from e

    def guided_edit_extraction(
        self, existing_card_content: str, new_context: str, domain: str
    ) -> list[str]:
        """Generate Socratic questions for refining an existing card.

        Args:
            existing_card_content: Formatted string of the existing card
            new_context: User's description of what changed in their understanding
            domain: Card domain (dsa-problem, dsa-concept, system-design, etc.)

        Returns:
            List of Socratic questions focused on the delta

        Raises:
            LLMError: If the API call fails or response is invalid
        """
        system_prompt = get_edit_extraction_prompt(domain)
        user_message = f"EXISTING CARD:\n{existing_card_content}\n\nNEW CONTEXT:\n{new_context}"
        response = self._get_completion(system_prompt, user_message)

        # Parse JSON response
        try:
            # Handle potential markdown code blocks
            text = response.strip()
            if text.startswith("```"):
                # Remove markdown code fence
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            questions = json.loads(text)
            if not isinstance(questions, list):
                raise LLMError("Expected a list of questions")
            return [str(q) for q in questions]
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse LLM response as JSON: {e}") from e

    def quality_feedback(self, front: str, back: str, card_type: str) -> QualityFeedback:
        """Get quality feedback on a card.

        Args:
            front: Card front (question)
            back: Card back (answer)
            card_type: Type of card for context

        Returns:
            QualityFeedback with analysis and suggestions

        Raises:
            LLMError: If the API call fails or response is invalid
        """
        system_prompt = get_quality_prompt()
        user_message = f"""Card type: {card_type}

Front (Question):
{front}

Back (Answer):
{back}"""

        response = self._get_completion(system_prompt, user_message)

        # Parse JSON response
        try:
            text = response.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            data = json.loads(text)

            issues = [
                QualityIssue(
                    type=issue.get("type", "unknown"),
                    description=issue.get("description", ""),
                    suggestion=issue.get("suggestion", ""),
                )
                for issue in data.get("issues", [])
            ]

            return QualityFeedback(
                overall_quality=data.get("overall_quality", "needs_work"),
                strengths=data.get("strengths", []),
                issues=issues,
                suggested_front=data.get("suggested_front"),
                suggested_back=data.get("suggested_back"),
            )
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse LLM response as JSON: {e}") from e

    def classify_failure(
        self,
        problem_front: str,
        submitted_code: str,
        error_message: str,
    ) -> FailureClassification:
        """Classify a LeetCode submission failure.

        Args:
            problem_front: The problem description/question
            submitted_code: The code that was submitted
            error_message: The error or failure message from LeetCode

        Returns:
            FailureClassification with type and suggested ratings

        Raises:
            LLMError: If the API call fails or response is invalid
        """
        system_prompt = """You are a coding tutor analyzing a failed LeetCode submission.

Classify the failure into one of these types:
- **conceptual**: Wrong approach entirely (e.g., used brute force when DP was needed)
- **technique**: Right approach but wrong technique/detail (e.g., wrong data structure)
- **mechanical**: Right approach and technique but coding bug (e.g., off-by-one, wrong variable)
- **trivial**: Typo or syntax error

Also suggest FSRS ratings (1=Again, 2=Hard, 3=Good, 4=Easy) for:
- understanding_rating: how well they understood the approach
- implementation_rating: how well they implemented it

Format response as JSON:
{
  "failure_type": "conceptual|technique|mechanical|trivial",
  "explanation": "brief explanation of why this classification",
  "understanding_rating": 1-4,
  "implementation_rating": 1-4
}

Only output the JSON, nothing else."""

        user_message = f"""Problem: {problem_front}

Submitted Code:
```
{submitted_code}
```

Error: {error_message}"""

        response = self._get_completion(system_prompt, user_message)

        try:
            text = response.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            data = json.loads(text)
            return FailureClassification(
                failure_type=FailureType(data.get("failure_type", "mechanical")),
                explanation=data.get("explanation", ""),
                understanding_rating=data.get("understanding_rating", 1),
                implementation_rating=data.get("implementation_rating", 1),
            )
        except (json.JSONDecodeError, ValueError) as e:
            raise LLMError(f"Failed to parse failure classification: {e}") from e

    def suggest_links(
        self,
        card_front: str,
        card_back: str,
        card_id: str,
        candidates: list[dict],
    ) -> list[LinkSuggestion]:
        """Suggest links between a target card and candidate cards.

        Args:
            card_front: Target card's front text
            card_back: Target card's back text
            card_id: Target card's ID
            candidates: List of dicts with keys: id, front, back, type

        Returns:
            List of LinkSuggestion objects

        Raises:
            LLMError: If the API call fails or response is invalid
        """
        system_prompt = get_link_suggestion_prompt()

        candidate_text = "\n".join(
            f"- ID: {c['id'][:8]}, Type: {c['type']},"
            f" Front: {c['front'][:100]}, Back: {c['back'][:100]}"
            for c in candidates
        )

        user_message = f"""TARGET CARD (ID: {card_id[:8]}):
Front: {card_front}
Back: {card_back}

CANDIDATES:
{candidate_text}"""

        response = self._get_completion(system_prompt, user_message)

        try:
            text = response.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            data = json.loads(text)
            if not isinstance(data, list):
                raise LLMError("Expected a list of link suggestions")

            suggestions = []
            for item in data:
                suggestions.append(
                    LinkSuggestion(
                        source_id=card_id,
                        target_id=item.get("candidate_id", ""),
                        link_type=item.get("link_type", ""),
                        weight=item.get("weight"),
                        rationale=item.get("rationale", ""),
                    )
                )
            return suggestions
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse LLM response as JSON: {e}") from e


class LLMError(Exception):
    """Error from LLM service."""

    pass
