"""
Admin API Routes
Protected endpoints for administrative operations
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.schemas import TerminalListResponse, TerminalResponse
from src.auth.dependencies import get_current_admin
from src.auth.schemas import LoginRequest, TokenResponse
from src.auth.jwt_handler import create_access_token
from src.config import settings
from src.database.models import Terminal
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
    # Verify credentials
    if (
        login_request.username != settings.ADMIN_USERNAME
        or login_request.password != settings.ADMIN_PASSWORD
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
