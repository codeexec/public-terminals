"""
Pydantic schemas for API request/response validation
"""

from pydantic import BaseModel, Field, field_validator, HttpUrl
from typing import Optional
from datetime import datetime
from src.database.models import TerminalStatus
import re


class TerminalCreate(BaseModel):
    """Request schema for creating a terminal"""

    pass  # No input required for basic creation


class TerminalResponse(BaseModel):
    """Response schema for terminal details"""

    id: str
    user_id: Optional[str] = None
    status: TerminalStatus
    tunnel_url: Optional[str] = None
    container_id: Optional[str] = None
    container_name: Optional[str] = None
    host_port: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class TerminalListResponse(BaseModel):
    """Response schema for listing terminals"""

    terminals: list[TerminalResponse]
    total: int


class TerminalCallbackRequest(BaseModel):
    """Request schema for container callback"""

    terminal_id: str = Field(..., min_length=1, max_length=255)
    tunnel_url: Optional[str] = Field(None, max_length=512)
    status: Optional[TerminalStatus] = None
    error_message: Optional[str] = Field(None, max_length=1024)
    cpu_percent: Optional[float] = Field(None, ge=0, le=100)
    memory_mb: Optional[float] = Field(None, ge=0, le=100000)  # Max 100GB
    memory_percent: Optional[float] = Field(None, ge=0, le=100)

    @field_validator('tunnel_url')
    @classmethod
    def validate_tunnel_url(cls, v):
        if v is not None and v:
            # Validate URL format and protocol
            if not re.match(r'^https?://', v):
                raise ValueError('tunnel_url must use http or https protocol')
            # Additional validation: ensure reasonable URL length and format
            if len(v) > 512:
                raise ValueError('tunnel_url is too long (max 512 characters)')
        return v

    @field_validator('terminal_id')
    @classmethod
    def validate_terminal_id(cls, v):
        # Validate terminal_id format (UUID-like or alphanumeric with hyphens)
        if not re.match(r'^[a-zA-Z0-9-]+$', v):
            raise ValueError('terminal_id contains invalid characters')
        return v


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
