"""
Pydantic schemas for API request/response validation
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from datetime import datetime
from src.database.models import SandboxStatus, SandboxType
import re


class SandboxCreate(BaseModel):
    """Request schema for creating a sandbox"""

    type: SandboxType = Field(
        default=SandboxType.TERMINAL,
        description="Type of sandbox to create",
    )

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, v):
        if isinstance(v, str):
            return v.upper()
        return v
    use_gpu: Optional[bool] = Field(
        default=None,
        description="Request a GPU-enabled sandbox (only available on GKE Autopilot)",
    )


class SandboxResponse(BaseModel):
    """Response schema for sandbox details"""

    id: str
    user_id: Optional[str] = None
    type: SandboxType
    status: SandboxStatus

    @field_validator("type", "status", mode="before")
    @classmethod
    def validate_enums(cls, v):
        if isinstance(v, str):
            return v.upper()
        if hasattr(v, "value"):
            return v.value.upper()
        return v

    tunnel_url: Optional[str] = None
    container_id: Optional[str] = None
    container_name: Optional[str] = None
    host_port: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    error_message: Optional[str] = None
    gpu_enabled: bool = False
    gpu_type: Optional[str] = None
    gpu_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class SandboxListResponse(BaseModel):
    """Response schema for listing sandboxes"""

    sandboxes: list[SandboxResponse]
    total: int


class SandboxCallbackRequest(BaseModel):
    """Request schema for container callback"""

    sandbox_id: Optional[str] = Field(None, min_length=1, max_length=255)
    terminal_id: Optional[str] = Field(None, min_length=1, max_length=255)
    type: Optional[str] = None  # Using str instead of Enum to avoid validation errors
    tunnel_url: Optional[str] = Field(None, max_length=512)
    status: Optional[str] = None  # Using str instead of Enum
    error_message: Optional[str] = Field(None, max_length=1024)
    message: Optional[str] = Field(None, max_length=1024)
    idle_seconds: Optional[int] = None
    cpu_percent: Optional[float] = Field(None, ge=0, le=100)
    memory_mb: Optional[float] = Field(None, ge=0, le=100000)
    memory_percent: Optional[float] = Field(None, ge=0, le=100)

    model_config = ConfigDict(extra="ignore")

    @field_validator("tunnel_url")
    @classmethod
    def validate_tunnel_url(cls, v):
        if v is not None and v:
            if not re.match(r"^https?://", v):
                raise ValueError("tunnel_url must use http or https protocol")
        return v


class OperationResponse(BaseModel):
    """Response schema for long-running operations"""

    operation_id: str
    status: str
    sandbox_id: Optional[str] = None
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Response schema for health check"""

    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"
