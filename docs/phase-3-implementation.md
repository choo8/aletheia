# Phase 3: LLM Integration - Implementation Plan

## Overview

Implement LLM-assisted card creation and refinement with three capabilities:
- **Mode 1 (Guided Extraction)**: Socratic questioning to help users articulate understanding when creating new cards
- **Mode 1b (Guided Edit)**: Socratic questioning focused on the *delta* when refining existing cards
- **Mode 4 (Quality Feedback)**: Review card quality and teach prompt-writing skills

Uses `litellm` for provider-agnostic LLM access (Claude, GPT-4, Ollama, etc.).

## Key Design Principles

1. **Socratic, not Generative** - LLM asks questions that help user think, not generate content
2. **Human-in-the-loop** - User validates and edits all LLM-assisted content
3. **Learning through Creation** - Crafting prompts IS the learning process
4. **Domain-specific Templates** - Different question templates for DSA, System Design, Math

---

## Implementation Order

### Step 1: LLM Service Module

**File:** `src/aletheia/llm/service.py` (NEW)

litellm wrapper with core methods:

```python
class LLMService:
    def __init__(self, model: str = "claude-sonnet-4-20250514")
    async def guided_extraction(self, context: str, domain: str) -> list[str]
    async def guided_edit_extraction(self, existing_card_content: str, new_context: str, domain: str) -> list[str]
    async def quality_feedback(self, card: Card) -> QualityFeedback
```

Features:
- Configurable model via environment variable `ALETHEIA_LLM_MODEL`
- API key via `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
- Sync wrappers for CLI usage
- Error handling with graceful fallback messages

### Step 2: System Prompts

**File:** `src/aletheia/llm/prompts.py` (NEW)

Three main prompts:
- `EXTRACTION_SYSTEM_PROMPT` - Generates Socratic questions for new card creation
- `EDIT_EXTRACTION_SYSTEM_PROMPT` - Generates Socratic questions focused on the delta when refining existing cards
- `QUALITY_SYSTEM_PROMPT` - Reviews card quality against Matuschak's principles

Domain-specific question templates embedded in extraction prompt.

### Step 3: CLI Integration

**File:** `src/aletheia/cli/main.py` (MODIFY)

Add `--guided` flag to `add` command:

```bash
aletheia add dsa-problem --guided    # Mode 1: LLM asks Socratic questions
aletheia add dsa-problem             # Default: manual entry (unchanged)
```

Add `--guided` flag to `edit` command:

```bash
aletheia edit <card-id> --guided     # Mode 1b: LLM asks Socratic questions about the delta
aletheia edit <card-id>              # Default: open in $EDITOR (unchanged)
```

Add new `check` command:

```bash
aletheia check <card-id>             # Mode 4: Get quality feedback
aletheia check --all                 # Check all cards
```

### Step 4: Tests

**File:** `tests/test_llm.py` (NEW)

- Test prompt generation
- Test quality feedback parsing
- Mock LLM responses for deterministic tests

---

## Files Summary

### Files to Create

| File | Purpose |
|------|---------|
| `src/aletheia/llm/service.py` | LLM service with litellm |
| `src/aletheia/llm/prompts.py` | System prompts for both modes |
| `tests/test_llm.py` | LLM module tests |

### Files to Modify

| File | Changes |
|------|---------|
| `src/aletheia/llm/__init__.py` | Export LLMService |
| `src/aletheia/cli/main.py` | Add `--guided` flag to `add` and `edit`, add `check` command |
| `pyproject.toml` | Ensure `litellm` in `[llm]` extras |

---

## Mode 1: Guided Extraction Flow

```
User: aletheia add dsa-problem --guided

1. Prompt: "Describe what you learned (problem, solution, insight):"
   User: "Solved Leetcode 42 Trapping Rain Water with two pointers"

2. LLM generates Socratic questions based on domain template:
   - "What's the key insight that makes two-pointers work here?"
   - "What invariant do the pointers maintain?"
   - "What would break this approach?"
   - "What similar problems use this pattern?"

3. User answers each question interactively

4. Answers structured into card fields:
   - front: Generated from key insight question
   - back: Combined from answers
   - intuition: From "why it works" answer
   - patterns: Extracted from context

5. User reviews/edits in $EDITOR

6. Card saved with creation_mode=GUIDED_EXTRACTION
```

---

## Mode 1b: Guided Edit Flow

```
User: aletheia edit abc123 --guided

