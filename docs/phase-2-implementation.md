# Phase 2: Review System - Implementation Plan

## Overview

This document details the implementation plan for Phase 2 of Aletheia, which adds the spaced repetition review system with FSRS algorithm integration, CLI review command, FastAPI web server, and HTMX templates with KaTeX for LaTeX rendering.

## Implementation Order

### Step 1: FSRS Scheduler Module

**File:** `src/aletheia/core/scheduler.py` (NEW)

Create a wrapper around py-fsrs that integrates with existing storage:

```python
class AletheiaScheduler:
    """Wraps py-fsrs Scheduler with Aletheia storage integration."""

    def __init__(self, db: ReviewDatabase, desired_retention: float = 0.9)
    def get_due_cards(self, limit: int = 20) -> list[str]
    def get_new_cards(self, limit: int = 10) -> list[str]
    def review_card(self, card_id: str, rating: ReviewRating) -> ReviewResult
```

Key components:
- `ReviewRating` enum: AGAIN=1, HARD=2, GOOD=3, EASY=4
- `ReviewResult` dataclass for review outcomes (due_next, interval_days, stability, etc.)
- Converts between FSRS Card objects and SQLite state
- Uses existing `ReviewDatabase` methods: `get_card_state()`, `upsert_card_state()`, `log_review()`

### Step 2: CLI Review Command

**File:** `src/aletheia/cli/main.py` (MODIFY)

Add `review` command for terminal-based review sessions:

```bash
aletheia review              # Start interactive review
aletheia review --limit 10   # Review up to 10 cards
aletheia review --new 3      # Include up to 3 new cards
```

Features:
- Fetches due cards + new cards
- Interactive loop: show front → reveal back → rate (1-4 or q to quit)
- Session summary at end showing cards reviewed

### Step 3: FastAPI Server Setup

**Files:**
- `src/aletheia/web/app.py` (NEW) - FastAPI app with static files, templates
- `src/aletheia/web/dependencies.py` (NEW) - Dependency injection for storage/scheduler
- `src/aletheia/cli/main.py` (MODIFY) - Add `serve` command

```bash
aletheia serve              # Start web server on port 8000
aletheia serve --port 3000  # Custom port
```

### Step 4: KaTeX Integration

**File:** `src/aletheia/web/katex.py` (NEW)

Server-side LaTeX rendering:
- `render_math(text)` - Renders `$...$` (inline) and `$$...$$` (display) patterns
- Uses subprocess to call `katex` CLI with graceful fallback to raw LaTeX
- LRU cache for performance (1000 entries)
- Jinja2 filter registration for templates

### Step 5: HTMX Templates

**Files:**
- `src/aletheia/web/templates/base.html` - Base layout with Tailwind CSS, HTMX, KaTeX CSS
- `src/aletheia/web/templates/review.html` - Review session page
- `src/aletheia/web/templates/partials/card.html` - Card display (HTMX partial)
- `src/aletheia/web/templates/partials/rating.html` - Rating buttons

Template structure:
```
base.html
└── review.html
    └── partials/card.html
        └── partials/rating.html (when answer revealed)
```

### Step 6: Review Routes

**File:** `src/aletheia/web/routes/review.py` (NEW)

HTMX-powered endpoints:
- `GET /review` - Start review session, display first card
- `POST /review/reveal/{card_id}` - Reveal answer (returns card partial with answer)
- `POST /review/rate/{card_id}` - Submit rating, return next card or completion message

### Step 7: Tests

**Files:**
- `tests/test_scheduler.py` - Scheduler unit tests
- `tests/test_web.py` - FastAPI route tests

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Store FSRS state as individual columns (not JSON blob) | Enables efficient SQL queries (`WHERE due <= datetime('now')`) |
| CLI review is simple fallback | Web UI is primary interface; CLI for quick sessions |
| Server-side KaTeX rendering | Faster perceived load, works without JS, cacheable |
| HTMX partials for review flow | No full page reloads, smooth mobile experience |

---

## Files Summary

### New Files

| File | Purpose |
|------|---------|
| `src/aletheia/core/scheduler.py` | FSRS algorithm integration |
| `src/aletheia/web/app.py` | FastAPI application setup |
| `src/aletheia/web/dependencies.py` | Dependency injection |
| `src/aletheia/web/katex.py` | LaTeX rendering utilities |
| `src/aletheia/web/routes/__init__.py` | Routes package |
| `src/aletheia/web/routes/review.py` | Review endpoints |
| `src/aletheia/web/templates/base.html` | Base HTML template |
| `src/aletheia/web/templates/review.html` | Review page |
| `src/aletheia/web/templates/partials/card.html` | Card display partial |
| `src/aletheia/web/templates/partials/rating.html` | Rating buttons partial |
| `src/aletheia/web/static/js/htmx.min.js` | HTMX library |
| `src/aletheia/web/static/css/styles.css` | Custom styles |
| `tests/test_scheduler.py` | Scheduler tests |
| `tests/test_web.py` | Web route tests |

### Modified Files

| File | Changes |
|------|---------|
| `src/aletheia/cli/main.py` | Add `review` and `serve` commands |
| `src/aletheia/core/__init__.py` | Export scheduler classes |

---

## Dependencies

**Already in `pyproject.toml`:**
- `fsrs>=4.0` - FSRS spaced repetition algorithm
- `[web]` extras: `fastapi`, `uvicorn`, `jinja2`, `python-multipart`

**External (CDN):**
- HTMX: Download to `static/js/htmx.min.js`
- Tailwind CSS: Via CDN in base template
- KaTeX CSS: Via CDN in base template

---

## Verification Checklist

### CLI Review
```bash
# Create test cards
aletheia add dsa-problem

# Run review session
aletheia review

# Check stats updated
aletheia stats
```

### Web Server
```bash
# Start server
aletheia serve --port 8000

# Test endpoints
# 1. Open http://localhost:8000/review
# 2. Should display card front
# 3. Click "Reveal Answer"
# 4. Click rating button (Again/Hard/Good/Easy)
# 5. Next card should appear
```

### Tests
```bash
pytest tests/test_scheduler.py -v
pytest tests/test_web.py -v
```

---

## FSRS Integration Details

### State Mapping

| py-fsrs `Card` | Aletheia `card_states` table |
|----------------|------------------------------|
| `state` | `state` ('new', 'learning', 'review', 'relearning') |
| `stability` | `stability` (float) |
| `difficulty` | `difficulty` (float) |
| `due` | `due` (ISO datetime) |
| `last_review` | `last_review` (ISO datetime) |
| `reps` | `reps` (int) |
| `lapses` | `lapses` (int) |

### Review Flow

```
1. Get due cards: SELECT card_id FROM card_states WHERE due <= datetime('now')
2. Load card content from JSON file
3. Display to user, get rating (1-4)
4. Load FSRS state from DB → create py-fsrs Card
5. Call scheduler.review_card(card, Rating(rating))
6. Save updated state to DB
7. Append to review_logs table
8. Repeat with next card
```
