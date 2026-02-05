# Aletheia - Technical Architecture

## Overview

This document describes the technical architecture for Aletheia, a personal knowledge management and spaced repetition system.

**Key Constraints:**
- Local-first with manual git sync
- JSON file storage (cards) + SQLite (reviews, state)
- Mobile-friendly web interface for review
- FSRS algorithm with default parameters
- LLM-assisted card creation (Modes 1 & 4)
- LaTeX rendering (server-side KaTeX)
- Free/cheap hosting (Oracle Cloud, GCP, AWS, or Hetzner)

---

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        Aletheia System                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │    CLI /     │    │   Card       │    │    LLM       │      │
│  │   Editor     │───▶│  Creation    │◀──▶│   Service    │      │
│  │  Interface   │    │   Module     │    │  (Optional)  │      │
│  └──────────────┘    └──────┬───────┘    └──────────────┘      │
│                             │                                   │
│                             ▼                                   │
│  ┌──────────────────────────────────────────────────────┐      │
│  │                    Core Library                       │      │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐      │      │
│  │  │   Card     │  │   FSRS     │  │   Index    │      │      │
│  │  │  Storage   │  │  Scheduler │  │  & Search  │      │      │
│  │  └────────────┘  └────────────┘  └────────────┘      │      │
│  └──────────────────────────────────────────────────────┘      │
│                             │                                   │
│                             ▼                                   │
│  ┌──────────────────────────────────────────────────────┐      │
│  │                 JSON File Storage                     │      │
│  │   /cards/  /reviews/  /index/  config.json           │      │
│  └──────────────────────────────────────────────────────┘      │
│                             │                                   │
│                             ▼                                   │
│  ┌──────────────┐    ┌──────────────┐                          │
│  │   Web API    │───▶│   Review     │  (Mobile-friendly)       │
│  │   Server     │    │   Web App    │                          │
│  └──────────────┘    └──────────────┘                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
aletheia/
├── data/                       # All user data (git-tracked)
│   ├── cards/                  # Card storage
│   │   ├── dsa/               # By domain
│   │   │   ├── problems/      # Problem cards
│   │   │   └── concepts/      # Concept cards
│   │   ├── system-design/
│   │   ├── math/
│   │   └── research/
│   ├── reviews/                # Review logs (for FSRS optimizer)
│   │   └── review-log.jsonl   # Append-only log
│   ├── sources/                # Source metadata (papers, books, etc.)
│   └── config.json            # User preferences
│
├── .aletheia/                  # Local state (git-ignored)
│   ├── index/                  # Search index cache
│   ├── scheduler-state.json   # FSRS card states
│   └── session/               # Temp files
│
├── src/                        # Source code
│   ├── core/                   # Core library
│   │   ├── cards/             # Card CRUD operations
│   │   ├── scheduler/         # FSRS implementation
│   │   ├── index/             # Taxonomy & tag indexing
│   │   └── storage/           # JSON file operations
│   ├── creation/              # Card creation module
│   │   ├── guided/            # Mode 1: Guided extraction
│   │   ├── feedback/          # Mode 4: Quality feedback
│   │   └── templates/         # Domain-specific templates
│   ├── llm/                   # LLM integration
│   ├── cli/                   # CLI interface
│   └── web/                   # Web server & frontend
│
├── docs/                       # Documentation
└── tests/                      # Test suite
```

---

## Data Models (JSON Schemas)

### Card Base Schema

All cards share common fields:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "type", "created_at", "updated_at", "front", "back"],
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "type": {
      "type": "string",
      "enum": ["dsa-problem", "dsa-concept", "system-design", "math", "research"]
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time"
    },
    "front": {
      "type": "string",
      "description": "Question/prompt (supports LaTeX: $..$ or $$..$$)"
    },
    "back": {
      "type": "string",
      "description": "Answer (supports LaTeX)"
    },
    "taxonomy": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Hierarchical path: ['dsa', 'graphs', 'shortest-path']"
    },
    "tags": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Flat tags: ['#interview-classic', '#greedy']"
    },
    "links": {
      "type": "object",
      "properties": {
        "similar_to": { "type": "array", "items": { "type": "string" } },
        "prerequisite": { "type": "array", "items": { "type": "string" } },
        "leads_to": { "type": "array", "items": { "type": "string" } },
        "applies": { "type": "array", "items": { "type": "string" } },
        "contrasts_with": { "type": "array", "items": { "type": "string" } }
      }
    },
    "sources": {
      "type": "array",
      "items": { "$ref": "#/$defs/source" }
    },
    "creation_mode": {
      "type": "string",
      "enum": ["manual", "guided-extraction", "quality-feedback", "draft-critique"],
      "description": "How this card was created (for analysis)"
    },
    "maturity": {
      "type": "string",
      "enum": ["active", "exhausted"],
      "default": "active"
    }
  }
}
```

