# Aletheia - Product Vision & Requirements

> **Aletheia** (Greek: ἀλήθεια) - "truth" or "disclosure"; the state of not being hidden.

## Overview

A personal knowledge management system designed for deep technical learning, focused on acquiring, crystallizing, indexing, and retaining knowledge across technical domains.

**Key Insight**: This is NOT a traditional flashcard/rote memorization system. The domains are conceptual and understanding-heavy. The system must support *understanding retention* rather than *fact memorization*.

---

## Problem Statement

Technical professionals need to:
1. Acquire deep knowledge across multiple complex domains
2. Retain that knowledge over time (combat the forgetting curve)
3. Prepare effectively for technical interviews
4. Connect disparate concepts to build intuition and solve novel problems

Current tools (Anki, Notion, Obsidian, etc.) solve pieces of this puzzle but don't provide an integrated experience for technical knowledge work. Traditional spaced repetition is optimized for memorization, not conceptual understanding.

---

## Decisions Made

### Scope
- **Primary user**: Personal tool (single user)
- **Future**: Open source if polished enough for others

### Platform & Interface
- **Content creation**: CLI with `$EDITOR` integration for frictionless input
- **Review**: Mobile-friendly web app (HTMX + Jinja2, server-rendered)
- **Storage**: Hybrid - JSON files for cards (git-tracked) + SQLite for reviews/stats

### Tech Stack (Finalized)
- **Backend**: Python 3.11+ (FastAPI, typer, pydantic, py-fsrs)
- **Frontend**: HTMX + Jinja2 + Tailwind CSS (server-rendered, minimal JS)
- **LLM**: litellm (supports Claude, GPT-4, Ollama, etc.)
- **LaTeX**: KaTeX (server-side rendering)
- **Storage**: JSON files + SQLite (hybrid approach)

### Hosting
- **Free options** (self-managed VM):
  - Oracle Cloud Free Tier (4 ARM cores, 24GB RAM - best specs)
  - GCP Compute Engine e2-micro (always free, most reliable)
  - AWS EC2 t2.micro (free for 12 months)
- **Cheap paid**: Hetzner VPS (~€4/mo, best reliability + specs)
- **Development**: Local with `aletheia serve`

### AI/LLM Integration
- Yes, but **human-in-the-loop** - LLM assists but user must understand
- Use cases: guided card extraction (Mode 1), quality feedback (Mode 4)
- Provider-agnostic via litellm

---

## Target Knowledge Domains

### Core Study Areas

| Area | Primary Sources | Knowledge Unit (TBD) |
|------|-----------------|---------------------|
| **DSA / Competitive Programming** | Leetcode problems, articles, books | Pattern? Problem? Technique? |
| **System Design** | Books, company tech blogs | Component? Trade-off? Case study? |
| **Mathematics** | Textbooks, websites/forums | Theorem? Concept? Proof technique? |
| **Research** | Arxiv papers, seminal books (e.g., DDIA) | Key insight? Method? Result? |

### Fields of Application
- Data Science / ML / AI
- Low-level Systems Programming / Infrastructure / Optimization
- Quantitative Finance

---

## Core Components

### Part 1: Knowledge Acquisition & Crystallization
- Capture knowledge from various sources
- Structure and index for retrieval
- Create connections between concepts
- Transform raw notes into "crystallized" understanding

### Part 2: Retention & Discovery
- Spaced repetition adapted for conceptual understanding (not rote learning)
- Link discovery to surface non-obvious connections
- Interview preparation workflows
- Skill progression tracking

### Existing Assets to Integrate
- Leetcode solutions repository (completed problems)
- Math textbook answers

---

## Knowledge Representation Design

### Core Principles (Decided)

1. **Topic-specific schemas**: Each knowledge domain has its own structure
2. **Atomic extraction**: Multiple cards/concepts per source
3. **Mixed review types**: Both factual recall AND active reasoning prompts
4. **Learning through creation**: Crafting prompts is part of the learning process
5. **Human-in-the-loop AI**: LLM assists but user validates understanding

