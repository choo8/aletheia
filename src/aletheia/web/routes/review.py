"""Review routes with HTMX support."""

import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from aletheia.core.models import Maturity
from aletheia.core.queue import QueueBuilder
from aletheia.core.scheduler import AletheiaScheduler, ReviewRating
from aletheia.core.storage import AletheiaStorage
from aletheia.web.dependencies import get_queue_builder, get_scheduler, get_storage, get_templates

router = APIRouter()


def _filter_active(storage: AletheiaStorage, card_ids: list[str]) -> list[str]:
    """Filter card IDs to only include active (non-suspended/exhausted) cards."""
    return [
        cid for cid in card_ids if (c := storage.load_card(cid)) and c.maturity == Maturity.ACTIVE
    ]


@router.get("/", response_class=HTMLResponse)
async def review_session(
    request: Request,
    storage: AletheiaStorage = Depends(get_storage),
    scheduler: AletheiaScheduler = Depends(get_scheduler),
    queue_builder: QueueBuilder = Depends(get_queue_builder),
):
    """Start or continue review session."""
    templates = get_templates()

    # Get cards to review using queue builder
    due_cards = scheduler.get_due_cards(limit=20)
    new_cards = scheduler.get_new_cards(limit=5)
    card_ids = queue_builder.build_queue(due_cards, new_cards, new_limit=5)
    card_ids = _filter_active(storage, card_ids)

    if not card_ids:
        return templates.TemplateResponse(
            request,
            "review.html",
            {
                "card": None,
                "message": "No cards due for review!",
                "remaining": 0,
            },
        )

    card = storage.load_card(card_ids[0])
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "card": card,
            "remaining": len(card_ids),
            "show_answer": False,
        },
    )


@router.post("/reveal/{card_id}", response_class=HTMLResponse)
async def reveal_answer(
    card_id: str,
    request: Request,
    storage: AletheiaStorage = Depends(get_storage),
    scheduler: AletheiaScheduler = Depends(get_scheduler),
):
    """Reveal card answer (HTMX partial)."""
    templates = get_templates()
    card = storage.load_card(card_id)

    # Get remaining count
    due_cards = scheduler.get_due_cards(limit=20)
    new_cards = scheduler.get_new_cards(limit=5)
    card_ids = due_cards + [c for c in new_cards if c not in due_cards]
    card_ids = _filter_active(storage, card_ids)

    return templates.TemplateResponse(
        request,
        "partials/card.html",
        {
            "card": card,
            "show_answer": True,
            "remaining": len(card_ids),
            "reveal_ts": time.monotonic(),
        },
    )


@router.post("/rate/{card_id}", response_class=HTMLResponse)
async def rate_card(
    card_id: str,
    request: Request,
    rating: int = Form(...),
    reveal_ts: float = Form(default=0.0),
    storage: AletheiaStorage = Depends(get_storage),
    scheduler: AletheiaScheduler = Depends(get_scheduler),
    queue_builder: QueueBuilder = Depends(get_queue_builder),
):
    """Rate a card and show next (HTMX partial)."""
    templates = get_templates()

    # Compute response time from reveal timestamp
    response_time_ms = None
    if reveal_ts > 0:
        response_time_ms = int((time.monotonic() - reveal_ts) * 1000)
        if response_time_ms < 0:
            response_time_ms = None

    # Process rating
    scheduler.review_card(card_id, ReviewRating(rating), response_time_ms=response_time_ms)

    # Get next card using queue builder
    due_cards = scheduler.get_due_cards(limit=20)
    new_cards = scheduler.get_new_cards(limit=5)
    card_ids = queue_builder.build_queue(due_cards, new_cards, new_limit=5)
    card_ids = _filter_active(storage, card_ids)

    if not card_ids:
        return templates.TemplateResponse(
            request,
            "partials/card.html",
            {
                "card": None,
                "message": "Session complete! All cards reviewed.",
                "remaining": 0,
            },
        )

    next_card = storage.load_card(card_ids[0])
    return templates.TemplateResponse(
        request,
        "partials/card.html",
        {
            "card": next_card,
            "remaining": len(card_ids),
            "show_answer": False,
        },
    )
