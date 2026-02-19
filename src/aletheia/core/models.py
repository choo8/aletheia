"""Pydantic models for Aletheia cards and related entities."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(UTC)


class CardType(StrEnum):
    """Types of cards supported by Aletheia."""

    DSA_PROBLEM = "dsa-problem"
    DSA_CONCEPT = "dsa-concept"
    SYSTEM_DESIGN = "system-design"
    MATH = "math"
    RESEARCH = "research"


class Maturity(StrEnum):
    """Card maturity states."""

    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    SUSPENDED = "suspended"


class PromptType(StrEnum):
    """Types of review prompts."""

    FACTUAL = "factual"
    REASONING = "reasoning"
    COMPARATIVE = "comparative"
    GENERATIVE = "generative"
    CODE = "code"
    BOUNDARY = "boundary"


class CreationMode(StrEnum):
    """How a card was created."""

    MANUAL = "manual"
    GUIDED_EXTRACTION = "guided-extraction"
    QUALITY_FEEDBACK = "quality-feedback"
    DRAFT_CRITIQUE = "draft-critique"


class LinkType(StrEnum):
    """Types of relationships between cards."""

    SIMILAR_TO = "similar_to"
    PREREQUISITE = "prerequisite"
    LEADS_TO = "leads_to"
    APPLIES = "applies"
    CONTRASTS_WITH = "contrasts_with"
    ENCOMPASSES = "encompasses"


class ReviewPrompt(BaseModel):
    """A review prompt for a card."""

    type: PromptType
    prompt: str
    answer_hint: str | None = None


class Source(BaseModel):
    """Source metadata for where knowledge came from."""

    type: str  # "leetcode", "book", "paper", "blog", "textbook", etc.
    title: str | None = None
    url: str | None = None
    chapter: str | None = None
    page: int | None = None

    # Platform-specific fields
    platform: str | None = None  # e.g., "leetcode", "arxiv"
    platform_id: str | None = None  # e.g., "42", "1706.03762"


class LeetcodeSource(Source):
    """Source for Leetcode problems."""

    type: str = "leetcode"
    platform: str = "leetcode"
    difficulty: str | None = None  # "easy", "medium", "hard"
    language: str | None = None  # "python3", "java", "cpp", etc.
    internal_question_id: str | None = None  # cached internal questionId


class Complexity(BaseModel):
    """Time and space complexity."""

    time: str
    space: str


class WeightedLink(BaseModel):
    """A weighted link to another card (used for encompasses relationships)."""

    card_id: str
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class CardLinks(BaseModel):
    """Links to related cards."""

    similar_to: list[str] = Field(default_factory=list)
    prerequisite: list[str] = Field(default_factory=list)
    leads_to: list[str] = Field(default_factory=list)
    applies: list[str] = Field(default_factory=list)
    contrasts_with: list[str] = Field(default_factory=list)
    encompasses: list[WeightedLink] = Field(default_factory=list)


class CardLifecycle(BaseModel):
    """Lifecycle metadata for a card."""

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    edit_count: int = 0
    reformulated_from: str | None = None
    split_from: str | None = None
    merged_from: list[str] = Field(default_factory=list)
    suspended_at: datetime | None = None
    exhausted_at: datetime | None = None
    exhausted_reason: str | None = None


class Card(BaseModel):
    """Base card model with common fields."""

    id: Annotated[str, Field(default_factory=lambda: str(uuid4()))]
    type: CardType
    front: str
    back: str

    # Organization
    taxonomy: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    links: CardLinks = Field(default_factory=CardLinks)

    # Sources
    sources: list[Source] = Field(default_factory=list)

    # Metadata
    maturity: Maturity = Maturity.ACTIVE
    creation_mode: CreationMode = CreationMode.MANUAL
    lifecycle: CardLifecycle = Field(default_factory=CardLifecycle)

    # Review prompts (additional prompts beyond the main front/back)
    review_prompts: list[ReviewPrompt] = Field(default_factory=list)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.lifecycle.updated_at = utcnow()
        self.lifecycle.edit_count += 1


class DSAProblemSubtype(StrEnum):
    """Subtypes for DSA problem cards."""

    UNDERSTANDING = "understanding"  # default for existing cards
    IMPLEMENTATION = "implementation"  # code-focused review


class DSAProblemCard(Card):
    """Card for a specific DSA/Leetcode problem."""

    type: CardType = CardType.DSA_PROBLEM

    # Problem-specific fields
    card_subtype: DSAProblemSubtype = DSAProblemSubtype.UNDERSTANDING
    problem_source: LeetcodeSource | None = None
    patterns: list[str] = Field(default_factory=list)
    data_structures: list[str] = Field(default_factory=list)
    complexity: Complexity | None = None
    intuition: str | None = None
    edge_cases: list[str] = Field(default_factory=list)
    code_solution: str | None = None  # Path or inline code


class DSAConceptCard(Card):
    """Card for general DSA concepts (algorithms, data structures)."""

    type: CardType = CardType.DSA_CONCEPT

    # Concept-specific fields
    name: str
    definition: str | None = None
    intuition: str | None = None
    properties: list[str] = Field(default_factory=list)
    common_patterns: list[str] = Field(default_factory=list)
    when_to_use: str | None = None
    when_not_to_use: str | None = None
    complexity: Complexity | None = None
    code_template: str | None = None


class TradeOff(BaseModel):
    """A trade-off in system design."""

    dimension: str  # e.g., "consistency vs availability"
    explanation: str


class SystemDesignCard(Card):
    """Card for system design concepts."""

    type: CardType = CardType.SYSTEM_DESIGN

    # System design specific fields
    name: str
    definition: str | None = None
    how_it_works: str | None = None
    trade_offs: list[TradeOff] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    anti_patterns: list[str] = Field(default_factory=list)
    real_world_examples: list[str] = Field(default_factory=list)


class MathCardSubtype(StrEnum):
    """Subtypes for math cards (Nielsen-inspired)."""

    DEFINITION = "definition"
    INTUITION = "intuition"
    PROOF_STEP = "proof-step"
    BOUNDARY = "boundary"
    REPRESENTATION = "representation"
    APPLICATION = "application"


class MathCard(Card):
    """Card for mathematical concepts (Nielsen-inspired atomic cards)."""

    type: CardType = CardType.MATH

    # Math-specific fields
    cluster: str | None = None  # Groups related cards (e.g., "linear-independence")
    card_subtype: MathCardSubtype = MathCardSubtype.DEFINITION
    cluster_siblings: list[str] = Field(default_factory=list)
    last_reformulated: datetime | None = None


class ResearchCardSubtype(StrEnum):
    """Subtypes for research cards."""

    INSIGHT = "insight"
    METHOD = "method"
    RESULT = "result"
    LIMITATION = "limitation"
    COMPARISON = "comparison"


class ResearchCard(Card):
    """Card for research paper insights."""

    type: CardType = CardType.RESEARCH

    # Research-specific fields
    paper_source: str | None = None  # ID of the paper source record
    card_subtype: ResearchCardSubtype = ResearchCardSubtype.INSIGHT


class PaperSource(BaseModel):
    """Metadata for a research paper (not a reviewable card)."""

    id: Annotated[str, Field(default_factory=lambda: str(uuid4()))]
    title: str
    authors: list[str] = Field(default_factory=list)
    source: Source
    one_line_summary: str | None = None
    cards: list[str] = Field(default_factory=list)  # IDs of related cards
    taxonomy: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


# Type alias for any card type
AnyCard = DSAProblemCard | DSAConceptCard | SystemDesignCard | MathCard | ResearchCard


def card_from_dict(data: dict) -> AnyCard:
    """Create a card from a dictionary based on its type."""
    card_type = data.get("type")

    if card_type == CardType.DSA_PROBLEM or card_type == "dsa-problem":
        return DSAProblemCard.model_validate(data)
    elif card_type == CardType.DSA_CONCEPT or card_type == "dsa-concept":
        return DSAConceptCard.model_validate(data)
    elif card_type == CardType.SYSTEM_DESIGN or card_type == "system-design":
        return SystemDesignCard.model_validate(data)
    elif card_type == CardType.MATH or card_type == "math":
        return MathCard.model_validate(data)
    elif card_type == CardType.RESEARCH or card_type == "research":
        return ResearchCard.model_validate(data)
    else:
        raise ValueError(f"Unknown card type: {card_type}")
