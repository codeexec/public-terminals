from typing import List, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import Sandbox
from src.constants import SandboxStatus, SandboxType


class SandboxRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, sandbox_id: str) -> Optional[Sandbox]:
        """Fetch a sandbox by its ID, ignoring soft-deleted ones by default."""
        stmt = select(Sandbox).where(Sandbox.id == sandbox_id, Sandbox.deleted_at.is_(None))
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_by_id_include_deleted(self, sandbox_id: str) -> Optional[Sandbox]:
        """Fetch a sandbox by its ID, including soft-deleted ones."""
        stmt = select(Sandbox).where(Sandbox.id == sandbox_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_by_container_name(self, container_name: str) -> Optional[Sandbox]:
        """Fetch a sandbox by its container name, ignoring soft-deleted ones by default."""
        stmt = select(Sandbox).where(Sandbox.container_name == container_name, Sandbox.deleted_at.is_(None))
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def create(self, sandbox: Sandbox) -> Sandbox:
        """Add a new sandbox to the session and flush."""
        self.db.add(sandbox)
        await self.db.flush()  # to populate id/created_at
        return sandbox

    async def save(self, sandbox: Sandbox) -> Sandbox:
        """Save/flush modifications on a sandbox."""
        await self.db.flush()
        return sandbox

    async def count_active_by_user(self, user_id: str) -> int:
        """Count the active sandboxes (PENDING, STARTING, STARTED) for a user."""
        stmt = (
            select(func.count(Sandbox.id))
            .where(
                Sandbox.user_id == user_id,
                Sandbox.status.in_([SandboxStatus.PENDING, SandboxStatus.STARTING, SandboxStatus.STARTED]),
                Sandbox.deleted_at.is_(None)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def count_active_total(self) -> int:
        """Count all active sandboxes in the system."""
        stmt = (
            select(func.count(Sandbox.id))
            .where(
                Sandbox.status.in_([SandboxStatus.PENDING, SandboxStatus.STARTING, SandboxStatus.STARTED]),
                Sandbox.deleted_at.is_(None)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def list_active(self) -> List[Sandbox]:
        """List all active sandboxes."""
        stmt = (
            select(Sandbox)
            .where(
                Sandbox.status.in_([SandboxStatus.PENDING, SandboxStatus.STARTING, SandboxStatus.STARTED]),
                Sandbox.deleted_at.is_(None)
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_user(self, user_id: str) -> List[Sandbox]:
        """List active sandboxes for a specific user, ordered by created_at desc."""
        stmt = (
            select(Sandbox)
            .where(
                Sandbox.user_id == user_id,
                Sandbox.deleted_at.is_(None)
            )
            .order_by(Sandbox.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[SandboxStatus] = None,
        type: Optional[SandboxType] = None,
        user_id: Optional[str] = None,
    ) -> List[Sandbox]:
        """List all sandboxes with pagination and optional filtering."""
        stmt = select(Sandbox).where(Sandbox.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Sandbox.status == status)
        if type:
            stmt = stmt.where(Sandbox.type == type)
        if user_id:
            stmt = stmt.where(Sandbox.user_id == user_id)
        stmt = stmt.order_by(Sandbox.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_all(
        self,
        status: Optional[SandboxStatus] = None,
        type: Optional[SandboxType] = None,
        user_id: Optional[str] = None,
    ) -> int:
        """Count all sandboxes (excluding soft-deleted ones) with optional filtering."""
        stmt = select(func.count(Sandbox.id)).where(Sandbox.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Sandbox.status == status)
        if type:
            stmt = stmt.where(Sandbox.type == type)
        if user_id:
            stmt = stmt.where(Sandbox.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_expired(self) -> List[Sandbox]:
        """Get all running/active sandboxes that have expired."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(Sandbox)
            .where(
                Sandbox.status.in_([SandboxStatus.PENDING, SandboxStatus.STARTING, SandboxStatus.STARTED]),
                Sandbox.expires_at.is_not(None),
                Sandbox.expires_at < now,
                Sandbox.deleted_at.is_(None)
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_idle(self, idle_timeout_minutes: int) -> List[Sandbox]:
        """Get all started sandboxes that have been idle too long."""
        threshold = datetime.now(timezone.utc) - timedelta(minutes=idle_timeout_minutes)
        stmt = (
            select(Sandbox)
            .where(
                Sandbox.status == SandboxStatus.STARTED,
                func.coalesce(Sandbox.last_activity_at, Sandbox.created_at) < threshold,
                Sandbox.deleted_at.is_(None)
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete(self, sandbox_id: str) -> bool:
        """Mark a sandbox as deleted (soft delete)."""
        sandbox = await self.get_by_id(sandbox_id)
        if sandbox:
            sandbox.deleted_at = datetime.now(timezone.utc)
            await self.save(sandbox)
            return True
        return False
