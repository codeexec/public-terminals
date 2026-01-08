"""
SQLAlchemy database models
"""
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import uuid
import enum

Base = declarative_base()


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

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(SQLEnum(TerminalStatus), default=TerminalStatus.PENDING, nullable=False)
    user_id = Column(String(36), nullable=True, index=True)
    tunnel_url = Column(String(512), nullable=True)
    container_id = Column(String(255), nullable=True)
    container_name = Column(String(255), nullable=True)
    host_port = Column(String(10), nullable=True)  # Port on host mapped to container's 8888

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Error tracking
    error_message = Column(String(1024), nullable=True)

    def __repr__(self):
        return f"<Terminal(id={self.id}, status={self.status}, tunnel_url={self.tunnel_url})>"

    def set_expiry(self, hours: int = 24):
        """Set the expiry time for the terminal"""
        self.expires_at = datetime.utcnow() + timedelta(hours=hours)

    def is_expired(self) -> bool:
        """Check if terminal has expired"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def to_dict(self):
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
