"""
API Server
Handles all API operations, container management, and database writes
"""

import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.database.session import init_db
from src.api.routes import terminals, callbacks, admin
from src.api.schemas import HealthResponse


def configure_logging():
    """Configure application logging"""
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger(__name__)


def create_lifespan(logger):
    """Create lifespan context manager"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting Terminal Server API")
        logger.info(f"Container Platform: {settings.CONTAINER_PLATFORM}")
        logger.info(f"Terminal TTL: {settings.TERMINAL_TTL_HOURS} hours")

        try:
            init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

        yield

        logger.info("Shutting down Terminal Server API")

    return lifespan


def create_app():
    """Create and configure FastAPI application"""
    logger = configure_logging()

    app = FastAPI(
        title="Terminal Server API",
        description="API for managing remote terminal instances",
        version="1.0.0",
        lifespan=create_lifespan(logger),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8001",
            "http://127.0.0.1:8001",
            settings.WEB_BASE_URL,
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(terminals.router, prefix="/api/v1")
    app.include_router(callbacks.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_check():
        return HealthResponse(status="healthy", version="1.0.0")

    return app


def main():
    """Main entry point"""
    uvicorn.run(
        "src.api_server:create_app",
        factory=True,
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )


app = create_app()


if __name__ == "__main__":
    main()
