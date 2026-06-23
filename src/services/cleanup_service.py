"""
Cleanup Service - Handles TTL enforcement and expired sandbox cleanup
"""

import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Sandbox
from src.constants import SandboxStatus
from src.database.session import get_db_context
from src.repositories.sandbox_repo import SandboxRepository
from src.services.container_service import get_container_service

logger = logging.getLogger(__name__)


class CleanupService:
    """Service to clean up expired sandboxes"""

    def __init__(self):
        self.container_service = get_container_service()

    async def cleanup_expired_sandboxes(self) -> None:
        """
        Find and cleanup all expired sandboxes
        """
        logger.info("Starting cleanup of expired sandboxes")

        async with get_db_context() as db:
            repo = SandboxRepository(db)
            expired_sandboxes = await repo.get_expired()

            logger.info(f"Found {len(expired_sandboxes)} expired sandboxes to clean up")

            for sandbox in expired_sandboxes:
                try:
                    await self._cleanup_sandbox(db, sandbox)
                except Exception as e:
                    logger.error(f"Failed to cleanup sandbox {sandbox.id}: {e}")

        logger.info("Completed cleanup of expired sandboxes")

    async def _cleanup_sandbox(self, db: AsyncSession, sandbox: Sandbox) -> None:
        """Cleanup a single sandbox"""
        logger.info(f"Cleaning up expired sandbox: {sandbox.id}")

        # Delete container if it exists
        if sandbox.container_id:
            # Propagate exception so status is not updated if container deletion fails
            await self.container_service.delete_sandbox_container(
                sandbox.container_id
            )

        # Update sandbox status
        sandbox.status = SandboxStatus.EXPIRED
        sandbox.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Successfully cleaned up sandbox: {sandbox.id}")

    async def cleanup_failed_sandboxes(self, max_age_hours: int = 1) -> None:
        """
        Cleanup sandboxes that failed to start
        """
        logger.info("Starting cleanup of failed sandboxes")

        async with get_db_context() as db:
            # Find sandboxes stuck in PENDING/STARTING state for too long
            from sqlalchemy import select
            threshold = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            stmt = (
                select(Sandbox)
                .where(
                    Sandbox.status.in_([SandboxStatus.PENDING, SandboxStatus.STARTING]),
                    Sandbox.created_at < threshold,
                    Sandbox.deleted_at.is_(None)
                )
            )
            result = await db.execute(stmt)
            stuck_sandboxes = list(result.scalars().all())

            logger.info(f"Found {len(stuck_sandboxes)} stuck sandboxes to clean up")

            for sandbox in stuck_sandboxes:
                try:
                    sandbox.status = SandboxStatus.FAILED
                    sandbox.error_message = (
                        "Sandbox failed to start within expected time"
                    )
                    sandbox.deleted_at = datetime.now(timezone.utc)

                    if sandbox.container_id:
                        await self.container_service.delete_sandbox_container(
                            sandbox.container_id
                        )

                    await db.commit()
                    logger.info(f"Marked stuck sandbox as failed: {sandbox.id}")
                except Exception as e:
                    logger.error(f"Failed to cleanup stuck sandbox {sandbox.id}: {e}")

    async def cleanup_idle_sandboxes(self, idle_timeout_seconds: int = 3600) -> None:
        """
        Find and stop all idle sandboxes
        """
        idle_timeout_minutes = idle_timeout_seconds // 60
        logger.info(
            f"Starting cleanup of idle sandboxes (timeout: {idle_timeout_minutes} minutes)"
        )

        async with get_db_context() as db:
            repo = SandboxRepository(db)
            idle_sandboxes = await repo.get_idle(idle_timeout_minutes)

            logger.info(f"Found {len(idle_sandboxes)} idle sandboxes to stop")

            for sandbox in idle_sandboxes:
                try:
                    await self._stop_idle_sandbox(db, sandbox)
                except Exception as e:
                    logger.error(f"Failed to stop idle sandbox {sandbox.id}: {e}")

        logger.info("Completed cleanup of idle sandboxes")

    async def _stop_idle_sandbox(self, db: AsyncSession, sandbox: Sandbox) -> None:
        """Stop a single idle sandbox"""
        logger.info(f"Stopping idle sandbox: {sandbox.id}")

        # Stop container if it exists
        if sandbox.container_id:
            # Propagate exception so status is not updated if container stop fails
            await self.container_service.stop_sandbox_container(
                sandbox.container_id
            )

        # Update sandbox status to STOPPED
        sandbox.status = SandboxStatus.STOPPED
        await db.commit()

        logger.info(f"Successfully stopped idle sandbox: {sandbox.id}")


# Celery tasks
try:
    from celery import shared_task

    @shared_task(bind=True, max_retries=3, default_retry_delay=60)
    def run_cleanup_task(self):
        """Celery task to run cleanup"""
        import asyncio

        try:
            cleanup_service = CleanupService()
            asyncio.run(cleanup_service.cleanup_expired_sandboxes())
            asyncio.run(cleanup_service.cleanup_failed_sandboxes())
        except Exception as exc:
            logger.error(f"Error running cleanup task: {exc}")
            raise self.retry(exc=exc)

    @shared_task(bind=True, max_retries=3, default_retry_delay=60)
    def run_idle_timeout_task(self):
        """Celery task to check for idle sandboxes"""
        import asyncio
        from src.config import settings

        try:
            cleanup_service = CleanupService()
            asyncio.run(
                cleanup_service.cleanup_idle_sandboxes(
                    settings.SANDBOX_IDLE_TIMEOUT_SECONDS
                )
            )
        except Exception as exc:
            logger.error(f"Error running idle timeout task: {exc}")
            raise self.retry(exc=exc)

except ImportError:
    logger.warning("Celery not available, periodic cleanup tasks won't be registered")