### DSA Problem Card (extends base)

```json
{
  "type": "dsa-problem",
  "problem_source": {
    "platform": "leetcode",
    "id": "42",
    "title": "Trapping Rain Water",
    "url": "https://leetcode.com/problems/trapping-rain-water/",
    "difficulty": "hard"
  },
  "patterns": ["two-pointers", "monotonic-stack"],
  "data_structures": ["array"],
  "complexity": {
    "time": "O(n)",
    "space": "O(1)"
  },
  "intuition": "Each position's water = min(max_left, max_right) - height",
  "edge_cases": ["empty array", "monotonic array"],
  "code_solution": "path/to/solution.py or inline"
}
```

### FSRS Card State

Stored separately from card content (in `.aletheia/scheduler-state.json`):

```json
{
  "card_id": "uuid",
  "stability": 1.0,
  "difficulty": 5.0,
  "due": "2024-01-15T10:00:00Z",
  "last_review": "2024-01-10T10:00:00Z",
  "reps": 3,
  "lapses": 0,
  "state": "review"
}
```

### Review Log Entry

Append-only log for FSRS optimizer training:

```json
{
  "card_id": "uuid",
  "reviewed_at": "2024-01-10T10:30:00Z",
  "rating": 3,
  "elapsed_days": 5.5,
  "scheduled_days": 5.0,
  "state_before": { "stability": 0.8, "difficulty": 5.2 },
  "state_after": { "stability": 1.2, "difficulty": 5.0 }
}
```

---

## Tech Stack (Decided)

```
Backend:  Python 3.11+
├── Core:      Pure Python + pydantic (validation)
├── FSRS:      py-fsrs library
├── CLI:       typer (modern, type-hinted)
├── Web API:   FastAPI
├── LLM:       litellm (provider abstraction)
└── Storage:   JSON files + SQLite (hybrid)

Frontend:  HTMX + Jinja2 (server-rendered)
├── Templating: Jinja2 (via FastAPI)
├── Interactivity: HTMX (HTML attributes, minimal JS)
├── LaTeX:     KaTeX (server-side rendering)
├── Styling:   Tailwind CSS
└── Mobile:    Responsive design (no PWA needed initially)

Data Storage:
├── Cards:     JSON files (git-tracked, human-readable)
├── Reviews:   SQLite (time-series queries, statistics)
├── FSRS State: SQLite (frequent updates)
└── Search:    SQLite FTS5 (full-text search)
```

**Why this stack:**
- Python: Fast development, rich ecosystem, learning goal
- HTMX: Simplest frontend approach, no JS framework to learn
- Hybrid storage: Git-friendly cards + queryable operational data
- litellm: Single interface for Claude, GPT-4, Ollama, etc.

---

## Hosting

### Option 1: Oracle Cloud Free Tier (Best Free)

| Aspect | Details |
|--------|---------|
| **Free Tier** | 4 ARM cores, 24GB RAM, 200GB disk (Always Free) |
| **Always On** | Yes - full VM |
| **SQLite** | Excellent - persistent filesystem |
| **Setup** | Manual: install Python, systemd service, nginx |

```bash
# Setup on Oracle Cloud ARM instance
sudo apt update && sudo apt install python3-pip nginx
pip install aletheia
# Configure systemd service and nginx reverse proxy
```

**Gotchas:**
- ARM availability can be limited in popular regions (keep trying)
- Idle instances may be reclaimed - upgrade to Pay-As-You-Go (still free if within limits)
- Some users report account termination issues

