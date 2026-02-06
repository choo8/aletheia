"""Search routes with HTMX support."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from aletheia.core.storage import AletheiaStorage
from aletheia.web.dependencies import get_storage, get_templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = "",
    storage: AletheiaStorage = Depends(get_storage),
):
    """Render search page, optionally with results if ?q= is present."""
    templates = get_templates()
    results = None
    if q.strip():
        results = storage.search(q)
    return templates.TemplateResponse(
        request,
        "search.html",
        {"query": q, "results": results},
    )


@router.get("/results", response_class=HTMLResponse)
async def search_results(
    request: Request,
    q: str = "",
    storage: AletheiaStorage = Depends(get_storage),
):
    """HTMX partial returning search results."""
    templates = get_templates()
    results = []
    if q.strip():
        results = storage.search(q)
    return templates.TemplateResponse(
        request,
        "partials/search_results.html",
        {"results": results, "query": q},
    )