### Review Prompt Types

| Type | Purpose | Example |
|------|---------|---------|
| **Factual** | Quick recall of definitions, properties | "What is the time complexity of heap insertion?" |
| **Reasoning** | Apply understanding, explain why | "Why is a monotonic stack useful for 'next greater element' problems?" |
| **Comparative** | Trade-offs, when to use what | "When would you choose a Trie over a HashMap for string problems?" |
| **Generative** | Produce solution/proof/design | "Design a rate limiter for an API" |
| **Code** | Write working code (with verification) | "Implement LRU Cache" - verified against test cases |

---

## Card Creation Assistance

### Design Philosophy

**Core tension**: Writing prompts creates understanding (Nielsen, Matuschak), but most people don't know how to write good prompts and find it onerous.

**Aletheia's approach**: LLM should make you *think harder*, not think less. Assist with structure and angles, not content generation.

### Card Creation Modes

The card creation system is designed as a **modular component** that can support multiple strategies. This allows experimentation and future improvements without changing the core data model.

#### Mode 1: Guided Extraction (MVP - Primary)

LLM asks Socratic questions → User articulates understanding → Questions become prompts

```
User: I just solved Leetcode 42 (Trapping Rain Water) using two pointers

System asks:
1. "What's the key insight that makes two-pointers work here?"
2. "Why can we use two pointers instead of precomputing both arrays?"
3. "What would break this approach?"
4. "What similar problems use this pattern?"

User answers each → Answers become card content
→ User reviews/edits generated cards before saving
```

**Why this works**:
- User must articulate understanding (learning happens here)
- LLM provides angles user might miss (boundary cases, connections)
- Structured extraction ensures coverage of important dimensions
- User still owns final content

#### Mode 4: Quality Feedback (MVP - Secondary)

LLM reviews user-written cards and teaches better prompt writing.

```
User writes: "Explain the two-pointer technique"

System feedback:
⚠️ Too vague - "explain" prompts produce inconsistent answers
⚠️ Not atomic - covers multiple variations

Suggestions:
→ "When would you use converging two-pointers vs. same-direction?"
→ Add specificity: "For Trapping Rain Water, why does two-pointers achieve O(1) space?"
```

**Why this works**:
- Teaches prompt-writing skills (compounds over time)
- Catches common mistakes (too broad, not atomic, binary yes/no)
- User learns Matuschak's principles through practice

#### Mode 2: Angle Suggester (Future)

User writes core content → LLM suggests unexplored angles (boundary cases, comparisons, connections)

#### Mode 3: Draft + Critique (Future - Use Carefully)

LLM generates draft cards → User must critically review and edit

**Safeguard**: Require minimum edit engagement to prevent passive acceptance.

### Domain-Specific Templates

Templates guide extraction with domain-appropriate questions:

**DSA Problem Template**:
| Question | Maps to Card Type |
|----------|-------------------|
| Pattern(s) used? | Tagging |
| Why does this pattern work here? | Reasoning |
| What's the non-obvious insight? | Reasoning |
| Edge cases that tripped you up? | Boundary |
| When would you NOT use this? | Comparative |
| Similar problems? | Links |

**System Design Template**:
| Question | Maps to Card Type |
|----------|-------------------|
| One-sentence definition? | Factual |
| When to use (signals)? | Reasoning |
| When NOT to use? | Comparative |
| Key trade-off? | Comparative |
| Real-world example? | Application |

**Math Template** (Nielsen-inspired):
| Question | Maps to Card Type |
|----------|-------------------|
| Formal definition? | Factual |
| Geometric/intuitive meaning? | Intuition |
| What breaks if we change assumption X? | Boundary |
| Key proof step? | Proof-step |
| Where is this applied? | Application |

### Architecture Note

The card creation system should be a **separate module** that:
- Takes user input + context (source material, domain)
- Produces candidate cards
- Can be swapped/configured without affecting storage or review systems
- Logs creation method for future analysis (which modes produce better retention?)

