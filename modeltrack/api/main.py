"""
FastAPI application factory and entry point for ModelTrack REST API.
"""

from fastapi import FastAPI

from .pipeline_routes import router as pipeline_router
from .model_routes import router as model_router
from .ab_test_routes import router as ab_test_router
from .middleware import add_middleware
from ..config import get_settings


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Includes:
    - All route routers (pipelines, models, A/B tests)
    - Middleware (CORS, logging, error handling)
    - Health check endpoints
    """
    app = FastAPI(
        title="ModelTrack API",
        description="Unified pipeline orchestration and model registry with A/B testing",
        version="0.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Add middleware (CORS, logging, error handlers)
    add_middleware(app)

    # Include routers
    app.include_router(pipeline_router)
    app.include_router(model_router)
    app.include_router(ab_test_router)

    # ─────────────────────────── Health Endpoints ────────────────────────

    @app.get("/health", tags=["health"])
    async def health():
        """Health check endpoint."""
        return {"status": "ok", "service": "modeltrack-api"}

    @app.get("/", tags=["info"])
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "ModelTrack API",
            "version": "0.2.0",
            "description": "Unified pipeline orchestration and model registry",
            "docs": "/docs",
            "health": "/health",
            "endpoints": {
                "pipelines": "/pipelines",
                "models": "/models",
                "ab_tests": "/ab-tests",
            },
        }

    return app


# Module-level app instance for uvicorn / Railway
app = create_app()


if __name__ == "__main__":
    import uvicorn

    app = create_app()
    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
