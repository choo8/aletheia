# Phase 6: Knowledge Graph, Smart Scheduling & FIRe - Implementation

## Overview

Implements Math Academy-inspired features for mastery-based learning: a knowledge graph with prerequisite tracking and encompasses relationships, smart scheduling with prerequisite-aware queue building, FIRe (Fractional Implicit Repetition) for credit propagation, response time tracking, LLM-guided link management, and implementation cards with failure classification.

**Inspiration**: [The Math Academy Way](https://www.justinmath.com/the-math-academy-way/) — mastery-based learning with knowledge graphs, prerequisite enforcement, and implicit review credit.

---

## Architecture

### New Core Modules

| Module | File | Purpose |
|--------|------|---------|
| `KnowledgeGraph` | `src/aletheia/core/graph.py` | Query layer over card links: prerequisite traversal, knowledge frontier, encompasses lookup, graph statistics |
| `QueueBuilder` | `src/aletheia/core/queue.py` | Smart review queue: prerequisite filtering, non-interference spacing, taxonomy interleaving, FIRe set-cover |
| `FIReEngine` | `src/aletheia/core/fire.py` | Fractional Implicit Repetition: credit/penalty propagation through encompasses links, covering set optimization |
| `ProgressMetrics` | `src/aletheia/core/metrics.py` | Mastery percentage, learning velocity, automaticity candidates |

### New CLI Modules

| Module | File | Purpose |
|--------|------|---------|
| `links_app` | `src/aletheia/cli/links.py` | Link management subcommands: show, add, remove, suggest, health |
| `graph_app` | in `src/aletheia/cli/main.py` | Graph subcommands: frontier, prereqs, stats |

### Modified Modules

| Module | Changes |
|--------|---------|
| `models.py` | `WeightedLink`, `encompasses` field on `CardLinks`, `ENCOMPASSES` LinkType, `DSAProblemSubtype` enum, `card_subtype` on `DSAProblemCard` |
| `storage.py` | `implicit_credit` table, `response_time_ms` column, `log_implicit_credit()`, `get_implicit_credit_since()`, `get_response_times()`, `get_automaticity_report()` |
| `scheduler.py` | `remediation_ids` on `ReviewResult`, `response_time_ms` parameter, `get_remediation_cards()` |
| `dependencies.py` | `get_graph()`, `get_queue_builder()` providers |
| `review.py` (web) | QueueBuilder integration, `reveal_ts` for response time tracking |
| `main.py` | QueueBuilder + FIReEngine in review loop, graph/links subcommands, extended stats |
| `leetcode.py` | `review-submit` command with failure classification and FIRe propagation |
| `service.py` (llm) | `classify_failure()`, `suggest_links()` methods |
| `prompts.py` | `LINK_SUGGESTION_SYSTEM_PROMPT` |

---

## Key Concepts

### Knowledge Graph

The knowledge graph is a query layer over the existing card link data (stored in JSON files). It provides:

- **Transitive prerequisites**: BFS traversal of `prerequisite` links with cycle detection
- **Knowledge frontier**: Cards whose prerequisites are all mastered (stability > threshold) but that are themselves unmastered or new
- **Encompasses relationships**: Weighted links (`WeightedLink`) where reviewing card A implicitly covers a fraction of card B
- **Reverse lookups**: Find all cards that depend on or encompass a given card
- **Graph statistics**: Total nodes/edges, orphan count, max prerequisite depth

### Smart Scheduling (QueueBuilder)

The `QueueBuilder` transforms a raw list of due card IDs into an optimized review queue:

1. **Prerequisite filtering**: Only include cards whose prerequisites are mastered
2. **Non-interference spacing**: Separate similar/contrasting cards to maximize distance between them. Uses a greedy insertion algorithm: process non-conflicting items first, then insert conflicting items into the position that maximizes minimum distance from other conflicting items
3. **Taxonomy interleaving**: Round-robin across taxonomy branches (e.g., alternate between DSA and System Design cards)
4. **FIRe covering set** (optional): If FIReEngine is provided, reduce the queue by identifying encompassing cards that implicitly cover multiple due cards

### FIRe Engine (Fractional Implicit Repetition)

When a user reviews a card that encompasses other cards, those encompassed cards receive fractional review credit:

- **Credit propagation**: Multi-level transitive with multiplicative weight decay. Rating factors: AGAIN=0.0, HARD=0.4, GOOD=0.8, EASY=1.0
- **Penalty propagation**: On AGAIN rating, encompassing cards are flagged (reverse direction)
- **Covering set**: Greedy set-cover algorithm identifies cards whose review would implicitly cover the most due cards, reducing queue size
- **Implicit extension**: Cards with sufficient accumulated credit get their due dates extended

### Response Time Tracking

- `response_time_ms` is recorded from card reveal to rating submission (both CLI and web)
- `ProgressMetrics.automaticity_candidates()` identifies cards with consistently fast response times (suggesting automaticity/fluency)
- Learning velocity tracks cards mastered per week

### Implementation Cards & Failure Classification

DSA problem cards now support a `card_subtype` field:
- `understanding` — Tests conceptual understanding
- `implementation` — Tests coding ability

On LeetCode submission failure, the LLM classifies the failure:
- `conceptual` — Wrong approach entirely
- `technique` — Right approach, wrong technique/detail
- `mechanical` — Right approach, coding bug
- `trivial` — Typo or syntax error

Each failure type maps to differentiated understanding/implementation ratings.

---

## Database Schema Changes

### New table: `implicit_credit`

```sql
CREATE TABLE implicit_credit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT NOT NULL,
    source_card_id TEXT NOT NULL,
    credit REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
```

### Modified table: `review_logs`

```sql
ALTER TABLE review_logs ADD COLUMN response_time_ms INTEGER
```

---

## CLI Commands

### Graph Subcommands

```bash
aletheia graph frontier            # Cards ready to learn (prereqs mastered)
aletheia graph prereqs <card-id>   # Full prerequisite chain
aletheia graph stats               # Node/edge counts, orphans, max depth
```

### Link Management Subcommands

```bash
aletheia links show <card-id>      # All links (outgoing + reverse)
aletheia links add <src> <dst> <type>          # Add a link
aletheia links add <src> <dst> encompasses -w 0.8  # Weighted encompasses
aletheia links remove <src> <dst> <type>       # Remove a link
aletheia links suggest <card-id>   # LLM-powered suggestions (interactive review)
aletheia links health              # Orphans, broken links, self-cycles
```

### LeetCode Review-Submit

```bash
aletheia leetcode review-submit <card-id>  # Show → edit → submit → auto-rate + classify
```

---

## Test Coverage

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_graph.py` | 22 | KnowledgeGraph: prereqs, frontier, encompasses, stats, cycles |
| `test_queue.py` | 10 | QueueBuilder: prereq filtering, non-interference, interleaving |
| `test_fire.py` | 14 | FIReEngine: credit/penalty propagation, covering set, implicit extension |
| `test_metrics.py` | 13 | ProgressMetrics: mastery, velocity, automaticity, schema migration |
| `test_links.py` | 11 | Links CLI: show, add, remove, health, encompasses operations |
| `test_implementation_cards.py` | 10 | DSAProblemSubtype, failure classification, review-submit flow |
| **Total** | **80** | All passing (343 total across project) |

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Knowledge graph is a query layer, not a separate store | Card links already live in JSON files; graph.py provides traversal without data duplication |
| Non-interference uses greedy insertion, not optimal | Optimal spacing is NP-hard; greedy gives good-enough results for typical queue sizes (< 50 cards) |
| FIRe credit is stored in SQLite, not on the card | Credit is transient operational data (like FSRS state), not part of the card's content |
| Encompasses weight is 0.0–1.0 | Represents fraction of the encompassed card that is implicitly reviewed; 1.0 = full coverage |
| Response time is optional (nullable column) | Backward compatible with existing review logs; only populated for new reviews |
| DSAProblemSubtype defaults to None | Backward compatible; existing cards don't need subtypes unless explicitly classified |
