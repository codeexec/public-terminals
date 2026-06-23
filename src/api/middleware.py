"""
API Middleware - Security headers and CORS configuration
"""

from fastapi import Request, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings


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


def setup_middleware(app: FastAPI):
    """Configure all middleware for the FastAPI application"""
    
    # Add security headers middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS configuration - restrictive for security
    allowed_origins = settings.ALLOWED_CORS_ORIGINS.copy()
    if "*" in allowed_origins:
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
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Guest-ID",
        ],
        max_age=600,
    )