1. Display existing card content

2. Prompt: "Describe what changed in your understanding:"
   User: "Realized the two-pointer approach also handles negative heights"

3. LLM compares existing card with new context, generates delta-focused questions:
   - "How does this new insight change the edge cases you originally identified?"
   - "Does this affect the invariant the pointers maintain?"
   - "Should the intuition field be updated to reflect this?"
   - "Are there new related problems this connects to?"

4. User answers each question interactively

5. Answers + existing card fields opened in $EDITOR for fine-tuning
   (Q&A summary included as reference material via _guided_qa_reference key)

6. User confirms save → card updated (lifecycle.edit_count incremented via touch())
```

**Key differences from Mode 1:**
- LLM sees existing card content alongside new context
- Questions probe the *delta* in understanding, not create from scratch
- Editor step is always shown (mapping from Q&A to field updates is ambiguous)
- `creation_mode` is not changed (records how card was *created*, not last edited)

---

## Mode 4: Quality Feedback Flow

```
User: aletheia check abc123

1. Load card content

2. LLM analyzes against quality criteria:
   - Specificity (not too vague)
   - Atomicity (single concept)
   - Question type (not binary yes/no)
   - Tractability (can be answered consistently)

3. Output structured feedback:
   ✓ Good: Specific problem context
   ⚠ Issue: Question is too broad ("explain X")
   → Suggestion: "What invariant do two-pointers maintain in Trapping Rain Water?"

4. User can edit card based on feedback
```

---

## Domain-Specific Question Templates

### DSA Problems
- What's the key insight/invariant?
- Why does this approach work (not just how)?
- What edge cases did you consider?
- When would this approach NOT work?
- What similar problems use this pattern?

### DSA Concepts
- One-sentence definition?
- When to recognize/use this?
- Common mistakes or gotchas?
- How does it relate to X? (connections)

### System Design
- What problem does this solve?
- What are the trade-offs?
- When would you NOT use this?
- Real-world examples?

---

## Quality Feedback Criteria

Based on Andy Matuschak's principles:

1. **Focused** - Single concept, not multiple ideas
2. **Precise** - Specific enough to have one answer
3. **Consistent** - Same answer every time
4. **Tractable** - Can be answered with reasonable effort
5. **Effortful** - Requires recall, not recognition
6. **Connected** - Tests relationships, not isolated facts

---

## Dependencies

Already in `pyproject.toml`:

```toml
[project.optional-dependencies]
llm = ["litellm>=1.0"]
```

Environment variables:
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` - API key for LLM provider
- `ALETHEIA_LLM_MODEL` - Override default model (optional)

---

## Verification

### Mode 1 (Guided Extraction)

```bash
export ANTHROPIC_API_KEY=sk-...
aletheia add dsa-problem --guided
# Should prompt for context, then ask Socratic questions
# Answers should be structured into card
```

### Mode 1b (Guided Edit)

```bash
export ANTHROPIC_API_KEY=sk-...
aletheia edit <card-id> --guided
# Should display existing card, prompt for new context
# LLM asks delta-focused Socratic questions
# Answers + existing fields opened in $EDITOR for fine-tuning
```

### Mode 4 (Quality Feedback)

```bash
aletheia check <card-id>
# Should show quality analysis with suggestions
```

### Tests

```bash
pytest tests/test_llm.py -v
```

---

## Scope Notes

- Web UI for LLM features deferred to Phase 4 (CLI-first for MVP)
- Math and Research card templates can be added later
- FSRS optimizer integration (using review logs) deferred to future phase

---

## Future Enhancements

### Conversational Follow-up (Multi-turn)

Currently each Socratic question is a single prompt-response. A richer flow would
let the user converse with the LLM per question — asking for clarification,
refining their answer, or exploring a tangent — before moving on.

Design sketch:
- After each answer the LLM can reply with a follow-up or accept the answer.
- A `/next` or empty Enter advances to the next question.
- Conversation history for that question is included when structuring the card.

### Atomic Card Generation

Today, guided extraction stuffs all follow-up Q&A answers into a single card's
`intuition` field. A better approach would produce multiple linked cards — one
per distinct insight — rather than a single overloaded card.

Design sketch:
- After the Q&A loop, the LLM proposes N atomic card drafts (each with its own
  front/back).
- Cards are linked via `links.similar_to` or a new `cluster` field.
- The user reviews and edits each draft before saving.
