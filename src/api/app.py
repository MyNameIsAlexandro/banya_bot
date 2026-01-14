from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from src.api.routes import banyas, bookings, users, masters


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Banya Bot API",
        description="API for Telegram Mini App - Sauna booking service",
        version="0.1.0",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, specify exact origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(banyas.router, prefix="/api/banyas", tags=["Banyas"])
    app.include_router(bookings.router, prefix="/api/bookings", tags=["Bookings"])
    app.include_router(users.router, prefix="/api/users", tags=["Users"])
    app.include_router(masters.router, prefix="/api/masters", tags=["Bath Masters"])

    # Mount static files for Mini App
    static_path = Path(__file__).parent.parent.parent / "webapp" / "dist"
    if static_path.exists():
        app.mount("/app", StaticFiles(directory=str(static_path), html=True), name="webapp")

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok"}

    return app
