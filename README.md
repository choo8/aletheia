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
- **Card lifecycle management** - suspend, resume, exhaust, reformulate, split, and merge cards
- **Full-text search** via SQLite FTS5 with prefix matching and 11 indexed fields
- **CLI** for card management
- **Mobile-friendly web interface** for review and search

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

## Configuration

Aletheia loads environment variables from a `.env` file in the project root automatically. Available settings:

```bash
# .env
ALETHEIA_LLM_MODEL=gemini/gemini-3-flash-preview  # LLM model (default)
ALETHEIA_DATA_DIR=./data                           # Card storage directory
ALETHEIA_STATE_DIR=./.aletheia                     # Local state directory
GEMINI_API_KEY=...                                 # Or ANTHROPIC_API_KEY, OPENAI_API_KEY
```

## Quick Start

```bash
# Add a new DSA problem card
aletheia add dsa-problem
aletheia add dsa-problem --guided   # LLM-guided Socratic extraction

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

# Get LLM quality feedback on a card
aletheia check <card-id>

# Search cards (FTS5 with prefix matching)
aletheia search "binary search"
aletheia search "mono"                    # Prefix match: finds "monotonic"
aletheia search --type dsa-problem "two"  # Filter by card type

# Rebuild search index
aletheia reindex

# View statistics
aletheia stats

# Start interactive review session
aletheia review
aletheia review --limit 10   # Limit number of cards
aletheia review --new 3      # Limit new cards

# Card lifecycle management
aletheia suspend <card-id>              # Pause reviews for a card
aletheia resume <card-id>               # Re-enable reviews
aletheia exhaust <card-id> -r duplicate # Permanently retire a card
aletheia revive <card-id>               # Un-exhaust a retired card
aletheia reformulate <card-id>          # Create improved card, retire original
aletheia reformulate <card-id> -g       # LLM-guided reformulation
aletheia split <card-id>                # Split into multiple cards
aletheia merge <id1> <id2>              # Merge cards into one

# Git sync (separate data repo)
aletheia init ~/aletheia-data        # Create a data repository
aletheia sync                        # Commit & push changes
aletheia sync --pull                 # Pull latest + reindex

# Start web server
aletheia serve               # Start on port 8000
aletheia serve --port 3000   # Custom port
```

## Data Repository Setup

Aletheia separates the **tool** (this repo) from your **personal card data**. Card data lives in its own git repository so you can sync it across machines.

### Local Workflow

```bash
# 1. Initialize a data repository
aletheia init ~/aletheia-data

# 2. Set environment variables (add to your shell profile)
export ALETHEIA_DATA_DIR=~/aletheia-data
export ALETHEIA_STATE_DIR=~/aletheia-data/.aletheia

# 3. Use Aletheia normally — cards are stored in the data repo
aletheia add dsa-problem
aletheia review

# 4. Commit and push changes
aletheia sync
```

### Server Deployment

To sync card data from a cloud VM (e.g., for running `aletheia serve`):

```bash
# On the server: generate an SSH deploy key
ssh-keygen -t ed25519 -f ~/.ssh/aletheia_deploy -N ""

# Add the public key as a deploy key (with write access) on your data repo
cat ~/.ssh/aletheia_deploy.pub
# → Go to GitHub repo → Settings → Deploy keys → Add deploy key

# Configure SSH to use the deploy key
cat >> ~/.ssh/config << 'EOF'
Host github.com-aletheia
    HostName github.com
    User git
    IdentityFile ~/.ssh/aletheia_deploy
EOF

# Clone the data repo
git clone git@github.com-aletheia:youruser/aletheia-data.git ~/aletheia-data

# Set environment variables
export ALETHEIA_DATA_DIR=~/aletheia-data
export ALETHEIA_STATE_DIR=~/aletheia-data/.aletheia

# Pull latest cards and push reviews back
aletheia sync --pull    # Pull new cards from laptop
aletheia sync           # Push review progress back to GitHub
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
- [x] **Phase 4**: Polish (card lifecycle, stats, search)
  - [x] **Phase 4a**: Card lifecycle commands (suspend, resume, exhaust, reformulate, split, merge)
  - [x] **Phase 4b**: Search (SQLite FTS5 full-text search, web search UI, reindex)
  - [x] **Phase 4c**: Statistics dashboard (per-domain stats, streaks, review heatmap)
  - [x] **Phase 4d**: Polish (mobile responsive, git sync helpers)

## License

MIT

## Acknowledgments

Inspired by:
- [Michael Nielsen's SRS for Mathematics](https://cognitivemedium.com/srs-mathematics)
- [Andy Matuschak's notes on spaced repetition](https://notes.andymatuschak.org/Spaced_repetition_memory_system)
- [FSRS algorithm](https://github.com/open-spaced-repetition/fsrs4anki)
