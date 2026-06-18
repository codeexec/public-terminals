"""
Cleanup Service - Handles TTL enforcement and expired sandbox cleanup
"""

import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from src.database.models import Sandbox, SandboxStatus
from src.database.session import get_db_context
from src.services.container_service import get_container_service

logger = logging.getLogger(__name__)


class CleanupService:
    """Service to clean up expired sandboxes"""

    def __init__(self):
        self.container_service = get_container_service()

    async def cleanup_expired_sandboxes(self):
        """
        Find and cleanup all expired sandboxes
        This should be run periodically (e.g., every 5 minutes)
        """
        logger.info("Starting cleanup of expired sandboxes")

        with get_db_context() as db:
            # Query for expired sandboxes that are still active
            expired_sandboxes = (
                db.query(Sandbox)
                .filter(
                    Sandbox.expires_at < datetime.now(timezone.utc),
                    Sandbox.status.in_(
                        [
                            SandboxStatus.STARTED,
                            SandboxStatus.STARTING,
                            SandboxStatus.PENDING,
                            SandboxStatus.STOPPED,
                        ]
                    ),
                )
                .all()
            )

            logger.info(f"Found {len(expired_sandboxes)} expired sandboxes to clean up")

            for sandbox in expired_sandboxes:
                try:
                    await self._cleanup_sandbox(db, sandbox)
                except Exception as e:
                    logger.error(f"Failed to cleanup sandbox {sandbox.id}: {e}")

        logger.info("Completed cleanup of expired sandboxes")

    async def _cleanup_sandbox(self, db: Session, sandbox: Sandbox):
        """Cleanup a single sandbox"""
        logger.info(f"Cleaning up expired sandbox: {sandbox.id}")

        # Delete container if it exists
        if sandbox.container_id:
            try:
                await self.container_service.delete_sandbox_container(
                    sandbox.container_id
                )
            except Exception as e:
                logger.error(f"Failed to delete container {sandbox.container_id}: {e}")

        # Update sandbox status
        sandbox.status = SandboxStatus.EXPIRED
        sandbox.deleted_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Successfully cleaned up sandbox: {sandbox.id}")

    async def cleanup_failed_sandboxes(self, max_age_hours: int = 1):
        """
        Cleanup sandboxes that failed to start
        This helps clean up stuck sandboxes
        """
        logger.info("Starting cleanup of failed sandboxes")

        with get_db_context() as db:
            # Find sandboxes stuck in PENDING/STARTING state for too long
            stuck_sandboxes = (
                db.query(Sandbox)
                .filter(
                    Sandbox.status.in_(
                        [SandboxStatus.PENDING, SandboxStatus.STARTING]
                    ),
                    Sandbox.created_at
                    < datetime.now(timezone.utc) - timedelta(hours=max_age_hours),
                )
                .all()
            )

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

                    db.commit()
                    logger.info(f"Marked stuck sandbox as failed: {sandbox.id}")
                except Exception as e:
                    logger.error(f"Failed to cleanup stuck sandbox {sandbox.id}: {e}")

    async def cleanup_idle_sandboxes(self, idle_timeout_seconds: int = 3600):
        """
        Find and stop all idle sandboxes (no activity for N seconds)
        This helps free resources while keeping sandbox record for restart
        """
        idle_timeout_minutes = idle_timeout_seconds // 60
        logger.info(
            f"Starting cleanup of idle sandboxes (timeout: {idle_timeout_minutes} minutes / {idle_timeout_seconds} seconds)"
        )

        with get_db_context() as db:
            # Query for sandboxes that are running but idle
            running_sandboxes = (
                db.query(Sandbox)
                .filter(
                    Sandbox.status == SandboxStatus.STARTED,
                    Sandbox.deleted_at.is_(None),
                )
                .all()
            )

            idle_sandboxes = [
                s for s in running_sandboxes if s.is_idle(idle_timeout_minutes)
            ]

            logger.info(f"Found {len(idle_sandboxes)} idle sandboxes to stop")

            for sandbox in idle_sandboxes:
                try:
                    await self._stop_idle_sandbox(db, sandbox)
                except Exception as e:
                    logger.error(f"Failed to stop idle sandbox {sandbox.id}: {e}")

        logger.info("Completed cleanup of idle sandboxes")

    async def _stop_idle_sandbox(self, db: Session, sandbox: Sandbox):
        """Stop a single idle sandbox"""
        logger.info(f"Stopping idle sandbox: {sandbox.id}")

        # Stop container if it exists
        if sandbox.container_id:
            try:
                await self.container_service.stop_sandbox_container(
                    sandbox.container_id
                )
            except Exception as e:
                logger.error(f"Failed to stop container {sandbox.container_id}: {e}")

        # Update sandbox status to STOPPED
        sandbox.status = SandboxStatus.STOPPED
        db.commit()

        logger.info(f"Successfully stopped idle sandbox: {sandbox.id}")


# Celery task for periodic cleanup
try:
    from celery import shared_task

    @shared_task
    def run_cleanup_task():
        """Celery task to run cleanup"""
        import asyncio

        cleanup_service = CleanupService()
        asyncio.run(cleanup_service.cleanup_expired_sandboxes())
        asyncio.run(cleanup_service.cleanup_failed_sandboxes())

    @shared_task
    def run_idle_timeout_task():
        """
        Celery task to check for idle sandboxes
        """
        import asyncio
        from src.config import settings

        cleanup_service = CleanupService()
        asyncio.run(
            cleanup_service.cleanup_idle_sandboxes(
                settings.SANDBOX_IDLE_TIMEOUT_SECONDS
            )
        )

except ImportError:
    logger.warning("Celery not available, periodic cleanup tasks won't be registered")
