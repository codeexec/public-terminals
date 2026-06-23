"""
API Callback Routes
Endpoints for containers to report back status and tunnel URLs

SECURITY: All endpoints require callback authentication via HMAC token
"""

import logging
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.database.session import get_db
from src.database.models import Sandbox, SandboxStatus
from src.repositories.sandbox_repo import SandboxRepository
from src.api.schemas import SandboxCallbackRequest
from src.auth.callback_auth import verify_callback_token, extract_bearer_token
from src.services.warm_pool_service import get_warm_pool_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/callbacks", tags=["callbacks"])


def get_actual_sandbox_id(callback: SandboxCallbackRequest) -> str:
    """Extract sandbox_id from callback, falling back to terminal_id for old containers"""
    s_id = callback.sandbox_id or callback.terminal_id
    if not s_id:
        # This shouldn't happen with the current schema and validators, but for safety:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Missing sandbox_id or terminal_id"
        )
    return s_id


def verify_callback_authentication(
    callback: SandboxCallbackRequest, authorization: Optional[str] = Header(None)
):
    """
    Verify callback authentication token.
    Supports both sandbox_id and terminal_id (for legacy containers).
    """
    s_id = get_actual_sandbox_id(callback)
    token = extract_bearer_token(authorization)

    if not token:
        logger.warning(f"Callback for {s_id} missing auth token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_callback_token(s_id, token):
        logger.warning(f"Callback for {s_id} has invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid callback token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/tunnel", status_code=status.HTTP_200_OK)
async def report_tunnel_url(
    callback: SandboxCallbackRequest,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """
    Callback endpoint for containers to report their tunnel URL
    """
    # Verify authentication
    verify_callback_authentication(callback, authorization)
    
    s_id = get_actual_sandbox_id(callback)

    logger.info(f"Received tunnel callback for sandbox {s_id}")

    # Check if this is a warm pool container
    warm_pool = get_warm_pool_service()
    if warm_pool.is_warm_id(s_id):
        # Update the warm pool instead of database
        if callback.tunnel_url:
            await warm_pool.update_tunnel_url(s_id, callback.tunnel_url)
            logger.info(
                f"Updated warm container {s_id} with tunnel URL"
            )
        return {
            "status": "success",
            "sandbox_id": s_id,
            "message": "Warm container tunnel URL registered",
        }

    # Find the sandbox
    repo = SandboxRepository(db)
    sandbox = await repo.get_by_id(s_id)

    if not sandbox:
        logger.error(f"Sandbox {s_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox {s_id} not found",
        )

    # Update tunnel URL and status
    sandbox.tunnel_url = callback.tunnel_url
    sandbox.status = SandboxStatus.STARTED

    await db.commit()
    await db.refresh(sandbox)

    logger.info(
        f"Updated sandbox {s_id} with tunnel URL: {callback.tunnel_url}"
    )

    return {
        "status": "success",
        "sandbox_id": sandbox.id,
        "message": "Tunnel URL registered successfully",
    }


@router.post("/status", status_code=status.HTTP_200_OK)
async def report_status(
    callback: SandboxCallbackRequest,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """
    Callback endpoint for containers to report their status
    """
    # Verify authentication
    verify_callback_authentication(callback, authorization)
    
    s_id = get_actual_sandbox_id(callback)

    logger.info(
        f"Received status callback for sandbox {s_id}: {callback.status}"
    )

    # Find the sandbox
    repo = SandboxRepository(db)
    sandbox = await repo.get_by_id(s_id)

    if not sandbox:
        logger.error(f"Sandbox {s_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox {s_id} not found",
        )

    # Update status (handle string or enum)
    if callback.status:
        try:
            # Convert string to uppercase Enum
            new_status = callback.status.upper()
            sandbox.status = SandboxStatus(new_status)
        except (ValueError, AttributeError):
            logger.warning(f"Invalid status received: {callback.status}")

    if callback.error_message:
        sandbox.error_message = callback.error_message
        sandbox.status = SandboxStatus.FAILED

    await db.commit()
    await db.refresh(sandbox)

    logger.info(f"Updated sandbox {s_id} status to: {sandbox.status}")

    return {
        "status": "success",
        "sandbox_id": sandbox.id,
        "message": "Status updated successfully",
    }


@router.post("/health", status_code=status.HTTP_200_OK)
async def container_health_check(
    callback: SandboxCallbackRequest,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """
    Health check endpoint for containers to ping
    """
    # Verify authentication
    verify_callback_authentication(callback, authorization)
    
    s_id = get_actual_sandbox_id(callback)

    # Find the sandbox
    repo = SandboxRepository(db)
    sandbox = await repo.get_by_id(s_id)

    if not sandbox:
        logger.error(f"Sandbox {s_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox {s_id} not found",
        )

    # Track activity for idle timeout detection
    sandbox.set_last_activity()
    await db.commit()

    # Just acknowledging the health check
    return {"status": "healthy", "sandbox_id": sandbox.id}


@router.post("/stats", status_code=status.HTTP_200_OK)
async def report_stats(
    callback: SandboxCallbackRequest,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    # Verify authentication
    verify_callback_authentication(callback, authorization)
    
    s_id = get_actual_sandbox_id(callback)

    # First try to find the sandbox directly
    repo = SandboxRepository(db)
    sandbox = await repo.get_by_id(s_id)

    # If not found, and it looks like a warm ID, check if it was claimed
    if not sandbox and s_id.startswith("warm-"):
        # The container_name is deterministically derived from the warm ID
        # warm-123 -> sandbox-warm-123
        expected_container_name = f"sandbox-{s_id}"
        sandbox = await repo.get_by_container_name(expected_container_name)

        if sandbox:
            logger.info(
                f"Found real sandbox {sandbox.id} for warm container {s_id} (via container_name lookup)"
            )

    # If still not found, check if it's an unclaimed warm container
    if not sandbox:
        warm_pool = get_warm_pool_service()
        if warm_pool.is_warm_id(s_id):
            return {
                "status": "success",
                "sandbox_id": s_id,
                "message": "Warm container stats received (ignored)",
            }

        # Real 404 if not found and not a warm container
        logger.error(f"Sandbox {s_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox {s_id} not found",
        )

    # Update stats cache
    if sandbox.container_id and (
        callback.cpu_percent is not None or callback.memory_mb is not None
    ):
        from src.services.stats_service import stats_service

        stats_service.update_container_stats(
            container_id=sandbox.container_id,
            cpu_percent=callback.cpu_percent or 0.0,
            memory_mb=callback.memory_mb or 0.0,
            memory_percent=callback.memory_percent or 0.0,
        )

        logger.debug(
            f"Updated stats for sandbox {sandbox.id}: "
            f"CPU={callback.cpu_percent}%, MEM={callback.memory_mb}MB"
        )

    return {
        "status": "success",
        "sandbox_id": sandbox.id,
        "message": "Stats updated successfully",
    }


@router.post("/idle", status_code=status.HTTP_200_OK)
async def report_idle_shutdown(
    callback: SandboxCallbackRequest,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """
    Callback endpoint for containers to report that they are idle and should be shut down
    """
    # Verify authentication
    verify_callback_authentication(callback, authorization)
    
    s_id = get_actual_sandbox_id(callback)

    logger.info(
        f"Received idle shutdown request for sandbox {s_id}: {callback.message or callback.error_message}"
    )

    # Find the sandbox
    repo = SandboxRepository(db)
    sandbox = await repo.get_by_id(s_id)

    if not sandbox:
        logger.error(f"Sandbox {s_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox {s_id} not found",
        )

    # Check if sandbox is already stopped or being deleted
    if sandbox.status in [
        SandboxStatus.STOPPED,
        SandboxStatus.EXPIRED,
        SandboxStatus.FAILED,
    ]:
        logger.info(
            f"Sandbox {s_id} already in terminal state: {sandbox.status}"
        )
        return {
            "status": "success",
            "sandbox_id": sandbox.id,
            "message": f"Sandbox already {sandbox.status}",
        }

    # Stop the container due to inactivity
    logger.info(
        f"Stopping sandbox {sandbox.id} due to inactivity: {callback.message or callback.error_message}"
    )

    # Import here to avoid circular dependency
    from src.services.container_service import get_container_service

    container_service = get_container_service()

    try:
        # Stop the container
        if sandbox.container_id:
            await container_service.stop_sandbox_container(sandbox.container_id)

        # Update sandbox status to STOPPED
        sandbox.status = SandboxStatus.STOPPED
        await db.commit()

        logger.info(
            f"Successfully stopped idle sandbox {sandbox.id} (container: {sandbox.container_id})"
        )

        return {
            "status": "success",
            "sandbox_id": sandbox.id,
            "message": "Sandbox stopped due to inactivity",
        }

    except Exception as e:
        logger.error(f"Failed to stop idle sandbox {sandbox.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop sandbox: {str(e)}",
        )