### Option 2: GCP Compute Engine e2-micro (Most Reliable Free)

| Aspect | Details |
|--------|---------|
| **Free Tier** | e2-micro (0.25 vCPU shared, 1GB RAM) - Always Free |
| **Regions** | us-west1, us-central1, us-east1 only |
| **SQLite** | Excellent - persistent disk |
| **Setup** | Manual: similar to Oracle |

```bash
# Create e2-micro instance in free region
gcloud compute instances create aletheia \
  --machine-type=e2-micro \
  --zone=us-central1-a \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud
```

**Gotchas:**
- 1GB RAM is tight - may need swap
- 30GB persistent disk included free

### Option 3: AWS EC2 t2.micro (Free for 12 months)

| Aspect | Details |
|--------|---------|
| **Free Tier** | t2.micro (1 vCPU, 1GB RAM) - 750 hrs/month for 12 months |
| **SQLite** | Excellent - EBS persistent |
| **Setup** | Manual: similar to above |

**Gotchas:**
- Free tier expires after 12 months
- Watch for accidental charges (EBS, data transfer)

### Option 4: Hetzner VPS (Best Cheap Paid)

| Aspect | Details |
|--------|---------|
| **Price** | ~€4/month (CX22: 2 vCPU, 4GB RAM, 40GB) |
| **Reliability** | 99.9% SLA, excellent reputation |
| **SQLite** | Excellent |
| **Setup** | Use Coolify for easy Git-based deploys |

```bash
# Install Coolify on fresh Hetzner VPS
curl -fsSL https://get.coolify.io | bash
# Then connect GitHub repo and deploy
```

### Comparison

| Platform | Cost | Specs | Always On | SQLite | Reliability |
|----------|------|-------|-----------|--------|-------------|
| **Oracle Cloud** | Free | 4 ARM, 24GB | Yes | Excellent | Medium* |
| **GCP e2-micro** | Free | 0.25 vCPU, 1GB | Yes | Excellent | High |
| **AWS t2.micro** | Free (12mo) | 1 vCPU, 1GB | Yes | Excellent | High |
| **Hetzner CX22** | €4/mo | 2 vCPU, 4GB | Yes | Excellent | High (SLA) |

*Oracle has reports of account issues; upgrade to Pay-As-You-Go to reduce risk

### Local Development

```bash
# Run locally
aletheia serve --port 8000

# Access at http://localhost:8000
```

### Deployment Checklist

1. [ ] Provision VM (Oracle/GCP/AWS/Hetzner)
2. [ ] Install Python 3.11+, pip, nginx
3. [ ] Clone repo, install dependencies
4. [ ] Configure systemd service for FastAPI (uvicorn)
5. [ ] Configure nginx as reverse proxy
6. [ ] Set up SSL with Let's Encrypt (certbot)
7. [ ] Configure firewall (allow 80, 443)
8. [ ] Set environment variables (LLM API keys)
9. [ ] Point domain/subdomain to VM IP

---

## API Design (Web Review Interface)

### REST Endpoints

```
# Cards
GET    /api/cards                    # List cards (with filters)
GET    /api/cards/{id}               # Get single card
POST   /api/cards                    # Create card
PUT    /api/cards/{id}               # Update card content
DELETE /api/cards/{id}               # Delete card

# Card Lifecycle
POST   /api/cards/{id}/exhaust       # Mark as exhausted
POST   /api/cards/{id}/suspend       # Pause reviews
POST   /api/cards/{id}/resume        # Resume reviews
POST   /api/cards/{id}/split         # Split into multiple
POST   /api/cards/merge              # Merge cards
GET    /api/cards/{id}/history       # Edit history

# Review
GET    /api/review/due               # Get cards due for review
POST   /api/review/{id}              # Submit review rating
GET    /api/review/session           # Start review session (returns first card)

# Statistics
GET    /api/stats                    # Overall statistics
GET    /api/stats/heatmap            # Review activity heatmap
GET    /api/stats/domain/{domain}    # Per-domain stats

# LLM
POST   /api/llm/extract              # Mode 1: Guided extraction
POST   /api/llm/feedback             # Mode 4: Quality feedback
```

