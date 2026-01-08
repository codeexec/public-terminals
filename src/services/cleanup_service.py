"""
Cleanup Service - Handles TTL enforcement and expired terminal cleanup
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.database.models import Terminal, TerminalStatus
from src.database.session import get_db_context
from src.services.container_service import get_container_service

logger = logging.getLogger(__name__)


class CleanupService:
    """Service to clean up expired terminals"""

    def __init__(self):
        self.container_service = get_container_service()

    async def cleanup_expired_terminals(self):
        """
        Find and cleanup all expired terminals
        This should be run periodically (e.g., every 5 minutes)
        """
        logger.info("Starting cleanup of expired terminals")

        with get_db_context() as db:
            # Query for expired terminals that are still active
            expired_terminals = (
                db.query(Terminal)
                .filter(
                    Terminal.expires_at < datetime.utcnow(),
                    Terminal.status.in_(
                        [
                            TerminalStatus.STARTED,
                            TerminalStatus.STARTING,
                            TerminalStatus.PENDING,
                        ]
                    ),
                )
                .all()
            )

            logger.info(f"Found {len(expired_terminals)} expired terminals to clean up")

            for terminal in expired_terminals:
                try:
                    await self._cleanup_terminal(db, terminal)
                except Exception as e:
                    logger.error(f"Failed to cleanup terminal {terminal.id}: {e}")

        logger.info("Completed cleanup of expired terminals")

    async def _cleanup_terminal(self, db: Session, terminal: Terminal):
        """Cleanup a single terminal"""
        logger.info(f"Cleaning up expired terminal: {terminal.id}")

        # Delete container if it exists
        if terminal.container_id:
            try:
                await self.container_service.delete_terminal_container(
                    terminal.container_id
                )
            except Exception as e:
                logger.error(f"Failed to delete container {terminal.container_id}: {e}")

        # Update terminal status
        terminal.status = TerminalStatus.EXPIRED
        terminal.deleted_at = datetime.utcnow()
        db.commit()

        logger.info(f"Successfully cleaned up terminal: {terminal.id}")

    async def cleanup_failed_terminals(self, max_age_hours: int = 1):
        """
        Cleanup terminals that failed to start
        This helps clean up stuck terminals
        """
        logger.info("Starting cleanup of failed terminals")

        with get_db_context() as db:
            # Find terminals stuck in PENDING/STARTING state for too long
            stuck_terminals = (
                db.query(Terminal)
                .filter(
                    Terminal.status.in_(
                        [TerminalStatus.PENDING, TerminalStatus.STARTING]
                    ),
                    Terminal.created_at
                    < datetime.utcnow() - timedelta(hours=max_age_hours),
                )
                .all()
            )

            logger.info(f"Found {len(stuck_terminals)} stuck terminals to clean up")

            for terminal in stuck_terminals:
                try:
                    terminal.status = TerminalStatus.FAILED
                    terminal.error_message = (
                        "Terminal failed to start within expected time"
                    )
                    terminal.deleted_at = datetime.utcnow()

                    if terminal.container_id:
                        await self.container_service.delete_terminal_container(
                            terminal.container_id
                        )

                    db.commit()
                    logger.info(f"Marked stuck terminal as failed: {terminal.id}")
                except Exception as e:
                    logger.error(f"Failed to cleanup stuck terminal {terminal.id}: {e}")


# Celery task for periodic cleanup
try:
    from celery import shared_task
    from datetime import timedelta

    @shared_task
    def run_cleanup_task():
        """Celery task to run cleanup"""
        import asyncio

        cleanup_service = CleanupService()
        asyncio.run(cleanup_service.cleanup_expired_terminals())
        asyncio.run(cleanup_service.cleanup_failed_terminals())

except ImportError:
    logger.warning("Celery not available, periodic cleanup tasks won't be registered")
