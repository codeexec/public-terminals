"""
API Callback Routes
Endpoints for containers to report back status and tunnel URLs
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import Terminal, TerminalStatus
from src.api.schemas import TerminalCallbackRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/callbacks", tags=["callbacks"])


@router.post("/tunnel", status_code=status.HTTP_200_OK)
async def report_tunnel_url(
    callback: TerminalCallbackRequest, db: Session = Depends(get_db)
):
    """
    Callback endpoint for containers to report their tunnel URL
    Called by the container's entrypoint script when tunnel is established
    """
    logger.info(f"Received tunnel callback for terminal {callback.terminal_id}")

    # Find the terminal
    terminal = db.query(Terminal).filter(Terminal.id == callback.terminal_id).first()

    if not terminal:
        logger.error(f"Terminal {callback.terminal_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Terminal {callback.terminal_id} not found",
        )

    # Update tunnel URL and status
    terminal.tunnel_url = callback.tunnel_url
    terminal.status = TerminalStatus.STARTED

    db.commit()
    db.refresh(terminal)

    logger.info(
        f"Updated terminal {callback.terminal_id} with tunnel URL: {callback.tunnel_url}"
    )

    return {
        "status": "success",
        "terminal_id": terminal.id,
        "message": "Tunnel URL registered successfully",
    }


@router.post("/status", status_code=status.HTTP_200_OK)
async def report_status(
    callback: TerminalCallbackRequest, db: Session = Depends(get_db)
):
    """
    Callback endpoint for containers to report their status
    Can be used to report errors or status changes
    """
    logger.info(
        f"Received status callback for terminal {callback.terminal_id}: {callback.status}"
    )

    # Find the terminal
    terminal = db.query(Terminal).filter(Terminal.id == callback.terminal_id).first()

    if not terminal:
        logger.error(f"Terminal {callback.terminal_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Terminal {callback.terminal_id} not found",
        )

    # Update status
    if callback.status:
        terminal.status = callback.status

    if callback.error_message:
        terminal.error_message = callback.error_message
        terminal.status = TerminalStatus.FAILED

    db.commit()
    db.refresh(terminal)

    logger.info(f"Updated terminal {callback.terminal_id} status to: {terminal.status}")

    return {
        "status": "success",
        "terminal_id": terminal.id,
        "message": "Status updated successfully",
    }


@router.post("/health", status_code=status.HTTP_200_OK)
async def container_health_check(
    callback: TerminalCallbackRequest, db: Session = Depends(get_db)
):
    """
    Health check endpoint for containers to ping
    Containers can periodically call this to signal they're still alive
    """
    # Find the terminal
    terminal = db.query(Terminal).filter(Terminal.id == callback.terminal_id).first()

    if not terminal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Terminal {callback.terminal_id} not found",
        )

    # Track activity for idle timeout detection
    terminal.set_last_activity()
    db.commit()

    # Just acknowledging the health check
    return {"status": "healthy", "terminal_id": terminal.id}
