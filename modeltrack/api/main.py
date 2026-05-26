""" 
FastAPI application factory and entry point for ModelTrack REST API.
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
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
    - Dashboard information endpoint
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
            "description": "Unified pipeline orchestration and model registry with A/B testing",
            "docs": "/docs",
            "health": "/health",
            "dashboard": "/dashboard",
            "endpoints": {
                "pipelines": "/pipelines",
                "models": "/models",
                "ab_tests": "/ab-tests",
                "dashboard": "/dashboard",
            },
        }
    
    # ─────────────────────────── Dashboard Endpoint ────────────────────────
    @app.get("/dashboard", tags=["dashboard"])
    async def dashboard():
        """
        Dashboard endpoint - information about the Streamlit dashboard.
        The dashboard provides real-time monitoring of pipelines and models.
        """
        return JSONResponse(
            status_code=200,
            content={
                "message": "ModelTrack Dashboard",
                "status": "running",
                "description": "Real-time monitoring and management interface for pipelines and models",
                "features": [
                    "Pipeline orchestration and status monitoring",
                    "Data quality metrics and lineage visualization",
                    "Model registry and version management",
                    "A/B test results and performance metrics",
                    "Automated retraining history"
                ],
                "note": "Dashboard is running as part of the ModelTrack system. Access the full dashboard by running: streamlit run dashboards/main.py",
                "api_endpoints": {
                    "pipelines": "/pipelines",
                    "models": "/models",
                    "ab_tests": "/ab-tests"
                }
            }
        )
    
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
