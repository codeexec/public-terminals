"""
Database session management (Asynchronous)
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging

from src.config import settings
from src.database.models import Base

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_maker = None


def get_engine() -> AsyncEngine:
    """Get or create the async SQLAlchemy engine"""
    global _engine
    if _engine is None:
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("sqlite://"):
            db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
            
        # SQLite doesn't support pool_size and max_overflow
        is_sqlite = db_url.startswith("sqlite")
        engine_kwargs = {
            "echo": settings.LOG_LEVEL == "DEBUG",
        }
        if not is_sqlite:
            engine_kwargs.update({
                "pool_pre_ping": True,
                "pool_size": 10,
                "max_overflow": 20,
            })
            
        _engine = create_async_engine(db_url, **engine_kwargs)
    return _engine


def get_session_maker():
    """Get or create the async session maker"""
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_maker


async def init_db():
    """Initialize database - create all tables asynchronously"""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to get async database session
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database session
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
