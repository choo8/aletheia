"""Review routes with HTMX support."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from aletheia.core.scheduler import AletheiaScheduler, ReviewRating
from aletheia.core.storage import AletheiaStorage
from aletheia.web.dependencies import get_scheduler, get_storage, get_templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def review_session(
    request: Request,
    storage: AletheiaStorage = Depends(get_storage),
    scheduler: AletheiaScheduler = Depends(get_scheduler),
):
    """Start or continue review session."""
    templates = get_templates()

    # Get cards to review
    due_cards = scheduler.get_due_cards(limit=20)
    new_cards = scheduler.get_new_cards(limit=5)
    card_ids = due_cards + [c for c in new_cards if c not in due_cards]

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

    return templates.TemplateResponse(
        request,
        "partials/card.html",
        {
            "card": card,
            "show_answer": True,
            "remaining": len(card_ids),
        },
    )


@router.post("/rate/{card_id}", response_class=HTMLResponse)
async def rate_card(
    card_id: str,
    request: Request,
    rating: int = Form(...),
    storage: AletheiaStorage = Depends(get_storage),
    scheduler: AletheiaScheduler = Depends(get_scheduler),
):
    """Rate a card and show next (HTMX partial)."""
    templates = get_templates()

    # Process rating
    scheduler.review_card(card_id, ReviewRating(rating))

    # Get next card
    due_cards = scheduler.get_due_cards(limit=20)
    new_cards = scheduler.get_new_cards(limit=5)
    card_ids = due_cards + [c for c in new_cards if c not in due_cards]

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
