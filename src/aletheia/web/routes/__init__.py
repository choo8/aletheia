"""Web routes for Aletheia."""

from aletheia.web.routes.review import router as review_router
from aletheia.web.routes.search import router as search_router

__all__ = ["review_router", "search_router"]
