"""
API Server
Handles all API operations, container management, and database writes
"""

import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.database.session import init_db
from src.api.routes import terminals, callbacks, admin
from src.api.schemas import HealthResponse


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "font-src 'self' cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )

        return response


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

        # Enforce strong admin credentials
        if settings.ADMIN_PASSWORD == "changeme":
            logger.error(
                "SECURITY ERROR: Default ADMIN_PASSWORD 'changeme' detected. "
                "The server will not start with default credentials. "
                "Please set a strong password using the ADMIN_PASSWORD environment variable."
            )
            raise ValueError(
                "Default admin password detected. Set ADMIN_PASSWORD environment variable to a strong password."
            )

        # Validate password strength
        if len(settings.ADMIN_PASSWORD) < 12:
            logger.error(
                f"SECURITY ERROR: ADMIN_PASSWORD is too short ({len(settings.ADMIN_PASSWORD)} characters). "
                "Minimum length is 12 characters."
            )
            raise ValueError("Admin password must be at least 12 characters long.")

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

    # Add security headers middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS configuration - restrictive for security
    allowed_origins = [
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ]
    # Only add WEB_BASE_URL if it's different from defaults
    if settings.WEB_BASE_URL not in allowed_origins:
        allowed_origins.append(settings.WEB_BASE_URL)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],  # Only needed methods
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Guest-ID",
        ],  # Only needed headers
        max_age=600,  # Cache preflight requests for 10 minutes
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
