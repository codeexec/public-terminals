"""
API Server
Handles all API operations, container management, and database writes
"""

import logging
import uvicorn
from fastapi import FastAPI

from src.config import settings
from src.api.routes import sandboxes, callbacks, admin
from src.api.schemas import HealthResponse
from src.api.middleware import setup_middleware
from src.api.lifespan import create_lifespan


_API_VERSION = "1.0.0"


def configure_logging():
    """Configure application logging"""
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger(__name__)


def create_app():
    """Create and configure FastAPI application"""
    logger = configure_logging()

    app = FastAPI(
        title="Sandbox Server API",
        description="API for managing remote sandbox instances",
        version=_API_VERSION,
        lifespan=create_lifespan(logger),
    )

    # Setup middleware (Security headers and CORS)
    setup_middleware(app)

    # Include routers
    app.include_router(sandboxes.router, prefix="/api/v1")
    app.include_router(callbacks.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_check():
        return HealthResponse(status="healthy", version=_API_VERSION)

    return app


def main():
    """Main entry point"""
    uvicorn.run(
        "src.api_server:create_app",
        factory=True,
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.LOG_LEVEL == "DEBUG",
        log_level=settings.LOG_LEVEL.lower(),
    )


app = create_app()


if __name__ == "__main__":
    main()
