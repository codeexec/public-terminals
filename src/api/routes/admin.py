"""
Admin API Routes
Protected endpoints for administrative operations
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.schemas import TerminalListResponse, TerminalResponse
from src.auth.dependencies import get_current_admin
from src.auth.schemas import LoginRequest, TokenResponse
from src.auth.jwt_handler import create_access_token
from src.config import settings
from src.database.models import Terminal, TerminalStatus
from src.database.session import get_db
from src.services.container_service import get_container_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", response_model=TokenResponse)
async def admin_login(login_request: LoginRequest):
    """
    Admin login endpoint
    Validates credentials and returns JWT token
    """
    # Verify credentials using constant-time comparison
    if not (
        secrets.compare_digest(login_request.username, settings.ADMIN_USERNAME)
        and secrets.compare_digest(login_request.password, settings.ADMIN_PASSWORD)
    ):
        logger.warning(f"Failed login attempt for username: {login_request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # Create access token
    access_token = create_access_token(data={"sub": login_request.username})

    logger.info(f"Successful admin login: {login_request.username}")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/terminals", response_model=TerminalListResponse)
async def list_all_terminals(
    skip: int = 0,
    limit: int = 100,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    List ALL terminals (admin-only, not filtered by guest ID)

    This endpoint bypasses the X-Guest-ID filtering used in the public API
    and returns all terminals regardless of which user created them.
    """
    query = db.query(Terminal)

    # Exclude deleted terminals
    query = query.filter(Terminal.deleted_at.is_(None))

    # Order by creation time (newest first)
    query = query.order_by(Terminal.created_at.desc())

    # Get total count
    total = query.count()

    # Apply pagination
    terminals = query.offset(skip).limit(limit).all()

    logger.info(f"Admin {current_admin} listed {len(terminals)} terminals")

    return TerminalListResponse(
        terminals=[TerminalResponse.model_validate(t) for t in terminals],
        total=total,
    )


@router.delete("/terminals/{terminal_id}", status_code=status.HTTP_200_OK)
async def admin_delete_terminal(
    terminal_id: str,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Admin endpoint to terminate any terminal

    Unlike the public delete endpoint, this allows admins to delete
    any terminal regardless of who created it.
    """
    terminal = db.query(Terminal).filter(Terminal.id == terminal_id).first()

    if not terminal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Terminal {terminal_id} not found",
        )

    # Soft delete
    terminal.deleted_at = datetime.now(timezone.utc)
    terminal.status = TerminalStatus.STOPPED
    db.commit()

    # Delete container synchronously for admin operations
    if terminal.container_id:
        try:
            container_service = get_container_service()
            await container_service.delete_terminal_container(terminal.container_id)
            logger.info(
                f"Admin {current_admin} deleted terminal {terminal_id} "
                f"(container: {terminal.container_id})"
            )
        except Exception as e:
            logger.error(f"Failed to delete container {terminal.container_id}: {e}")
            # Continue even if container deletion fails

    return {
        "status": "success",
        "terminal_id": terminal.id,
        "message": "Terminal terminated by admin",
    }


@router.get("/stats", response_model=Dict)
async def get_admin_stats(
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Get system and terminal resource statistics
    """
    try:
        from src.services.stats_service import stats_service

        logger.info("Fetching system stats...")
        # 1. Get system stats
        try:
            system_stats = stats_service.get_system_stats()
            logger.info("System stats fetched successfully")
        except Exception as e:
            logger.error(f"Error fetching system stats: {e}")
            # Return empty/default stats if this fails to avoid 500
            system_stats = {
                "cpu": {"percent": 0, "cores": 0},
                "memory": {"total_gb": 0, "used_gb": 0, "percent": 0},
                "disk": {"total_gb": 0, "used_gb": 0, "percent": 0},
            }

        logger.info("Fetching active terminals from DB...")
        # 2. Get active terminals
        try:
            active_terminals = (
                db.query(Terminal)
                .filter(
                    Terminal.status.in_(
                        [
                            TerminalStatus.PENDING,
                            TerminalStatus.STARTING,
                            TerminalStatus.STARTED,
                        ]
                    ),
                    Terminal.container_id.isnot(None),
                    Terminal.deleted_at.is_(None),
                )
                .all()
            )
            logger.info(f"Found {len(active_terminals)} active terminals")
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(e)}",
            )

        # 3. Get list of active terminals (without fetching real-time stats)
        terminal_stats = []
        for terminal in active_terminals:
            t_stats: Dict[str, Any] = {
                "id": str(terminal.id),
                "container_id": str(terminal.container_id)
                if terminal.container_id
                else None,
                "user_id": str(terminal.user_id) if terminal.user_id else None,
                "status": terminal.status.value
                if hasattr(terminal.status, "value")
                else str(terminal.status),
                "created_at": terminal.created_at.isoformat()
                if terminal.created_at
                else None,
                "expires_at": terminal.expires_at.isoformat()
                if terminal.expires_at
                else None,
                "tunnel_url": terminal.tunnel_url,
                "stats": None,  # Will be fetched lazily by frontend
            }
            terminal_stats.append(t_stats)

        logger.info("Successfully compiled admin stats")
        return {
            "system": system_stats,
            "terminals": terminal_stats,
            "terminal_count": len(active_terminals),
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        logger.error(f"Unhandled error in get_admin_stats: {e}\n{error_trace}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@router.get("/terminals/{container_id}/stats", response_model=Dict)
async def get_terminal_stats(
    container_id: str,
    current_admin: str = Depends(get_current_admin),
):
    """
    Get resource statistics for a specific terminal container
    """
    from src.services.stats_service import stats_service

    try:
        stats = await stats_service.get_container_stats(container_id)
        if not stats:
            # Return empty stats if not found or failed, rather than 404 to avoid frontend errors
            return {"cpu_percent": 0, "memory_mb": 0, "memory_percent": 0}
        return stats
    except Exception as e:
        logger.error(f"Failed to get stats for container {container_id}: {e}")
        return {"cpu_percent": 0, "memory_mb": 0, "memory_percent": 0, "error": str(e)}