---

## Indexing & Discovery System

### Dual-Layer Approach (Decided)

1. **Hierarchical Taxonomy** - for navigation and organization
   ```
   domain > topic > subtopic

   Examples:
   - dsa > graphs > shortest-path > dijkstra
   - system-design > storage > replication > leader-follower
   - math > linear-algebra > vector-spaces > linear-independence
   - research > ml > transformers > attention-mechanism
   ```

2. **Flat Tags** - for cross-cutting concerns and discovery
   ```
   Examples:
   - #greedy, #dynamic-programming, #interview-classic
   - #trade-off, #cap-theorem, #consistency
   - #proof-by-contradiction, #optimization
   - #foundational, #cutting-edge
   ```

3. **Explicit Links** - for strong relationships between cards
   - `similar_to`: Problems/concepts that are variations of each other
   - `prerequisite`: Must understand X before Y
   - `applies`: Concept X is used in Problem Y
   - `contrasts_with`: Compare/contrast relationship

---

## Schemas by Topic

### DSA Schema (Two Card Types)

**Type 1: Problem Card** (tied to specific Leetcode/competitive programming problem)
```
Problem Card:
├── id: uuid
├── type: "problem"
├── source: { platform: "leetcode", id: "42", url: "...", title: "Trapping Rain Water" }
├── difficulty: "hard"
├── taxonomy: ["dsa", "arrays", "two-pointers"]
├── tags: ["#interview-classic", "#monotonic-stack", "#optimization"]
├── patterns_used: [link to Concept Cards]
├── data_structures: ["array", "stack"]
├── intuition: "Why does this pattern work here?"
├── approach: "Step-by-step solution approach"
├── edge_cases: ["empty array", "single element", "all same height"]
├── complexity: { time: "O(n)", space: "O(1)" }
├── links: {
│     similar_to: ["leetcode:11", "leetcode:84"],
│     applies: ["concept:monotonic-stack", "concept:two-pointers"]
│   }
├── code_solution: "link to code or inline"
└── review_prompts: [...]
```

**Type 2: Concept Card** (general algorithm/data structure knowledge)
```
Concept Card:
├── id: uuid
├── type: "concept"
├── source: { type: "book", title: "CLRS", chapter: "6" } // or multiple sources
├── name: "Monotonic Stack"
├── taxonomy: ["dsa", "data-structures", "stack-variants"]
├── tags: ["#technique", "#range-queries"]
├── definition: "A stack that maintains elements in sorted order"
├── intuition: "When/why to use this"
├── properties: ["O(n) amortized for n operations", "useful for next-greater-element patterns"]
├── common_patterns: ["next greater element", "largest rectangle in histogram"]
├── when_to_use: "Signals that suggest this approach"
├── when_not_to_use: "Common mistakes / wrong applications"
├── complexity: { typical_time: "O(n)", typical_space: "O(n)" }
├── links: {
│     prerequisite: ["concept:stack-basics"],
│     contrasts_with: ["concept:two-pointers"],
│     applied_in: ["leetcode:42", "leetcode:84", "leetcode:85"]
│   }
├── code_template: "Generic implementation"
└── review_prompts: [
      { type: "comparative", prompt: "When would you use monotonic stack vs two-pointers?" },
      { type: "reasoning", prompt: "Why does monotonic stack give O(n) for next-greater-element?" }
    ]
```

### System Design Schema (Concept-Level Granularity)

Each concept is its own card. Multiple sources can enrich the same concept.

