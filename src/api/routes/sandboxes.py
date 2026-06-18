"""
Sandbox API Routes
Main endpoints for sandbox CRUD operations
"""

import logging
import asyncio
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Header
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import Sandbox, SandboxStatus, SandboxType
from src.api.schemas import (
    SandboxCreate,
    SandboxResponse,
    SandboxListResponse,
    OperationResponse,
)
from src.services.container_service import get_container_service
from src.services.warm_pool_service import get_warm_pool_service
from src.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sandboxes", tags=["sandboxes"])


async def _poll_container_status(
    sandbox_id: str,
    container_name: str,
    db: Session,
    container_service,
    max_attempts: int = 80,
):
    """
    Poll the container's HTTP status endpoint to get tunnel URL
    Uses progressive backoff for faster initial detection
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        for attempt in range(max_attempts):
            try:
                # Resolve IP dynamically (needed for K8s)
                container_ip = await container_service.get_container_ip(container_name)

                if not container_ip:
                    logger.debug(
                        f"Container {container_name} no IP yet (attempt {attempt + 1})"
                    )
                    # Use container name as fallback (works for Docker)
                    status_url = f"http://{container_name}:8888/status"
                else:
                    status_url = f"http://{container_ip}:8888/status"

                logger.info(
                    f"Polling container status for sandbox {sandbox_id} (attempt {attempt + 1}/{max_attempts})"
                )
                
                # Check DB first - maybe a callback already updated it!
                # We need to refresh the sandbox from DB to get current state
                db.expire_all() # Ensure we get fresh data
                db_sandbox = db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
                if db_sandbox and db_sandbox.status == SandboxStatus.STARTED and db_sandbox.tunnel_url:
                    logger.info(f"Sandbox {sandbox_id} already updated via callback. Polling successful.")
                    return True

                response = await client.get(status_url)

                if response.status_code == 200:
                    data = response.json()
                    tunnel_url = data.get("tunnel_url")
                    container_status = data.get("status")

                    if tunnel_url and container_status == "ready":
                        # Update sandbox with tunnel URL
                        sandbox = (
                            db.query(Sandbox)
                            .filter(Sandbox.id == sandbox_id)
                            .first()
                        )
                        if sandbox:
                            sandbox.tunnel_url = tunnel_url
                            sandbox.status = SandboxStatus.STARTED
                            db.commit()
                            logger.info(
                                f"Sandbox {sandbox_id} ready with tunnel URL: {tunnel_url}"
                            )
                            return True
                    else:
                        logger.debug(
                            f"Container not ready yet: status={container_status}, tunnel_url={tunnel_url}"
                        )

            except Exception as e:
                logger.debug(
                    f"Failed to poll container status (attempt {attempt + 1}): {e}"
                )

            # Wait before next attempt
            # Progressive backoff: faster polling at start to reduce perceived latency
            if attempt < 10:
                poll_interval = 0.5
            elif attempt < 20:
                poll_interval = 1.0
            else:
                poll_interval = 2.0

            await asyncio.sleep(poll_interval)

    # Failed to get tunnel URL within timeout
    logger.error(
        f"Failed to get tunnel URL for sandbox {sandbox_id} after {max_attempts} attempts"
    )
    return False


async def _create_sandbox_background(
    sandbox_id: str,
    db: Session,
    restart: bool = False,
    use_gpu: bool = False,
    sandbox_type: SandboxType = SandboxType.TERMINAL,
):
    """
    Background task to create sandbox container
    This runs asynchronously after the API returns
    """
    try:
        container_service = get_container_service()

        # Get the sandbox
        sandbox = db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
        if not sandbox:
            logger.error(f"Sandbox {sandbox_id} not found in background task")
            return

        # Cleanup previous container if restarting
        if restart:
            try:
                container_name = f"sandbox-{sandbox_id}"
                logger.info(
                    f"Cleaning up previous container {container_name} for restart"
                )
                await container_service.delete_sandbox_container(container_name)
            except Exception as e:
                logger.warning(f"Cleanup failed (might be expected): {e}")

        # Update status to starting
        sandbox.status = SandboxStatus.STARTING
        db.commit()

        # Create the container (pass GPU flag and type)
        logger.info(
            f"Creating container for sandbox {sandbox_id} (type={sandbox_type}, gpu={use_gpu})"
        )
        result = await container_service.create_sandbox_container(
            sandbox_id, use_gpu=use_gpu, sandbox_type=sandbox_type
        )

        # Update sandbox with container info
        sandbox.container_id = result["container_id"]
        sandbox.container_name = result["container_name"]
        sandbox.host_port = result.get("host_port")
        db.commit()

        logger.info(
            f"Container created for sandbox {sandbox_id}: {result['container_id']}, host_port: {sandbox.host_port}"
        )

        # Poll container status endpoint to get tunnel URL
        success = await _poll_container_status(
            sandbox_id, sandbox.container_name, db, container_service
        )
        if not success:
            # Mark as failed if we couldn't get tunnel URL
            sandbox = db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
            if sandbox:
                sandbox.status = SandboxStatus.FAILED
                sandbox.error_message = "Failed to obtain tunnel URL from container"
                db.commit()

    except Exception as e:
        logger.error(f"Failed to create container for sandbox {sandbox_id}: {e}")

        # Mark sandbox as failed
        sandbox = db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
        if sandbox:
            sandbox.status = SandboxStatus.FAILED
            sandbox.error_message = str(e)
            db.commit()


@router.post("", response_model=SandboxResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_sandbox(
    sandbox_create: SandboxCreate,
    background_tasks: BackgroundTasks,
    x_guest_id: str = Header(None),
    db: Session = Depends(get_db),
):
    """
    Create a new sandbox instance
    Returns 202 Accepted as this is a long-running operation
    The container creation happens in the background

    OPTIMIZATION: First tries to claim a pre-warmed container for instant startup.
    Falls back to background container creation if no warm containers available.
    """
    # Check max containers limit
    # 1. Check DB count
    active_db_count = (
        db.query(Sandbox)
        .filter(
            Sandbox.status.in_(
                [
                    SandboxStatus.PENDING,
                    SandboxStatus.STARTING,
                    SandboxStatus.STARTED,
                ]
            )
        )
        .count()
    )

    if active_db_count >= settings.MAX_CONTAINERS_PER_SERVER:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Server capacity reached (active sandboxes: {active_db_count})",
        )

    # 2. Check real process count (secondary safeguard)
    try:
        container_service = get_container_service()
        active_real_count = await container_service.count_active_containers()

        if active_real_count >= settings.MAX_CONTAINERS_PER_SERVER:
            logger.warning(
                f"Real container count ({active_real_count}) exceeds DB count ({active_db_count})"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Server capacity reached",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check container count: {e}")
        pass

    # Determine GPU usage
    use_gpu = sandbox_create.use_gpu or False
    if use_gpu and not (settings.GKE_AUTOPILOT_ENABLED and settings.GPU_ENABLED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GPU sandboxes are not available (requires GKE Autopilot with GPU enabled)",
        )

    # Create sandbox record
    sandbox = Sandbox()
    sandbox.user_id = x_guest_id
    sandbox.type = sandbox_create.type
    sandbox.set_expiry(hours=settings.SANDBOX_TTL_HOURS)
    sandbox.status = SandboxStatus.PENDING

    # Store GPU configuration
    sandbox.gpu_enabled = use_gpu
    if use_gpu:
        sandbox.gpu_type = settings.GPU_TYPE
        sandbox.gpu_count = settings.GPU_COUNT

    db.add(sandbox)
    db.commit()
    db.refresh(sandbox)

    logger.info(f"Created sandbox record: {sandbox.id} (gpu={use_gpu})")

    # OPTIMIZATION: Try to claim a pre-warmed container first
    # Currently only Terminal sandboxes support pre-warmed containers
    warm_pool = get_warm_pool_service()
    if settings.WARM_POOL_ENABLED and sandbox.type == SandboxType.TERMINAL:
        try:
            warm_container = await warm_pool.claim_container(use_gpu=use_gpu)
            if warm_container and warm_container.tunnel_url:
                # Instant startup! Transfer warm container to sandbox
                sandbox.container_id = warm_container.container_id
                sandbox.container_name = warm_container.container_name
                sandbox.host_port = warm_container.host_port
                sandbox.tunnel_url = warm_container.tunnel_url
                sandbox.status = SandboxStatus.STARTED

                db.commit()
                db.refresh(sandbox)

                logger.info(
                    f"INSTANT STARTUP: Sandbox {sandbox.id} claimed warm container "
                    f"{warm_container.warm_id} with tunnel {warm_container.tunnel_url}"
                )
                return sandbox
        except Exception as e:
            logger.warning(f"Failed to claim warm container: {e}")

    # Fallback: Trigger background container creation
    background_tasks.add_task(
        _create_sandbox_background,
        sandbox.id,
        db,
        restart=False,
        use_gpu=use_gpu,
        sandbox_type=sandbox.type,
    )

    return sandbox


@router.get("/{sandbox_id}", response_model=SandboxResponse)
async def get_sandbox(
    sandbox_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """
    Get details of a specific sandbox
    If sandbox is stopped, automatically restart it
    """
    sandbox = db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()

    if not sandbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox {sandbox_id} not found",
        )

    # Check for expiration (lazy update)
    if sandbox.is_expired() and sandbox.status != SandboxStatus.EXPIRED:
        logger.info(f"Lazily marking sandbox {sandbox_id} as expired")
        sandbox.status = SandboxStatus.EXPIRED
        db.commit()
        db.refresh(sandbox)
        return sandbox

    # Auto-restart stopped sandboxes
    if sandbox.status == SandboxStatus.STOPPED:
        logger.info(f"Auto-restarting stopped sandbox {sandbox_id}")
        sandbox.status = SandboxStatus.PENDING
        db.commit()

        # Create new container in background (reuse existing function)
        background_tasks.add_task(
            _create_sandbox_background,
            sandbox.id,
            db,
            restart=True,
            use_gpu=sandbox.gpu_enabled,
            sandbox_type=sandbox.type,
        )

    return sandbox


@router.get("", response_model=SandboxListResponse)
async def list_sandboxes(
    skip: int = 0,
    limit: int = 100,
    status_filter: SandboxStatus | None = None,
    x_guest_id: str = Header(None),
    db: Session = Depends(get_db),
):
    """
    List all sandboxes with optional filtering
    """
    query = db.query(Sandbox)

    # Filter by user_id if provided (Guest Mode)
    if x_guest_id:
        query = query.filter(Sandbox.user_id == x_guest_id)

    # Filter by status if provided
    if status_filter:
        query = query.filter(Sandbox.status == status_filter)

    # Exclude deleted sandboxes by default
    query = query.filter(Sandbox.deleted_at.is_(None))

    # Order by creation time (newest first)
    query = query.order_by(Sandbox.created_at.desc())

    # Get total count
    total = query.count()

    # Apply pagination
    sandboxes = query.offset(skip).limit(limit).all()

    # Lazy expiration check for listed sandboxes
    updates_made = False
    for s in sandboxes:
        if s.is_expired() and s.status != SandboxStatus.EXPIRED:
            s.status = SandboxStatus.EXPIRED
            updates_made = True

    if updates_made:
        db.commit()

    return SandboxListResponse(
        sandboxes=[SandboxResponse.model_validate(s) for s in sandboxes], total=total
    )


@router.post("/{sandbox_id}/start", response_model=SandboxResponse)
async def start_sandbox(
    sandbox_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Start a stopped sandbox
    """
    sandbox = db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()

    if not sandbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox {sandbox_id} not found",
        )

    if sandbox.status not in [SandboxStatus.STOPPED, SandboxStatus.FAILED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sandbox is in {sandbox.status} state, cannot start. Create a new one or wait.",
        )

    # Check expiry
    if sandbox.is_expired():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sandbox has expired",
        )

    # Restart logic
    sandbox.status = SandboxStatus.PENDING
    sandbox.error_message = None
    db.commit()

    # Pass the GPU flag from the sandbox record
    background_tasks.add_task(
        _create_sandbox_background,
        sandbox.id,
        db,
        restart=True,
        use_gpu=sandbox.gpu_enabled,
        sandbox_type=sandbox.type,
    )

    return sandbox


