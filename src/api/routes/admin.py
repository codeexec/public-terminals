"""
Admin API Routes
Protected endpoints for administrative operations
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.schemas import SandboxListResponse, SandboxResponse
from src.auth.dependencies import get_current_admin
from src.auth.schemas import LoginRequest, TokenResponse
from src.auth.jwt_handler import create_access_token
from src.config import settings
from src.database.models import Sandbox, SandboxStatus
from src.database.session import get_db
from src.services.container_service import get_container_service
from src.services.warm_pool_service import get_warm_pool_service

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


@router.get("/sandboxes", response_model=SandboxListResponse)
async def list_all_sandboxes(
    skip: int = 0,
    limit: int = 100,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    List ALL sandboxes (admin-only, not filtered by guest ID)

    This endpoint bypasses the X-Guest-ID filtering used in the public API
    and returns all sandboxes regardless of which user created them.
    """
    query = db.query(Sandbox)

    # Exclude deleted sandboxes
    query = query.filter(Sandbox.deleted_at.is_(None))

    # Order by creation time (newest first)
    query = query.order_by(Sandbox.created_at.desc())

    # Get total count
    total = query.count()

    # Apply pagination
    sandboxes = query.offset(skip).limit(limit).all()

    logger.info(f"Admin {current_admin} listed {len(sandboxes)} sandboxes")

    return SandboxListResponse(
        sandboxes=[SandboxResponse.model_validate(s) for s in sandboxes],
        total=total,
    )


@router.delete("/sandboxes/{sandbox_id}", status_code=status.HTTP_200_OK)
async def admin_delete_sandbox(
    sandbox_id: str,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Admin endpoint to terminate any sandbox

    Unlike the public delete endpoint, this allows admins to delete
    any sandbox regardless of who created it.
    """
    sandbox = db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()

    if not sandbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox {sandbox_id} not found",
        )

    # Soft delete
    sandbox.deleted_at = datetime.now(timezone.utc)
    sandbox.status = SandboxStatus.STOPPED
    db.commit()

    # Delete container synchronously for admin operations
    if sandbox.container_id:
        try:
            container_service = get_container_service()
            await container_service.delete_sandbox_container(sandbox.container_id)
            logger.info(
                f"Admin {current_admin} deleted sandbox {sandbox_id} "
                f"(container: {sandbox.container_id})"
            )
        except Exception as e:
            logger.error(f"Failed to delete container {sandbox.container_id}: {e}")
            # Continue even if container deletion fails

    return {
        "status": "success",
        "sandbox_id": sandbox.id,
        "message": "Sandbox terminated by admin",
    }


@router.get("/stats", response_model=Dict)
async def get_admin_stats(
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Get system and sandbox resource statistics
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

        logger.info("Fetching sandboxes from DB...")
        # 2. Get all non-deleted sandboxes
        try:
            active_sandboxes = (
                db.query(Sandbox)
                .filter(Sandbox.deleted_at.is_(None))
                .order_by(Sandbox.created_at.desc())
                .all()
            )
            logger.info(f"Found {len(active_sandboxes)} active sandboxes")
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(e)}",
            )

        # 3. Get list of active sandboxes
        from fastapi.encoders import jsonable_encoder
        sandbox_stats = []
        for sandbox in active_sandboxes:
            try:
                # Use jsonable_encoder to convert datetimes to strings
                s_dict = jsonable_encoder(SandboxResponse.model_validate(sandbox))
                # Ensure stats field is present (Frontend expects it, even if None)
                s_dict["stats"] = None
                sandbox_stats.append(s_dict)
            except Exception as e:
                logger.error(f"Failed to serialize sandbox {sandbox.id}: {e}")
                continue

        logger.info(f"Successfully compiled admin stats for {len(sandbox_stats)} sandboxes")
        return {
            "system": system_stats,
            "sandboxes": sandbox_stats,
            "sandbox_count": len(active_sandboxes),
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Unhandled error in get_admin_stats: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@router.get("/sandboxes/{container_id}/stats", response_model=Dict)
async def get_sandbox_stats(
    container_id: str,
    current_admin: str = Depends(get_current_admin),
):
    """
    Get resource statistics for a specific sandbox container
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


@router.get("/warm-pool", response_model=Dict)
async def get_warm_pool_status(
    current_admin: str = Depends(get_current_admin),
):
    """
    Get the status of the warm container pool.
    Shows how many pre-warmed containers are available for instant startup.
    """
    warm_pool = get_warm_pool_service()
    return await warm_pool.get_pool_status()
