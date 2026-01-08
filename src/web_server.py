"""
Web Server
Serves static web UI and provides frontend access to terminal management
"""

import logging
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.config import settings
from src.api.schemas import HealthResponse


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
        title="Terminal Server Web UI",
        description="Web interface for terminal management",
        version="1.0.0",
    )

    app.mount("/static", StaticFiles(directory="src/static"), name="static")

    @app.get("/", tags=["root"])
    async def root():
        logger.info("Serving index.html")
        return FileResponse("src/static/index.html")

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_check():
        return HealthResponse(status="healthy", version="1.0.0")

    return app


def main():
    """Main entry point"""

    logger = configure_logging()
    logger.info("Starting Terminal Server Web UI")
    logger.info(
        f"Web UI will be available at http://{settings.WEB_HOST}:{settings.WEB_PORT}"
    )
    logger.info(f"API server should be running at {settings.API_BASE_URL}")

    uvicorn.run(
        "src.web_server:create_app",
        factory=True,
        host=settings.WEB_HOST,
        port=settings.WEB_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )


app = create_app()


if __name__ == "__main__":
    main()