### Review Flow

```
1. Client: GET /api/cards/due?limit=20
   Server: Returns batch of due cards (front only initially)

2. User sees card front, thinks, reveals back

3. User rates: Again (1), Hard (2), Good (3), Easy (4)

4. Client: POST /api/cards/{id}/review { rating: 3 }
   Server:
   - Updates FSRS state
   - Appends to review log
   - Returns next due date

5. Repeat until session complete
```

### WebSocket (Optional, for real-time)

```
WS /api/review/session
- Server pushes next card
- Client sends rating
- Lower latency for mobile
```

---

## Card Lifecycle & Editing

### Card States

```
                    ┌─────────────┐
                    │   Created   │
                    └──────┬──────┘
                           │
                           ▼
    ┌──────────────────────────────────────────┐
    │                 Active                    │
    │  (being reviewed, accumulating history)  │
    └──────────────────────────────────────────┘
           │              │              │
           ▼              ▼              ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │  Edited  │   │Exhausted │   │Suspended │
    │(improved)│   │(obsolete)│   │(paused)  │
    └──────────┘   └──────────┘   └──────────┘
```

### Editing Flows

**1. Edit During Review (Web UI)**

When reviewing a card, user can flag it for editing:
```
[Card Front]
"What is the time complexity of Dijkstra's?"

[Reveal] [Flag for Edit]

[Card Back]
"O((V+E) log V) with binary heap"

[Again] [Hard] [Good] [Easy] [Edit Now]
```

Clicking "Edit Now" opens inline editor (HTMX partial):
```html
<form hx-put="/api/cards/{id}" hx-target="#card-display">
  <textarea name="front">What is the time complexity...</textarea>
  <textarea name="back">O((V+E) log V)...</textarea>
  <button type="submit">Save</button>
  <button hx-get="/api/cards/{id}" hx-target="#card-display">Cancel</button>
</form>
```

**2. Edit via CLI**

```bash
# Edit specific card (opens in $EDITOR)
$ aletheia edit abc123

# Edit with search
$ aletheia edit --search "dijkstra complexity"
Found 2 cards:
  [1] abc123: "What is the time complexity of Dijkstra's?"
  [2] def456: "Compare Dijkstra vs Bellman-Ford complexity"
Select card to edit [1-2]: 1

# Opens card in $EDITOR as YAML for easy editing
```

Card opens as editable YAML:
```yaml
# Card: abc123
# Type: dsa-concept
# Created: 2024-01-10
# Last edited: 2024-01-15

front: |
  What is the time complexity of Dijkstra's algorithm?

back: |
  O((V+E) log V) with binary heap
  O(V²) with array (dense graphs)

tags:
  - "#graphs"
  - "#shortest-path"

# Edit above, save and close to update
# Delete all content to cancel
```

