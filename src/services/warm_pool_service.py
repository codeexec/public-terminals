"""
Warm Pool Service - Manages pre-warmed sandbox containers for instant startup

This service maintains a pool of pre-started containers that are ready to be
assigned to users immediately, eliminating cold start latency.

Architecture:
1. Warm containers start with a temporary "warm-{uuid}" identifier
2. They report their tunnel URL to a special warm pool callback endpoint
3. When a user requests a sandbox, we "claim" a warm container
4. The warm container's tunnel URL is transferred to the new sandbox record
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
    gpu_enabled: bool = False  # Whether this is a GPU-enabled container


class WarmPoolService:
    """
    Manages a pool of pre-warmed containers for instant sandbox startup.

    The pool maintains WARM_POOL_SIZE containers that are fully initialized
    and ready to serve users immediately.
    """

    _instance: Optional["WarmPoolService"] = None

    def __init__(self):
        self._pool: Dict[str, WarmContainer] = {}  # warm_id -> WarmContainer (non-GPU)
        self._gpu_pool: Dict[str, WarmContainer] = {}  # warm_id -> WarmContainer (GPU)
        self._lock = asyncio.Lock()
        self._replenish_task: Optional[asyncio.Task] = None
        self._running = False

        # Configuration
        self.pool_size = getattr(settings, "WARM_POOL_SIZE", 2)
        self.pool_enabled = getattr(settings, "WARM_POOL_ENABLED", True)

        # GPU warm pool configuration (smaller due to cost)
        self.gpu_pool_size = getattr(settings, "WARM_POOL_GPU_SIZE", 1)
        self.gpu_enabled = getattr(
            settings, "GKE_AUTOPILOT_ENABLED", False
        ) and getattr(settings, "GPU_ENABLED", False)

        logger.info(
            f"WarmPoolService initialized (size={self.pool_size}, "
            f"gpu_size={self.gpu_pool_size}, gpu_enabled={self.gpu_enabled})"
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

        # Cleanup all warm containers (both pools)
        async with self._lock:
            container_service = get_container_service()
            # Cleanup non-GPU pool
            for warm_id, container in list(self._pool.items()):
                try:
                    await container_service.delete_sandbox_container(
                        container.container_id
                    )
                    logger.info(f"Cleaned up warm container {warm_id}")
                except Exception as e:
                    logger.error(f"Failed to cleanup warm container {warm_id}: {e}")
            self._pool.clear()

            # Cleanup GPU pool
            for warm_id, container in list(self._gpu_pool.items()):
                try:
                    await container_service.delete_sandbox_container(
                        container.container_id
                    )
                    logger.info(f"Cleaned up GPU warm container {warm_id}")
                except Exception as e:
                    logger.error(f"Failed to cleanup GPU warm container {warm_id}: {e}")
            self._gpu_pool.clear()

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
        """Remove containers from pools that no longer exist"""
        container_service = get_container_service()

        async with self._lock:
            # Cleanup non-GPU pool
            dead_containers = []
            for warm_id, container in self._pool.items():
                try:
                    status = await container_service.get_container_status(
                        container.container_id
                    )
                    if status is None or status not in (
                        "running",
                        "created",
                        "Running",
                        "Pending",
                    ):
                        dead_containers.append(warm_id)
                except Exception:
                    dead_containers.append(warm_id)

            for warm_id in dead_containers:
                del self._pool[warm_id]
                logger.info(f"Removed dead warm container {warm_id} from pool")

            # Cleanup GPU pool
            dead_gpu_containers = []
            for warm_id, container in self._gpu_pool.items():
                try:
                    status = await container_service.get_container_status(
                        container.container_id
                    )
                    if status is None or status not in (
                        "running",
                        "created",
                        "Running",
                        "Pending",
                    ):
                        dead_gpu_containers.append(warm_id)
                except Exception:
                    dead_gpu_containers.append(warm_id)

            for warm_id in dead_gpu_containers:
                del self._gpu_pool[warm_id]
                logger.info(f"Removed dead GPU warm container {warm_id} from pool")

    async def _replenish_pool(self):
        """Add containers to pools if below target size"""
        # First, check for dead containers and remove them
        await self._cleanup_dead_containers()

        tasks = []

        # Replenish non-GPU pool
        async with self._lock:
            current_size = len(self._pool)
            needed = self.pool_size - current_size

        if needed > 0:
            logger.info(
                f"Replenishing warm pool: current={current_size}, needed={needed}"
            )
            # Create containers in parallel (up to 2 at a time to avoid overload)
            for _ in range(min(needed, 2)):
                tasks.append(self._create_warm_container(use_gpu=False))

        # Replenish GPU pool (if enabled)
        if self.gpu_enabled:
            async with self._lock:
                gpu_current_size = len(self._gpu_pool)
                gpu_needed = self.gpu_pool_size - gpu_current_size

            if gpu_needed > 0:
                logger.info(
                    f"Replenishing GPU warm pool: current={gpu_current_size}, needed={gpu_needed}"
                )
                # Create GPU containers (one at a time due to cost)
                for _ in range(min(gpu_needed, 1)):
                    tasks.append(self._create_warm_container(use_gpu=True))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Failed to create warm container: {result}")

    async def _create_warm_container(
        self, use_gpu: bool = False
    ) -> Optional[WarmContainer]:
        """Create a single warm container (GPU or non-GPU)"""
        prefix = "warm-gpu-" if use_gpu else "warm-"
        warm_id = f"{prefix}{uuid.uuid4().hex[:12]}"
        container_service = get_container_service()

        try:
            # Create container with warm_id as the sandbox_id
            result = await container_service.create_sandbox_container(
                warm_id, use_gpu=use_gpu
            )

            warm_container = WarmContainer(
                warm_id=warm_id,
                container_id=result["container_id"],
                container_name=result["container_name"],
                host_port=result.get("host_port"),
                gpu_enabled=use_gpu,
            )

            async with self._lock:
                if use_gpu:
                    self._gpu_pool[warm_id] = warm_container
                else:
                    self._pool[warm_id] = warm_container

            gpu_label = "GPU " if use_gpu else ""
            logger.info(
                f"Created {gpu_label}warm container {warm_id}: {result['container_id'][:12]}"
            )
            return warm_container

        except Exception as e:
            gpu_label = "GPU " if use_gpu else ""
            logger.error(f"Failed to create {gpu_label}warm container {warm_id}: {e}")
            return None

    async def update_tunnel_url(self, warm_id: str, tunnel_url: str) -> bool:
        """
        Update tunnel URL for a warm container (called by callback endpoint).
        Returns True if the warm container exists and was updated.
        """
        async with self._lock:
            # Check non-GPU pool
            if warm_id in self._pool:
                self._pool[warm_id].tunnel_url = tunnel_url
                self._pool[warm_id].ready = True
                logger.info(f"Warm container {warm_id} ready with tunnel: {tunnel_url}")
                return True
            # Check GPU pool
            if warm_id in self._gpu_pool:
                self._gpu_pool[warm_id].tunnel_url = tunnel_url
                self._gpu_pool[warm_id].ready = True
                logger.info(
                    f"GPU warm container {warm_id} ready with tunnel: {tunnel_url}"
                )
                return True
        return False

    async def claim_container(self, use_gpu: bool = False) -> Optional[WarmContainer]:
        """
        Claim a ready warm container from the appropriate pool.

        Args:
            use_gpu: Whether to claim a GPU-enabled container

        Returns:
            The container if one is available and ready, None otherwise.
        """
        pool = self._gpu_pool if use_gpu else self._pool
        gpu_label = "GPU " if use_gpu else ""

        async with self._lock:
            # Find a ready container in the appropriate pool
            for warm_id, container in list(pool.items()):
                if container.ready and container.tunnel_url:
                    # Remove from pool and return
                    del pool[warm_id]
                    logger.info(
                        f"Claimed {gpu_label}warm container {warm_id} with tunnel {container.tunnel_url}"
                    )
                    return container

        return None

    async def get_pool_status(self) -> Dict:
        """Get current pool status for monitoring"""
        async with self._lock:
            total = len(self._pool)
            ready = sum(1 for c in self._pool.values() if c.ready)

            gpu_total = len(self._gpu_pool)
            gpu_ready = sum(1 for c in self._gpu_pool.values() if c.ready)

            return {
                "enabled": self.pool_enabled,
                "target_size": self.pool_size,
                "total_containers": total,
                "ready_containers": ready,
                "warming_containers": total - ready,
                # GPU pool stats
                "gpu_enabled": self.gpu_enabled,
                "gpu_target_size": self.gpu_pool_size,
                "gpu_total_containers": gpu_total,
                "gpu_ready_containers": gpu_ready,
                "gpu_warming_containers": gpu_total - gpu_ready,
            }

    def is_warm_id(self, sandbox_id: str) -> bool:
        """Check if a sandbox_id is a warm pool ID (GPU or non-GPU)"""
        return sandbox_id.startswith("warm-")

    async def return_container(self, warm_container: WarmContainer):
        """
        Return an unclaimed container back to the appropriate pool.
        Used when sandbox creation fails after claiming.
        """
        async with self._lock:
            if warm_container.gpu_enabled:
                if warm_container.warm_id not in self._gpu_pool:
                    self._gpu_pool[warm_container.warm_id] = warm_container
                    logger.info(
                        f"Returned GPU warm container {warm_container.warm_id} to pool"
                    )
            else:
                if warm_container.warm_id not in self._pool:
                    self._pool[warm_container.warm_id] = warm_container
                    logger.info(
                        f"Returned warm container {warm_container.warm_id} to pool"
                    )


# Convenience function to get the service instance
def get_warm_pool_service() -> WarmPoolService:
    """Get the warm pool service singleton"""
    return WarmPoolService.get_instance()
