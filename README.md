# Aletheia

> **Aletheia** (Greek: ἀλήθεια) - "truth" or "disclosure"; the state of not being hidden.

A personal knowledge management and spaced repetition system designed for deep technical learning.

## Overview

Aletheia helps you acquire, crystallize, and retain knowledge across technical domains:

- **DSA / Competitive Programming** - Leetcode problems, algorithms, data structures
- **System Design** - Architecture patterns, trade-offs, scalability concepts
- **Mathematics** - Theorems, proofs, concepts (with LaTeX support)
- **Research** - Key insights from papers and technical books

Unlike traditional flashcard apps optimized for rote memorization, Aletheia is designed for **conceptual understanding** - supporting reasoning prompts, comparative questions, and interconnected knowledge.

## Features

- **Multiple card types** with domain-specific schemas
- **Hybrid storage**: JSON files (git-friendly) + SQLite (fast queries)
- **FSRS algorithm** for optimized spaced repetition
- **LLM-assisted card creation and refinement** (guided extraction, guided editing, quality feedback)
- **CLI** for card management
- **Mobile-friendly web interface** for review

## Installation

Requires Python 3.12+.

```bash
# Clone the repository
git clone https://github.com/choo8/aletheia.git
cd aletheia

# Install with uv (recommended)
uv sync

# Or install with pip
pip install -e .
```

## Quick Start

```bash
# Add a new DSA problem card
aletheia add dsa-problem

# Add a DSA concept card
aletheia add dsa-concept

# Add a system design card
aletheia add system-design

# List all cards
aletheia list

# Show a specific card
aletheia show <card-id>

# Edit a card
aletheia edit <card-id>
aletheia edit <card-id> --guided   # LLM-guided refinement

# Search cards
aletheia search "binary search"

# View statistics
aletheia stats

# Start interactive review session
aletheia review
aletheia review --limit 10   # Limit number of cards
aletheia review --new 3      # Limit new cards

# Start web server
aletheia serve               # Start on port 8000
aletheia serve --port 3000   # Custom port
```

## Project Structure

```
aletheia/
├── data/                 # Card storage (git-tracked)
│   └── cards/           # JSON files organized by type
├── .aletheia/           # Local state (git-ignored)
│   └── aletheia.db     # SQLite: reviews, FSRS state, search
├── src/aletheia/
│   ├── core/           # Models and storage
│   ├── cli/            # Command-line interface
│   ├── web/            # Web server (Phase 2)
│   ├── llm/            # LLM integration (Phase 3)
│   └── creation/       # Card creation modes
└── tests/              # Test suite
```

## Development

```bash
# Install all dependencies including dev
uv sync --all-extras

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=aletheia

# Lint
uv run ruff check src/
```

## Documentation

- [Product Vision](docs/product-vision.md) - Goals, knowledge representation design, MVP scope
- [Technical Architecture](docs/technical-architecture.md) - Tech stack, API design, hosting

## Roadmap

- [x] **Phase 1**: Core foundation (models, storage, CLI)
- [x] **Phase 2**: Review system (FSRS, web UI, KaTeX)
- [x] **Phase 3**: LLM integration (guided extraction, guided editing, quality feedback)
- [ ] **Phase 4**: Polish (lifecycle features, stats, search)

## License

MIT

## Acknowledgments

Inspired by:
- [Michael Nielsen's SRS for Mathematics](https://cognitivemedium.com/srs-mathematics)
- [Andy Matuschak's notes on spaced repetition](https://notes.andymatuschak.org/Spaced_repetition_memory_system)
- [FSRS algorithm](https://github.com/open-spaced-repetition/fsrs4anki)
