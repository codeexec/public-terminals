"""
API Callback Routes
Endpoints for containers to report back status and tunnel URLs

SECURITY: All endpoints require callback authentication via HMAC token
"""

import logging
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from src.database.session import get_db
from src.database.models import Terminal, TerminalStatus
from src.api.schemas import TerminalCallbackRequest
from src.auth.callback_auth import verify_callback_token, extract_bearer_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/callbacks", tags=["callbacks"])


def verify_callback_authentication(
    callback: TerminalCallbackRequest, authorization: Optional[str] = Header(None)
):
    """
    Verify callback authentication token.

    Args:
        callback: The callback request containing terminal_id
        authorization: The Authorization header

    Raises:
        HTTPException: If authentication fails
    """
    token = extract_bearer_token(authorization)

    if not token:
        logger.warning(f"Callback for {callback.terminal_id} missing auth token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_callback_token(callback.terminal_id, token):
        logger.warning(f"Callback for {callback.terminal_id} has invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid callback token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/tunnel", status_code=status.HTTP_200_OK)
async def report_tunnel_url(
    callback: TerminalCallbackRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """
    Callback endpoint for containers to report their tunnel URL
    Called by the container's entrypoint script when tunnel is established

    Requires: Valid callback authentication token
    """
    # Verify authentication
    verify_callback_authentication(callback, authorization)

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
    callback: TerminalCallbackRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """
    Callback endpoint for containers to report their status
    Can be used to report errors or status changes

    Requires: Valid callback authentication token
    """
    # Verify authentication
    verify_callback_authentication(callback, authorization)

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
    callback: TerminalCallbackRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """
    Health check endpoint for containers to ping
    Containers can periodically call this to signal they're still alive

    Requires: Valid callback authentication token
    """
    # Verify authentication
    verify_callback_authentication(callback, authorization)

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


@router.post("/stats", status_code=status.HTTP_200_OK)
async def report_stats(
    callback: TerminalCallbackRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """
    Callback endpoint for containers to report their resource usage statistics
    Containers call this periodically (every 30 seconds) to push CPU and memory stats

    Requires: Valid callback authentication token
    """
    # Verify authentication
    verify_callback_authentication(callback, authorization)

    # Find the terminal
    terminal = db.query(Terminal).filter(Terminal.id == callback.terminal_id).first()

    if not terminal:
        logger.error(f"Terminal {callback.terminal_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Terminal {callback.terminal_id} not found",
        )

    # Update stats cache
    if terminal.container_id and (
        callback.cpu_percent is not None or callback.memory_mb is not None
    ):
        from src.services.stats_service import stats_service

        stats_service.update_container_stats(
            container_id=terminal.container_id,
            cpu_percent=callback.cpu_percent or 0.0,
            memory_mb=callback.memory_mb or 0.0,
            memory_percent=callback.memory_percent or 0.0,
        )

        logger.debug(
            f"Updated stats for terminal {callback.terminal_id}: "
            f"CPU={callback.cpu_percent}%, MEM={callback.memory_mb}MB"
        )

    # DO NOT track activity here - stats reporting doesn't mean user activity
    # Activity tracking is now handled by the idle monitor in the container

    return {
        "status": "success",
        "terminal_id": terminal.id,
        "message": "Stats updated successfully",
    }


@router.post("/idle", status_code=status.HTTP_200_OK)
async def report_idle_shutdown(
    callback: TerminalCallbackRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """
    Callback endpoint for containers to report that they are idle and should be shut down
    Called by the idle monitor when no user is connected and no commands are running
    for the configured idle timeout period

    Requires: Valid callback authentication token
    """
    # Verify authentication
    verify_callback_authentication(callback, authorization)

    logger.info(
        f"Received idle shutdown request for terminal {callback.terminal_id}: {callback.error_message}"
    )

    # Find the terminal
    terminal = db.query(Terminal).filter(Terminal.id == callback.terminal_id).first()

    if not terminal:
        logger.error(f"Terminal {callback.terminal_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Terminal {callback.terminal_id} not found",
        )

    # Check if terminal is already stopped or being deleted
    if terminal.status in [
        TerminalStatus.STOPPED,
        TerminalStatus.EXPIRED,
        TerminalStatus.FAILED,
    ]:
        logger.info(
            f"Terminal {callback.terminal_id} already in terminal state: {terminal.status}"
        )
        return {
            "status": "success",
            "terminal_id": terminal.id,
            "message": f"Terminal already {terminal.status}",
        }

    # Stop the container due to inactivity
    logger.info(
        f"Stopping terminal {callback.terminal_id} due to inactivity: {callback.error_message}"
    )

    # Import here to avoid circular dependency
    from src.services.container_service import get_container_service

    container_service = get_container_service()

    try:
        # Stop the container
        if terminal.container_id:
            await container_service.stop_terminal_container(terminal.container_id)

        # Update terminal status to STOPPED (not deleted, so it can be restarted if needed)
        terminal.status = TerminalStatus.STOPPED
        db.commit()

        logger.info(
            f"Successfully stopped idle terminal {callback.terminal_id} (container: {terminal.container_id})"
        )

        return {
            "status": "success",
            "terminal_id": terminal.id,
            "message": "Terminal stopped due to inactivity",
        }

    except Exception as e:
        logger.error(f"Failed to stop idle terminal {callback.terminal_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop terminal: {str(e)}",
        )
