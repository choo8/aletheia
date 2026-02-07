"""Statistics dashboard route."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from aletheia.core.storage import AletheiaStorage
from aletheia.web.dependencies import get_storage, get_templates

router = APIRouter()


def _build_heatmap_days(heatmap: dict[str, int], num_weeks: int = 52) -> list[dict]:
    """Convert heatmap dict into a flat list of day cells for the CSS grid.

    The grid uses ``grid-auto-flow: column`` so items fill top-to-bottom
    (Mon→Sun) then advance to the next column (week).  We start from the
    Monday of the earliest week so columns align properly.

    Each entry: ``{"date": "2025-01-06", "count": 3, "level": 2}``

    Level thresholds: 0 (no reviews), 1 (1-2), 2 (3-4), 3 (5+).
    """
    today = date.today()
    # End on the current day's week-ending Sunday
    end = today + timedelta(days=(6 - today.weekday()))
    start = end - timedelta(weeks=num_weeks) + timedelta(days=1)
    # Align to Monday
    start -= timedelta(days=start.weekday())

    days: list[dict] = []
    current = start
    while current <= end:
        iso = current.isoformat()
        count = heatmap.get(iso, 0)
        if count == 0:
            level = 0
        elif count <= 2:
            level = 1
        elif count <= 4:
            level = 2
        else:
            level = 3
        days.append({"date": iso, "count": count, "level": level})
        current += timedelta(days=1)

    return days


@router.get("/", response_class=HTMLResponse)
async def stats_page(
    request: Request,
    storage: AletheiaStorage = Depends(get_storage),
):
    """Render the statistics dashboard."""
    templates = get_templates()
    full_stats = storage.get_full_stats()
    heatmap_days = _build_heatmap_days(full_stats.get("heatmap", {}))

    return templates.TemplateResponse(
        request,
        "stats.html",
        {"stats": full_stats, "heatmap_days": heatmap_days},
    )