```
System Design Card:
├── id: uuid
├── type: "system-design-concept"
├── name: "Leader-Follower Replication"
├── taxonomy: ["system-design", "storage", "replication"]
├── tags: ["#consistency", "#availability", "#interview-classic"]
├── sources: [
│     { type: "book", title: "DDIA", chapter: "5" },
│     { type: "blog", title: "How Postgres Replication Works", url: "..." }
│   ]
├── definition: "One node (leader) accepts writes; followers replicate asynchronously"
├── how_it_works: "Detailed explanation"
├── trade_offs: [
│     { dimension: "consistency vs latency", explanation: "..." },
│     { dimension: "read scalability vs write bottleneck", explanation: "..." }
│   ]
├── use_cases: ["read-heavy workloads", "single-region deployments"]
├── anti_patterns: ["write-heavy workloads", "multi-region with low latency requirements"]
├── real_world_examples: ["PostgreSQL streaming replication", "MySQL replication"]
├── links: {
│     prerequisite: ["concept:write-ahead-log"],
│     contrasts_with: ["concept:multi-leader", "concept:leaderless"],
│     related: ["concept:failover", "concept:replication-lag"]
│   }
└── review_prompts: [
      { type: "comparative", prompt: "When would you choose leader-follower vs leaderless?" },
      { type: "generative", prompt: "Design replication strategy for a banking application" },
      { type: "reasoning", prompt: "Why can't leader-follower provide strong consistency with async replication?" }
    ]
```

### Mathematics Schema (Nielsen-Inspired Approach)

