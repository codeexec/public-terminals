"""
Pydantic schemas for API request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from src.database.models import TerminalStatus


class TerminalCreate(BaseModel):
    """Request schema for creating a terminal"""
    pass  # No input required for basic creation


class TerminalResponse(BaseModel):
    """Response schema for terminal details"""
    id: str
    status: TerminalStatus
    tunnel_url: Optional[str] = None
    container_id: Optional[str] = None
    container_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class TerminalListResponse(BaseModel):
    """Response schema for listing terminals"""
    terminals: list[TerminalResponse]
    total: int


class TerminalCallbackRequest(BaseModel):
    """Request schema for container callback"""
    terminal_id: str
    tunnel_url: Optional[str] = None
    status: Optional[TerminalStatus] = None
    error_message: Optional[str] = None


class OperationResponse(BaseModel):
    """Response schema for long-running operations"""
    operation_id: str
    status: str
    terminal_id: Optional[str] = None
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Response schema for health check"""
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"
