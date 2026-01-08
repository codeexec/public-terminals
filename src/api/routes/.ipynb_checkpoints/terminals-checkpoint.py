"""
Terminal API Routes
Main endpoints for terminal CRUD operations
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

from src.database.session import get_db
from src.database.models import Terminal, TerminalStatus
from src.api.schemas import (
    TerminalCreate,
    TerminalResponse,
    TerminalListResponse,
    OperationResponse
)
from src.services.container_service import get_container_service
from src.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/terminals", tags=["terminals"])


async def _create_terminal_background(terminal_id: str, db: Session):
    """
    Background task to create terminal container
    This runs asynchronously after the API returns
    """
    container_service = get_container_service()

    try:
        # Get the terminal
        terminal = db.query(Terminal).filter(Terminal.id == terminal_id).first()
        if not terminal:
            logger.error(f"Terminal {terminal_id} not found in background task")
            return

        # Update status to starting
        terminal.status = TerminalStatus.STARTING
        db.commit()

        # Create the container
        logger.info(f"Creating container for terminal {terminal_id}")
        result = await container_service.create_terminal_container(terminal_id)

        # Update terminal with container info
        terminal.container_id = result["container_id"]
        terminal.container_name = result["container_name"]
        db.commit()

        logger.info(f"Container created for terminal {terminal_id}: {result['container_id']}")

        # Note: Status will be updated to STARTED when container calls back with tunnel URL

    except Exception as e:
        logger.error(f"Failed to create container for terminal {terminal_id}: {e}")

        # Mark terminal as failed
        terminal = db.query(Terminal).filter(Terminal.id == terminal_id).first()
        if terminal:
            terminal.status = TerminalStatus.FAILED
            terminal.error_message = str(e)
            db.commit()


@router.post("", response_model=TerminalResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_terminal(
    terminal_create: TerminalCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Create a new terminal instance
    Returns 202 Accepted as this is a long-running operation
    The container creation happens in the background
    """
    # Create terminal record
    terminal = Terminal()
    terminal.set_expiry(hours=settings.TERMINAL_TTL_HOURS)
    terminal.status = TerminalStatus.PENDING

    db.add(terminal)
    db.commit()
    db.refresh(terminal)

    logger.info(f"Created terminal record: {terminal.id}")

    # Trigger background container creation
    background_tasks.add_task(_create_terminal_background, terminal.id, db)

    return terminal


@router.get("/{terminal_id}", response_model=TerminalResponse)
async def get_terminal(terminal_id: str, db: Session = Depends(get_db)):
    """
    Get details of a specific terminal
    """
    terminal = db.query(Terminal).filter(Terminal.id == terminal_id).first()

    if not terminal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Terminal {terminal_id} not found"
        )

    return terminal


@router.get("", response_model=TerminalListResponse)
async def list_terminals(
    skip: int = 0,
    limit: int = 100,
    status_filter: TerminalStatus = None,
    db: Session = Depends(get_db)
):
    """
    List all terminals with optional filtering
    """
    query = db.query(Terminal)

    # Filter by status if provided
    if status_filter:
        query = query.filter(Terminal.status == status_filter)

    # Exclude deleted terminals by default
    query = query.filter(Terminal.deleted_at.is_(None))

    # Order by creation time (newest first)
    query = query.order_by(Terminal.created_at.desc())

    # Get total count
    total = query.count()

    # Apply pagination
    terminals = query.offset(skip).limit(limit).all()

    return TerminalListResponse(
        terminals=terminals,
        total=total
    )


@router.delete("/{terminal_id}", status_code=status.HTTP_200_OK)
async def delete_terminal(
    terminal_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Delete a terminal instance
    Stops the container and marks the terminal as stopped
    """
    terminal = db.query(Terminal).filter(Terminal.id == terminal_id).first()

    if not terminal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Terminal {terminal_id} not found"
        )

    # Update status
    terminal.status = TerminalStatus.STOPPED
    db.commit()

    # Delete container in background
    if terminal.container_id:
        async def _delete_container():
            container_service = get_container_service()
            try:
                await container_service.delete_terminal_container(terminal.container_id)
                logger.info(f"Deleted container for terminal {terminal_id}")
            except Exception as e:
                logger.error(f"Failed to delete container for terminal {terminal_id}: {e}")

        background_tasks.add_task(_delete_container)

    return {
        "status": "success",
        "terminal_id": terminal.id,
        "message": "Terminal deleted successfully"
    }


@router.get("/{terminal_id}/status", response_model=OperationResponse)
async def get_terminal_status(terminal_id: str, db: Session = Depends(get_db)):
    """
    Poll the status of a terminal (useful for long-running operations)
    """
    terminal = db.query(Terminal).filter(Terminal.id == terminal_id).first()

    if not terminal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Terminal {terminal_id} not found"
        )

    # Map terminal status to operation status
    operation_status = "pending"
    if terminal.status == TerminalStatus.STARTED:
        operation_status = "completed"
    elif terminal.status == TerminalStatus.FAILED:
        operation_status = "failed"
    elif terminal.status in [TerminalStatus.STARTING, TerminalStatus.PENDING]:
        operation_status = "in_progress"

    return OperationResponse(
        operation_id=terminal.id,
        status=operation_status,
        terminal_id=terminal.id,
        message=terminal.error_message
    )
