"""
Sandbox API Routes
Main endpoints for sandbox CRUD operations
"""

import logging
from fastapi import APIRouter, Depends, status, BackgroundTasks, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db
from src.database.models import SandboxStatus
from src.api.schemas import (
    SandboxCreate,
    SandboxResponse,
    SandboxListResponse,
    OperationResponse,
)
from src.services.sandbox_service import (
    SandboxService,
    _create_sandbox_background,
    _poll_container_status,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sandboxes", tags=["sandboxes"])


@router.post("", response_model=SandboxResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_sandbox(
    sandbox_create: SandboxCreate,
    background_tasks: BackgroundTasks,
    x_guest_id: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new sandbox instance
    Returns 202 Accepted as this is a long-running operation
    The container creation happens in the background

    OPTIMIZATION: First tries to claim a pre-warmed container for instant startup.
    Falls back to background container creation if no warm containers available.
    """
    service = SandboxService(db)
    return await service.create_sandbox(
        sandbox_create, background_tasks, user_id=x_guest_id
    )


@router.get("/{sandbox_id}", response_model=SandboxResponse)
async def get_sandbox(
    sandbox_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Get details of a specific sandbox
    If sandbox is stopped, automatically restart it
    """
    service = SandboxService(db)
    return await service.get_sandbox(sandbox_id, background_tasks)


@router.get("", response_model=SandboxListResponse)
async def list_sandboxes(
    skip: int = 0,
    limit: int = 100,
    status_filter: SandboxStatus | None = None,
    x_guest_id: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    List all sandboxes with optional filtering
    """
    if not x_guest_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Guest-ID header",
        )
    service = SandboxService(db)
    sandboxes, total = await service.list_sandboxes(
        skip=skip, limit=limit, status_filter=status_filter, user_id=x_guest_id
    )
    return SandboxListResponse(
        sandboxes=[SandboxResponse.model_validate(s) for s in sandboxes], total=total
    )


@router.post("/{sandbox_id}/start", response_model=SandboxResponse)
async def start_sandbox(
    sandbox_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Start a stopped sandbox
    """
    service = SandboxService(db)
    return await service.start_sandbox(sandbox_id, background_tasks)


@router.delete("/{sandbox_id}", status_code=status.HTTP_200_OK)
async def delete_sandbox(
    sandbox_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a sandbox instance
    Stops the container and soft-deletes the sandbox record
    """
    service = SandboxService(db)
    return await service.delete_sandbox(sandbox_id, background_tasks)


@router.get("/{sandbox_id}/status", response_model=OperationResponse)
async def get_sandbox_status(
    sandbox_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Poll the status of a sandbox (useful for long-running operations)
    """
    service = SandboxService(db)
    res = await service.get_sandbox_status(sandbox_id)
    return OperationResponse(**res)
