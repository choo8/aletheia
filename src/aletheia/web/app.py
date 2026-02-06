"""FastAPI application for Aletheia web interface."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from aletheia.web.routes import review_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Aletheia",
        description="Spaced repetition for technical learning",
        version="0.1.0",
    )

    # Static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Routes
    app.include_router(review_router, prefix="/review", tags=["review"])

    @app.get("/")
    async def home():
        """Redirect to review session."""
        return RedirectResponse(url="/review")

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "ok"}

    return app


# Create the app instance for uvicorn
app = create_app()