**3. Reformulate Card (Nielsen's "exhaust" concept)**

When understanding deepens, a card may need fundamental rethinking:

```bash
$ aletheia reformulate abc123

Current card:
  Q: "What is the time complexity of Dijkstra's?"
  A: "O((V+E) log V)"

This card will be marked 'exhausted' and archived.
Create replacement card(s)? [y/n]: y

# Opens guided extraction for new card(s)
# Links new cards to original via 'reformulated_from'
```

**4. Split Card**

Break an overly complex card into atomic pieces:

```bash
$ aletheia split abc123

Current card covers multiple ideas:
  - Dijkstra time complexity
  - Comparison with Bellman-Ford
  - When to use which

Split into 3 cards? [y/n]: y

# Creates 3 new cards, marks original as 'split_into: [id1, id2, id3]'
```

**5. Merge Cards**

Combine related cards that overlap:

```bash
$ aletheia merge abc123 def456

Cards to merge:
  [abc123] "Time complexity of Dijkstra's"
  [def456] "Space complexity of Dijkstra's"

Merge into single card? [y/n]: y

# Opens editor with combined content
# Original cards marked 'merged_into: xyz789'
```

### Card Metadata for Lifecycle

```json
{
  "id": "abc123",
  "maturity": "active",  // active | exhausted | suspended
  "lifecycle": {
    "created_at": "2024-01-10T10:00:00Z",
    "updated_at": "2024-01-15T14:30:00Z",
    "edit_count": 3,
    "reformulated_from": null,  // or card ID
    "split_from": null,
    "merged_from": [],
    "suspended_at": null,
    "exhausted_at": null,
    "exhausted_reason": null  // "understanding_deepened" | "duplicate" | "incorrect"
  }
}
```

### Review Log Tracks Edits

```json
{
  "card_id": "abc123",
  "event_type": "edit",  // or "review", "reformulate", "split", "merge"
  "timestamp": "2024-01-15T14:30:00Z",
  "changes": {
    "front": { "before": "...", "after": "..." },
    "back": { "before": "...", "after": "..." }
  }
}
```

### API Endpoints for Editing

```
PUT    /api/cards/{id}           # Update card content
POST   /api/cards/{id}/exhaust   # Mark as exhausted
POST   /api/cards/{id}/suspend   # Pause reviews
POST   /api/cards/{id}/resume    # Resume reviews
POST   /api/cards/{id}/split     # Split into multiple
POST   /api/cards/merge          # Merge multiple cards
GET    /api/cards/{id}/history   # View edit history
```

---

## LLM Integration

### Using litellm

```python
from litellm import completion

class LLMService:
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model

    async def guided_extraction(
        self,
        context: str,
        domain: str,
        template: Template
    ) -> list[ExtractionQuestion]:
        """Generate Socratic questions for Mode 1"""
        response = await completion(
            model=self.model,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Domain: {domain}\n\nContext:\n{context}"}
            ]
        )
        return parse_questions(response.choices[0].message.content)

    async def quality_feedback(self, card: Card) -> list[QualityIssue]:
        """Review card quality for Mode 4"""
        response = await completion(
            model=self.model,
            messages=[
                {"role": "system", "content": QUALITY_SYSTEM_PROMPT},
                {"role": "user", "content": card.to_review_format()}
            ]
        )
        return parse_issues(response.choices[0].message.content)

    async def suggest_reformulation(self, card: Card, review_history: list) -> list[Card]:
        """Suggest card improvements based on review struggles"""
        # Called when user repeatedly fails a card
        ...
```

### Supported Providers (via litellm)

```python
# All use the same completion() interface:
model="claude-sonnet-4-20250514"           # Anthropic Claude
model="gpt-4"                     # OpenAI
model="ollama/llama2"             # Local Ollama
model="together_ai/mistral-7b"    # Together.ai
model="groq/mixtral-8x7b"         # Groq
```

### Configuration

```json
// config.json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "api_key_env": "ANTHROPIC_API_KEY",  // reads from env var
    "fallback_model": "ollama/llama2"    // if API unavailable
  }
}
```

---

## CLI Commands Summary

```bash
# Card Creation
aletheia add <domain>              # Interactive guided extraction (Mode 1)
aletheia add dsa-problem           # Add DSA problem card
aletheia add dsa-concept           # Add DSA concept card
aletheia add system-design         # Add System Design card
aletheia add --quick               # Quick add (skip guided extraction)

# Card Management
aletheia edit <card-id>            # Edit card in $EDITOR
aletheia edit --search "query"     # Search and edit
aletheia list                      # List all cards
aletheia list --domain dsa         # Filter by domain
aletheia list --tag "#graphs"      # Filter by tag
aletheia show <card-id>            # Display card details

# Card Lifecycle
aletheia reformulate <card-id>     # Replace with improved version
aletheia split <card-id>           # Split into multiple cards
aletheia merge <id1> <id2>         # Merge cards
aletheia suspend <card-id>         # Pause reviews
aletheia resume <card-id>          # Resume reviews
aletheia exhaust <card-id>         # Mark as obsolete

# Review (CLI fallback, main review is web)
aletheia review                    # Quick CLI review session
aletheia due                       # Show cards due today

# Server
aletheia serve                     # Start web server for review
aletheia serve --port 8080         # Custom port

# Statistics
aletheia stats                     # Review statistics
aletheia stats --domain dsa        # Per-domain stats

# Quality Check (Mode 4)
aletheia check <card-id>           # Get LLM feedback on card
aletheia check --all               # Check all cards for issues

# Sync
aletheia sync                      # Git add, commit, push
aletheia sync --pull               # Git pull
```

---

## Decisions Made

| Question | Decision |
|----------|----------|
| Tech stack | Python (FastAPI, typer, pydantic, py-fsrs) |
| Frontend | HTMX + Jinja2 + Tailwind CSS |
| Storage | JSON files (cards) + SQLite (reviews, stats, search) |
| Card organization | One file per card |
| CLI style | Simple commands (like git) |
| LLM | litellm (supports Claude, GPT-4, Ollama, etc.) |
| LaTeX | KaTeX server-side rendering |

---

## Implementation Phases

### Phase 1: Core Foundation ✓
- [x] Project setup (pyproject.toml, structure)
- [x] Card models (pydantic)
- [x] JSON file storage for cards
- [x] SQLite setup for reviews/state
- [x] Basic CLI: `add`, `list`, `show`, `edit`, `search`, `stats`

### Phase 2: Review System ✓
- [x] FSRS integration (py-fsrs)
- [x] Review log storage
- [x] CLI review command
- [x] FastAPI server setup
- [x] HTMX templates for review UI
- [x] KaTeX integration

### Phase 3: LLM Integration
- [ ] litellm setup
- [ ] Mode 1: Guided extraction prompts
- [ ] Mode 4: Quality feedback prompts
- [ ] CLI integration

### Phase 4: Polish
- [ ] Card lifecycle (reformulate, split, merge)
- [ ] Statistics dashboard
- [ ] Search (SQLite FTS5)
- [ ] Mobile responsive refinement
- [ ] Git sync helper commands

---

## File Structure (Detailed)

```
aletheia/
├── pyproject.toml                 # Project config, dependencies
├── README.md
│
├── data/                          # User data (git-tracked)
│   ├── cards/
│   │   ├── dsa/
│   │   │   ├── problems/
│   │   │   │   └── leetcode-42.json
│   │   │   └── concepts/
│   │   │       └── monotonic-stack.json
│   │   ├── system-design/
│   │   │   └── leader-follower-replication.json
│   │   ├── math/
│   │   └── research/
│   ├── sources/                   # Source metadata
│   │   └── books.json
│   └── config.json               # User preferences
│
├── .aletheia/                     # Local state (git-ignored)
│   ├── aletheia.db               # SQLite: reviews, FSRS state, search index
│   └── cache/                    # Temp files
│
├── src/
│   └── aletheia/
│       ├── __init__.py
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py           # Typer app entry point
│       │   ├── add.py            # Add commands
│       │   ├── edit.py           # Edit commands
│       │   └── review.py         # Review commands
│       ├── core/
│       │   ├── __init__.py
│       │   ├── models.py         # Pydantic models
│       │   ├── storage.py        # JSON + SQLite operations
│       │   ├── scheduler.py      # FSRS wrapper
│       │   └── search.py         # Full-text search
│       ├── creation/
│       │   ├── __init__.py
│       │   ├── guided.py         # Mode 1: Guided extraction
│       │   ├── feedback.py       # Mode 4: Quality feedback
│       │   └── templates.py      # Domain-specific templates
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── service.py        # LLM service (litellm)
│       │   └── prompts.py        # System prompts
│       └── web/
│           ├── __init__.py
│           ├── app.py            # FastAPI app
│           ├── routes/
│           │   ├── cards.py
│           │   ├── review.py
│           │   └── stats.py
│           ├── templates/        # Jinja2 templates
│           │   ├── base.html
│           │   ├── review.html
│           │   ├── partials/
│           │   │   ├── card.html
│           │   │   └── edit_form.html
│           │   └── stats.html
│           └── static/
│               ├── css/
│               │   └── tailwind.css
│               └── js/
│                   └── htmx.min.js
│
├── tests/
│   ├── test_models.py
│   ├── test_storage.py
│   ├── test_scheduler.py
│   └── test_api.py
│
└── docs/
    ├── product-vision.md
    └── technical-architecture.md
```
