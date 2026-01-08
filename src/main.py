"""
Main FastAPI Application
Terminal Server API
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.config import settings
from src.database.session import init_db
from src.api.routes import terminals, callbacks
from src.api.schemas import HealthResponse

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    """
    # Startup
    logger.info("Starting Terminal Server API")
    logger.info(f"Container Platform: {settings.CONTAINER_PLATFORM}")
    logger.info(f"Terminal TTL: {settings.TERMINAL_TTL_HOURS} hours")

    # Initialize database
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Terminal Server API")


# Create FastAPI app
app = FastAPI(
    title="Terminal Server API",
    description="API for managing remote terminal instances",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(terminals.router, prefix="/api/v1")
app.include_router(callbacks.router, prefix="/api/v1")

# Mount static files
app.mount("/static", StaticFiles(directory="src/static"), name="static")


@app.get("/", tags=["root"])
async def root():
    """Serve the frontend app"""
    return FileResponse("src/static/index.html")


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        version="1.0.0"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower()
    )