**Philosophy** (from [Michael Nielsen's SRS for Mathematics](https://cognitivemedium.com/srs-mathematics)):
- **Grazing**: Extract proof elements into interconnected atomic cards, not linear steps
- **Multiple representations**: Same concept from algebraic, geometric, intuitive angles
- **Boundary-pushing**: "What if this assumption changed?" - tests real understanding
- **Exhaust cleanup**: Cards become obsolete as understanding deepens - reformulate or discard
- **Chunking over memorization**: Build mental libraries for intuition, not symbol recall

**Card Philosophy**: Rather than one big "Linear Independence" card, create a *cluster* of atomic cards that explore the concept from different angles.

```
Math Card (Atomic):
├── id: uuid
├── type: "math-card"
├── cluster: "linear-independence"  // groups related cards
├── card_subtype: "definition" | "intuition" | "proof-step" | "boundary" | "representation" | "application"
├── taxonomy: ["math", "linear-algebra", "vector-spaces"]
├── tags: ["#foundational"]
├── sources: [{ type: "textbook", title: "Linear Algebra Done Right", chapter: "3" }]
├── front: "Question/prompt (LaTeX supported)"
├── back: "Minimal answer - core idea as sharply as possible"
├── links: {
│     cluster_siblings: ["card:li-definition", "card:li-geometric", "card:li-boundary-1"],
│     prerequisite: ["cluster:vector-spaces"],
│     leads_to: ["cluster:basis"],
│     applied_in: ["cluster:pca"]
│   }
├── maturity: "active" | "exhausted"  // mark obsolete cards
└── last_reformulated: timestamp  // track when card was refined
```

**Example Card Cluster for "Linear Independence":**

| Card | Subtype | Front | Back |
|------|---------|-------|------|
| li-def | definition | "Define linear independence for vectors v₁...vₙ" | "Only solution to c₁v₁+...+cₙvₙ=0 is all cᵢ=0" |
| li-geo | intuition | "Geometrically, what does linear independence mean for 2 vectors in R²?" | "Neither vector lies on the line spanned by the other" |
| li-boundary-1 | boundary | "If {v₁,v₂} is independent, what happens when we add 0?" | "Becomes dependent: 1·0 + 0·v₁ + 0·v₂ = 0" |
| li-boundary-2 | boundary | "If v₃ = 2v₁ + v₂, is {v₁,v₂,v₃} independent? Why?" | "No: 2v₁ + v₂ - v₃ = 0 with non-zero coefficients" |
| li-proof-step | proof-step | "Key step: proving max independent set in Rⁿ has n vectors" | "Induction on dimension; removing one vector from independent set..." |
| li-application | application | "How does linear independence relate to matrix invertibility?" | "Columns independent ⟺ only solution to Ax=0 is x=0 ⟺ A invertible" |

### Research Schema (Atomic Cards per Paper)

**Philosophy**: Extract 3-7 atomic insight cards per paper. Each card captures ONE key idea worth remembering. The paper itself is a "source" that links to multiple cards.

```
Paper Source (metadata only, not a reviewable card):
├── id: uuid
├── type: "paper-source"
├── title: "Attention Is All You Need"
├── authors: ["Vaswani et al."]
├── source: { type: "arxiv", id: "1706.03762", url: "...", year: 2017 }
├── one_line_summary: "Introduces transformer architecture using only attention"
├── cards: ["transformer-insight-1", "transformer-insight-2", ...]  // linked atomic cards
└── taxonomy: ["research", "ml", "nlp"]  // for filtering/browsing
```

```
Research Insight Card (atomic, reviewable):
├── id: uuid
├── type: "research-card"
├── paper_source: "paper:attention-is-all-you-need"
├── taxonomy: ["research", "ml", "architectures", "attention"]
├── tags: ["#foundational", "#complexity-analysis"]
├── card_subtype: "insight" | "method" | "result" | "limitation" | "comparison"
├── front: "Why is self-attention O(n²) in sequence length?"
├── back: "Each position attends to all n positions → n×n attention matrix"
├── links: {
│     related_insights: ["card:rnn-sequential-bottleneck"],
│     builds_on: ["concept:attention-mechanism"],
│     prerequisite: ["concept:matrix-multiplication-complexity"]
│   }
└── maturity: "active" | "exhausted"
```

**Example Cards from "Attention Is All You Need":**

| Card | Subtype | Front | Back |
|------|---------|-------|------|
| transformer-1 | insight | "What problem with RNNs do transformers solve?" | "Sequential computation bottleneck - can't parallelize across time steps" |
| transformer-2 | method | "How do transformers preserve sequence order without recurrence?" | "Positional encodings (sinusoidal or learned) added to embeddings" |
| transformer-3 | insight | "Why use multi-head attention instead of single attention?" | "Different heads learn different relationship types (syntax, semantics, etc.)" |
| transformer-4 | limitation | "What's the main computational limitation of transformers?" | "O(n²) attention - struggles with very long sequences" |

---

## Open Questions

### Resolved ✓

1. ~~**DSA granularity**~~ → Two card types: Problem Cards + Concept Cards
2. ~~**System Design granularity**~~ → Concept-level (one card per concept, multiple sources can enrich)
3. ~~**Tagging approach**~~ → Both: Hierarchical taxonomy + flat tags + explicit links
4. ~~**Math proofs**~~ → Nielsen-inspired approach: atomic card clusters exploring proof from multiple angles (definition, intuition, boundary cases, proof steps)
5. ~~**Research papers**~~ → Multiple atomic cards per paper (3-7 insights); paper itself is a source record linking to cards
6. ~~**LaTeX support**~~ → Critical for Math, but can defer if needed; choose frontend with LaTeX in mind

### MVP Priority (Decided)

**Order of implementation**: DSA → System Design → Math → Research

7. ~~**Storage format**~~ → JSON files (simple, human-readable, git-friendly). LaTeX stored as raw strings, rendered by frontend.
8. ~~**Sync mechanism**~~ → Manual git (user runs git push/pull)
9. ~~**SRS algorithm**~~ → FSRS with default parameters (outperforms SM-2, ~100 lines core). Store all review logs from day one for future optimizer training.

### Future Enhancements (Post-MVP)

- **FSRS Optimizer**: Train personalized parameters once we have 1,000+ reviews
- **Interleaved Practice**: Mix cards across topics to strengthen connections (research suggests better transfer)
- **Mnemonic Medium**: Embed prompts in narrative context (Andy Matuschak's approach)

### Leetcode Integration (Implemented)

**Research findings**: No official Leetcode API exists, but undocumented GraphQL endpoints are available. The `python-leetcode` package wraps these APIs. Requires session cookies for authentication.

**Implementation**: Direct GraphQL calls via `python-leetcode` library. CLI commands:
- `aletheia leetcode login` — browser cookie extraction (via `rookiepy`) with manual paste fallback
- `aletheia leetcode status` — check login status and session validity
- `aletheia leetcode set-solution <card-id>` — editor auto-fetches problem description + starter code from LeetCode API; or set from file with `--file`
- `aletheia leetcode submit <card-id>` — test-first safety check + full submission

**Risks**: Undocumented APIs may break without notice. Personal use with rate limiting is low risk.

---

## MVP Scope (Draft)

### MVP Goal
A working end-to-end flow for DSA and System Design knowledge capture and review.

### In Scope (MVP)

**Content Creation**
- [ ] CLI or local file-based card creation (low friction)
- [ ] DSA Problem Cards + Concept Cards
- [ ] System Design Concept Cards
- [ ] Manual linking between cards (similar_to, prerequisite, etc.)
- [ ] Taxonomy + tag assignment
- [ ] LLM-assisted card creation and refinement:
  - [ ] Mode 1: Guided Extraction (Socratic questions → user articulates → cards generated)
  - [ ] Mode 1b: Guided Edit (Socratic questions about the *delta* → refine existing cards)
  - [ ] Mode 4: Quality Feedback (review user-written cards, suggest improvements)

**Review System**
- [ ] Mobile-friendly web interface for review
- [ ] FSRS algorithm with default parameters
- [ ] Store all review logs (for future optimizer)
- [ ] Mixed prompt types: factual, reasoning, comparative
- [ ] Self-assessment after each card (Again, Hard, Good, Easy)

**Storage & Sync**
- [ ] JSON files for cards (git-tracked, human-readable)
- [ ] SQLite for reviews, FSRS state, search index (local operational data)
- [ ] LaTeX as raw strings (rendered server-side via KaTeX)
- [ ] Manual git sync (user manages push/pull)

**Card Lifecycle**
- [ ] Edit cards via CLI (`$EDITOR` integration)
- [ ] LLM-guided card editing via CLI (`aletheia edit <id> --guided`)
- [ ] Edit cards during review (inline web form)
- [ ] Mark cards as exhausted (understanding deepened)
- [ ] Suspend/resume cards

### Out of Scope (Post-MVP)

- Math card clusters (requires LaTeX rendering polish)
- Research paper cards
- LLM-assisted link discovery (automatic connection suggestions)
- Card creation Mode 2 (Angle Suggester) and Mode 3 (Draft + Critique)
- Card split/merge operations (advanced lifecycle)
- Automatic GitHub sync
- Interview preparation mode / study plans
- Progress analytics and visualizations
- Multi-device real-time sync
- Interleaved practice scheduling
- FSRS optimizer (requires 1,000+ reviews)

### MVP Success Criteria

1. Can create a DSA Problem Card in < 2 minutes
2. Can review cards on mobile browser
3. Cards resurface at appropriate intervals (basic SRS working)
4. Can find related cards via links and tags

---

## Success Metrics (Draft)

1. **Retention**: % of reviewed concepts retained over 6+ months
2. **Coverage**: % of target domains with crystallized knowledge
3. **Interview Readiness**: Confidence/performance in mock interviews
4. **Connection Density**: Links discovered between concepts across domains

---

## Next Steps

1. ~~Answer initial scoping questions~~ ✓
2. ~~Define knowledge representation~~ ✓ (schemas drafted)
3. ~~Finalize technical decisions~~ ✓ (storage: JSON+SQLite, sync: manual git, SRS: FSRS)
4. ~~Define MVP scope~~ ✓
5. ~~Design technical architecture~~ ✓ (see `docs/technical-architecture.md`)
   - Directory structure
   - JSON schema definitions
   - Tech stack: Python + FastAPI + HTMX + Jinja2
   - API design, CLI commands, card lifecycle
   - Hosting: Koyeb free tier
6. **Build MVP**
   - Phase 1: Core foundation (models, storage, basic CLI) ✓
   - Phase 2: Review system (FSRS, web UI, KaTeX) ✓
   - Phase 3: LLM integration (litellm, Mode 1 & 4) ✓
   - Phase 4a: Card lifecycle (suspend, resume, exhaust, reformulate, split, merge) ← Next
   - Phase 4b: Search (SQLite FTS5)
   - Phase 4c: Statistics dashboard
   - Phase 4d: Polish (mobile responsive, git sync)

---

## References & Inspirations

### Spaced Repetition Theory

| Source | Key Insight | How It Influenced Aletheia |
|--------|-------------|---------------------------|
| [Michael Nielsen - Using SRS for Mathematics](https://cognitivemedium.com/srs-mathematics) | "Grazing" approach: atomic cards exploring concepts from multiple angles; cards become "exhausted" as understanding deepens | Math schema uses card clusters with multiple representations; added `maturity` field to mark obsolete cards |
| [Michael Nielsen - Augmenting Long-term Memory](http://augmentingcognition.com/ltm.html) | Atomic cards, understanding over memorization, making memory a choice | Core principle: atomic extraction, mixed review types |
| [Andy Matuschak - Spaced Repetition Memory System](https://notes.andymatuschak.org/Spaced_repetition_memory_system) | Traditional SRS is "too atomized"; prompts should "connect and relate ideas"; SRS as "programmable attention" not memory drilling | Emphasis on relational prompts (comparative, reasoning types); explicit links between cards |
| [Andy Matuschak - Mnemonic Medium](https://notes.andymatuschak.org/Mnemonic_medium) | Embed prompts in narrative context; expert-authored prompts remove learner burden | Future enhancement: embed cards in study notes/explanations |
| [Andy Matuschak - How to Write Good Prompts](https://andymatuschak.org/prompts/) | Prompts should be focused, precise, consistent, tractable, effortful; writing prompts creates understanding | Card creation modes; quality feedback system; domain templates |

**Key Matuschak insights for Aletheia:**
- Prompts should test "connections, implications, causes, consequences" - not isolated facts
- SRS can develop conceptual understanding, but requires deliberate prompt design
- "Memory systems help you focus on deeper engagement by automating away rote memorization"
- Reframe as helping future self engage repeatedly with important ideas

### Knowledge Management

| Source | Key Insight | How It Influenced Aletheia |
|--------|-------------|---------------------------|
| Zettelkasten method | Atomic notes with explicit links enable emergent understanding | Dual-layer indexing: taxonomy + tags + explicit links |
| Andy Matuschak's Evergreen Notes | Notes should be concept-oriented, densely linked | Concept-level granularity for System Design |

### Technical Learning

| Source | Key Insight | How It Influenced Aletheia |
|--------|-------------|---------------------------|
| Designing Data-Intensive Applications (Kleppmann) | Trade-off thinking: every design choice has consequences | System Design schema emphasizes trade_offs, use_cases, anti_patterns |
| Leetcode patterns literature | Problems cluster around reusable patterns | DSA schema separates Problem Cards from Concept Cards |

### SRS Algorithms

| Source | Key Insight | How It Influenced Aletheia |
|--------|-------------|---------------------------|
| [FSRS (Free Spaced Repetition Scheduler)](https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm) | Modern algorithm based on DSR memory model; 20-30% fewer reviews than SM-2; default parameters work well | Using FSRS with defaults for MVP; storing review logs for future optimization |
| [FSRS Implementation Guide](https://borretti.me/article/implementing-fsrs-in-100-lines) | Core scheduler is ~100 lines; complexity is in optimizer, not scheduler | Confidence that FSRS is feasible for MVP |

### To Explore

- [ ] Piotr Wozniak's SuperMemo research on optimal spacing algorithms
- [ ] Barbara Oakley's "Learning How to Learn" - chunking and interleaving
- [ ] Make It Stick (Brown et al.) - retrieval practice research
- [ ] Interleaved practice research - mixing topics for better transfer
- [ ] Desirable difficulties (Robert Bjork) - productive struggle in learning
