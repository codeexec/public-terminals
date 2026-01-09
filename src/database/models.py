"""
SQLAlchemy database models
"""

from sqlalchemy import String, DateTime, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime, timedelta, timezone
import uuid
import enum


class Base(DeclarativeBase):
    pass


class TerminalStatus(str, enum.Enum):
    """Terminal status enumeration"""

    PENDING = "pending"
    STARTING = "starting"
    STARTED = "started"
    STOPPED = "stopped"
    EXPIRED = "expired"
    FAILED = "failed"


class Terminal(Base):
    """Terminal instance model"""

    __tablename__ = "terminals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    status: Mapped[TerminalStatus] = mapped_column(
        SQLEnum(TerminalStatus), default=TerminalStatus.PENDING, nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    tunnel_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    container_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    container_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host_port: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # Port on host mapped to container's 8888

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    def __repr__(self) -> str:
        return f"<Terminal(id={self.id}, status={self.status}, tunnel_url={self.tunnel_url})>"

    def set_expiry(self, hours: int = 24) -> None:
        """Set the expiry time for the terminal"""
        self.expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)

    def is_expired(self) -> bool:
        """Check if terminal has expired"""
        if self.expires_at is None:
            return False
        # Ensure we are comparing offset-aware datetimes
        now = datetime.now(timezone.utc)
        if self.expires_at.tzinfo is None:
            # Fallback if DB returns naive (though it shouldn't with timezone=True)
            return now.replace(tzinfo=None) > self.expires_at
        return now > self.expires_at

    def is_idle(self, idle_timeout_minutes: int) -> bool:
        """Check if terminal has been idle for longer than the timeout"""
        if self.last_activity_at is None:
            # If never tracked activity, use created_at as fallback
            check_time = self.created_at
        else:
            check_time = self.last_activity_at

        if check_time is None:
            return False

        # Ensure we are comparing offset-aware datetimes
        now = datetime.now(timezone.utc)
        idle_threshold = now - timedelta(minutes=idle_timeout_minutes)

        if check_time.tzinfo is None:
            # Fallback if DB returns naive
            return check_time < idle_threshold.replace(tzinfo=None)
        return check_time < idle_threshold

    def set_last_activity(self) -> None:
        """Update the last activity timestamp to now"""
        self.last_activity_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "status": self.status.value,
            "tunnel_url": self.tunnel_url,
            "container_id": self.container_id,
            "container_name": self.container_name,
            "host_port": self.host_port,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "error_message": self.error_message,
        }
