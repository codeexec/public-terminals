"""
Warm Pool Service - Manages pre-warmed terminal containers for instant startup

This service maintains a pool of pre-started containers that are ready to be
assigned to users immediately, eliminating cold start latency.

Architecture:
1. Warm containers start with a temporary "warm-{uuid}" identifier
2. They report their tunnel URL to a special warm pool callback endpoint
3. When a user requests a terminal, we "claim" a warm container
4. The warm container's tunnel URL is transferred to the new terminal record
5. A background task continuously replenishes the pool
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional
from dataclasses import dataclass, field

from src.config import settings
from src.services.container_service import get_container_service

logger = logging.getLogger(__name__)


@dataclass
class WarmContainer:
    """Represents a pre-warmed container ready to be claimed"""

    warm_id: str  # The temporary ID used during warm-up
    container_id: str
    container_name: str
    host_port: Optional[str] = None
    tunnel_url: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ready: bool = False


class WarmPoolService:
    """
    Manages a pool of pre-warmed containers for instant terminal startup.

    The pool maintains WARM_POOL_SIZE containers that are fully initialized
    and ready to serve users immediately.
    """

    _instance: Optional["WarmPoolService"] = None

    def __init__(self):
        self._pool: Dict[str, WarmContainer] = {}  # warm_id -> WarmContainer
        self._lock = asyncio.Lock()
        self._replenish_task: Optional[asyncio.Task] = None
        self._running = False

        # Configuration
        self.pool_size = getattr(settings, "WARM_POOL_SIZE", 3)
        self.pool_enabled = getattr(settings, "WARM_POOL_ENABLED", True)

        logger.info(
            f"WarmPoolService initialized (size={self.pool_size}, enabled={self.pool_enabled})"
        )

    @classmethod
    def get_instance(cls) -> "WarmPoolService":
        """Get singleton instance of WarmPoolService"""
        if cls._instance is None:
            cls._instance = WarmPoolService()
        return cls._instance

    async def start(self):
        """Start the warm pool service and background replenishment task"""
        if not self.pool_enabled:
            logger.info("Warm pool is disabled, skipping start")
            return

        if self._running:
            return

        self._running = True
        self._replenish_task = asyncio.create_task(self._replenish_loop())
        logger.info("Warm pool service started")

    async def stop(self):
        """Stop the warm pool service and cleanup containers"""
        self._running = False

        if self._replenish_task:
            self._replenish_task.cancel()
            try:
                await self._replenish_task
            except asyncio.CancelledError:
                pass

        # Cleanup all warm containers
        async with self._lock:
            container_service = get_container_service()
            for warm_id, container in list(self._pool.items()):
                try:
                    await container_service.delete_terminal_container(
                        container.container_id
                    )
                    logger.info(f"Cleaned up warm container {warm_id}")
                except Exception as e:
                    logger.error(f"Failed to cleanup warm container {warm_id}: {e}")
            self._pool.clear()

        logger.info("Warm pool service stopped")

    async def _replenish_loop(self):
        """Background task that maintains the pool size"""
        while self._running:
            try:
                await self._replenish_pool()
            except Exception as e:
                logger.error(f"Error in replenish loop: {e}")

            # Check every 5 seconds
            await asyncio.sleep(5)

    async def _cleanup_dead_containers(self):
        """Remove containers from pool that no longer exist"""
        container_service = get_container_service()
        dead_containers = []

        async with self._lock:
            for warm_id, container in self._pool.items():
                try:
                    status = await container_service.get_container_status(
                        container.container_id
                    )
                    if status is None or status not in ("running", "created"):
                        dead_containers.append(warm_id)
                except Exception:
                    dead_containers.append(warm_id)

            # Remove dead containers from pool
            for warm_id in dead_containers:
                del self._pool[warm_id]
                logger.info(f"Removed dead warm container {warm_id} from pool")

    async def _replenish_pool(self):
        """Add containers to the pool if below target size"""
        # First, check for dead containers and remove them
        await self._cleanup_dead_containers()

        async with self._lock:
            current_size = len(self._pool)
            needed = self.pool_size - current_size

        if needed <= 0:
            return

        logger.info(f"Replenishing warm pool: current={current_size}, needed={needed}")

        # Create containers in parallel (up to 2 at a time to avoid overload)
        tasks = []
        for _ in range(min(needed, 2)):
            tasks.append(self._create_warm_container())

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Failed to create warm container: {result}")

    async def _create_warm_container(self) -> Optional[WarmContainer]:
        """Create a single warm container"""
        warm_id = f"warm-{uuid.uuid4().hex[:12]}"
        container_service = get_container_service()

        try:
            # Create container with warm_id as the terminal_id
            result = await container_service.create_terminal_container(warm_id)

            warm_container = WarmContainer(
                warm_id=warm_id,
                container_id=result["container_id"],
                container_name=result["container_name"],
                host_port=result.get("host_port"),
            )

            async with self._lock:
                self._pool[warm_id] = warm_container

            logger.info(
                f"Created warm container {warm_id}: {result['container_id'][:12]}"
            )
            return warm_container

        except Exception as e:
            logger.error(f"Failed to create warm container {warm_id}: {e}")
            return None

    async def update_tunnel_url(self, warm_id: str, tunnel_url: str) -> bool:
        """
        Update tunnel URL for a warm container (called by callback endpoint).
        Returns True if the warm container exists and was updated.
        """
        async with self._lock:
            if warm_id in self._pool:
                self._pool[warm_id].tunnel_url = tunnel_url
                self._pool[warm_id].ready = True
                logger.info(f"Warm container {warm_id} ready with tunnel: {tunnel_url}")
                return True
        return False

    async def claim_container(self) -> Optional[WarmContainer]:
        """
        Claim a ready warm container from the pool.
        Returns the container if one is available and ready, None otherwise.
        """
        async with self._lock:
            # Find a ready container
            for warm_id, container in list(self._pool.items()):
                if container.ready and container.tunnel_url:
                    # Remove from pool and return
                    del self._pool[warm_id]
                    logger.info(
                        f"Claimed warm container {warm_id} with tunnel {container.tunnel_url}"
                    )
                    return container

        return None

    async def get_pool_status(self) -> Dict:
        """Get current pool status for monitoring"""
        async with self._lock:
            total = len(self._pool)
            ready = sum(1 for c in self._pool.values() if c.ready)

            return {
                "enabled": self.pool_enabled,
                "target_size": self.pool_size,
                "total_containers": total,
                "ready_containers": ready,
                "warming_containers": total - ready,
            }

    def is_warm_id(self, terminal_id: str) -> bool:
        """Check if a terminal_id is a warm pool ID"""
        return terminal_id.startswith("warm-")

    async def return_container(self, warm_container: WarmContainer):
        """
        Return an unclaimed container back to the pool.
        Used when terminal creation fails after claiming.
        """
        async with self._lock:
            if warm_container.warm_id not in self._pool:
                self._pool[warm_container.warm_id] = warm_container
                logger.info(f"Returned warm container {warm_container.warm_id} to pool")


# Convenience function to get the service instance
def get_warm_pool_service() -> WarmPoolService:
    """Get the warm pool service singleton"""
    return WarmPoolService.get_instance()
