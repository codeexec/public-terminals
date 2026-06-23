"""
API Lifespan - Handles startup and shutdown events
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.config import settings
from src.database.session import init_db
from src.services.warm_pool_service import get_warm_pool_service

_DEFAULT_PASSWORD = "changeme"


def create_lifespan(logger: logging.Logger):
    """Create lifespan context manager"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting Sandbox Server API")
        logger.info(f"Container Platform: {settings.CONTAINER_PLATFORM}")
        logger.info(f"Sandbox TTL: {settings.SANDBOX_TTL_HOURS} hours")

        # Enforce strong admin credentials
        if settings.ADMIN_PASSWORD == _DEFAULT_PASSWORD:
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
            await init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

        # Start warm pool service if enabled
        warm_pool = None
        if settings.WARM_POOL_ENABLED:
            try:
                warm_pool = get_warm_pool_service()
                await warm_pool.start()
                logger.info(
                    f"Warm pool service started (size={settings.WARM_POOL_SIZE})"
                )
            except Exception as e:
                logger.warning(f"Failed to start warm pool service: {e}")

        yield

        # Stop warm pool service
        if warm_pool:
            try:
                await warm_pool.stop()
                logger.info("Warm pool service stopped")
            except Exception as e:
                logger.warning(f"Error stopping warm pool service: {e}")

        logger.info("Shutting down Sandbox Server API")

    return lifespan
