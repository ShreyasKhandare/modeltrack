"""
FastAPI middleware for request/response handling, logging, and error handling.
"""

import time
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from modeltrack.shared.errors import ModelTrackError

logger = logging.getLogger("modeltrack.api")


def add_middleware(app: FastAPI):
    """
    Add all middleware to the FastAPI app.

    - CORS middleware for cross-origin requests
    - Request logging middleware
    - Global exception handler
    """

    # ─────────────────────────── CORS Middleware ─────────────────────────

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─────────────────────────── Request Logging ─────────────────────────

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log incoming requests with timing information."""
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time

        logger.info(
            f"{request.method} {request.url.path} {response.status_code} {duration:.3f}s"
        )

        return response

    # ─────────────────────────── Error Handlers ──────────────────────────

    @app.exception_handler(ModelTrackError)
    async def modeltrack_error_handler(request: Request, exc: ModelTrackError):
        """Handle custom ModelTrack errors."""
        logger.error(
            f"ModelTrackError: {exc.message}",
            extra={"details": exc.details},
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": exc.message,
                "error_type": exc.__class__.__name__,
                "details": exc.details,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected errors."""
        logger.error(
            f"Unexpected error: {type(exc).__name__}: {str(exc)}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "error_type": type(exc).__name__,
                "detail": str(exc),
            },
        )
