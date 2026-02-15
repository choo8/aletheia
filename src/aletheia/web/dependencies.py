"""Dependency injection for FastAPI routes."""

import os
from functools import lru_cache
from pathlib import Path

from fastapi.templating import Jinja2Templates

from aletheia.core.scheduler import AletheiaScheduler
from aletheia.core.storage import AletheiaStorage
from aletheia.web.katex import setup_katex_filter


@lru_cache
def get_storage() -> AletheiaStorage:
    """Get the storage instance (singleton)."""
    data_dir = Path(os.environ.get("ALETHEIA_DATA_DIR", Path.cwd() / "data"))
    state_dir = Path(os.environ.get("ALETHEIA_STATE_DIR", Path.cwd() / ".aletheia"))
    return AletheiaStorage(data_dir, state_dir)


@lru_cache
def get_scheduler() -> AletheiaScheduler:
    """Get the scheduler instance (singleton)."""
    storage = get_storage()
    return AletheiaScheduler(storage.db)


@lru_cache
def get_templates() -> Jinja2Templates:
    """Get the Jinja2 templates instance."""
    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    # Register KaTeX filter for LaTeX rendering
    setup_katex_filter(templates)

    return templates