@router.delete("/{sandbox_id}", status_code=status.HTTP_200_OK)
async def delete_sandbox(
    sandbox_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """
    Delete a sandbox instance
    Stops the container and soft-deletes the sandbox record
    """
    sandbox = db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()

    if not sandbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox {sandbox_id} not found",
        )

    # Soft delete: set deleted_at timestamp
    from datetime import datetime, timezone

    sandbox.deleted_at = datetime.now(timezone.utc)
    db.commit()

    # Delete container in background
    if sandbox.container_id:
        container_id_to_delete = sandbox.container_id

        async def _delete_container():
            container_service = get_container_service()
            try:
                await container_service.delete_sandbox_container(
                    container_id_to_delete
                )
                logger.info(f"Deleted container for sandbox {sandbox_id}")
            except Exception as e:
                logger.error(
                    f"Failed to delete container for sandbox {sandbox_id}: {e}"
                )

        background_tasks.add_task(_delete_container)

    return {
        "status": "success",
        "sandbox_id": sandbox.id,
        "message": "Sandbox deleted successfully",
    }


@router.get("/{sandbox_id}/status", response_model=OperationResponse)
async def get_sandbox_status(sandbox_id: str, db: Session = Depends(get_db)):
    """
    Poll the status of a sandbox (useful for long-running operations)
    """
    sandbox = db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()

    if not sandbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox {sandbox_id} not found",
        )

    # Map sandbox status to operation status
    operation_status = "pending"
    if sandbox.status == SandboxStatus.STARTED:
        operation_status = "completed"
    elif sandbox.status == SandboxStatus.FAILED:
        operation_status = "failed"
    elif sandbox.status in [SandboxStatus.STARTING, SandboxStatus.PENDING]:
        operation_status = "in_progress"

    return OperationResponse(
        operation_id=sandbox.id,
        status=operation_status,
        sandbox_id=sandbox.id,
        message=sandbox.error_message,
    )
