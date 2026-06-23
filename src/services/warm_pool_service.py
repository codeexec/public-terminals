"""
Warm Pool Service - Manages pre-warmed sandbox containers for instant startup
"""

import asyncio
import logging
import uuid
import threading
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

from src.config import settings
from src.services.container_service import get_container_service
from src.exceptions import ContainerError

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
    """

    _instance: Optional["WarmPoolService"] = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._pool: Dict[str, WarmContainer] = {}  # warm_id -> WarmContainer (non-GPU)
        self._gpu_pool: Dict[str, WarmContainer] = {}  # warm_id -> WarmContainer (GPU)
        self._lock = asyncio.Lock()
        self._replenish_task: Optional[asyncio.Task] = None
        self._running = False

        # Configuration
        self.pool_size = getattr(settings, "WARM_POOL_SIZE", 2)
        self.pool_enabled = getattr(settings, "WARM_POOL_ENABLED", True)

        # GPU warm pool configuration
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
            with cls._instance_lock:
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
            
            # Helper for cleanup
            async def cleanup_pool(pool: Dict[str, WarmContainer], name: str):
                for warm_id, container in list(pool.items()):
                    try:
                        await container_service.delete_sandbox_container(
                            container.container_id
                        )
                        logger.info(f"Cleaned up {name} warm container {warm_id}")
                    except Exception as e:
                        logger.error(f"Failed to cleanup {name} warm container {warm_id}: {e}")
                pool.clear()

            await cleanup_pool(self._pool, "standard")
            await cleanup_pool(self._gpu_pool, "GPU")

        logger.info("Warm pool service stopped")

    async def _replenish_loop(self):
        """Background task that maintains the pool size"""
        while self._running:
            try:
                await self._replenish_pool()
            except Exception as e:
                logger.error(f"Error in replenish loop: {e}")

            # Check periodically
            await asyncio.sleep(settings.WARM_POOL_REPLENISH_INTERVAL)

    async def _cleanup_dead_containers(self):
        """Remove containers from pools that no longer exist"""
        container_service = get_container_service()

        async with self._lock:
            # Cleanup pools
            for pool, name in [(self._pool, "standard"), (self._gpu_pool, "GPU")]:
                dead_containers = []
                for warm_id, container in pool.items():
                    try:
                        status = await container_service.get_container_status(
                            container.container_id
                        )
                        # Normalize status checks
                        if status is None or status.lower() not in (
                            "running",
                            "created",
                            "pending",
                        ):
                            dead_containers.append(warm_id)
                    except Exception:
                        dead_containers.append(warm_id)

                for warm_id in dead_containers:
                    del pool[warm_id]
                    logger.info(f"Removed dead {name} warm container {warm_id} from pool")

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
            logger.info(f"Replenishing warm pool: current={current_size}, needed={needed}")
            # Create containers in parallel (up to WARM_POOL_MAX_PARALLEL_CREATES at a time)
            for _ in range(min(needed, settings.WARM_POOL_MAX_PARALLEL_CREATES)):
                tasks.append(self._create_warm_container(use_gpu=False))

        # Replenish GPU pool
        if self.gpu_enabled:
            async with self._lock:
                gpu_current_size = len(self._gpu_pool)
                gpu_needed = self.gpu_pool_size - gpu_current_size

            if gpu_needed > 0:
                logger.info(f"Replenishing GPU warm pool: current={gpu_current_size}, needed={gpu_needed}")
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
            # Create container
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
            logger.info(f"Created {gpu_label}warm container {warm_id}: {result['container_id'][:12]}")
            return warm_container

        except ContainerError as e:
            gpu_label = "GPU " if use_gpu else ""
            logger.error(f"Failed to create {gpu_label}warm container {warm_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating warm container {warm_id}: {e}")
            return None

    async def update_tunnel_url(self, warm_id: str, tunnel_url: str) -> bool:
        """Update tunnel URL for a warm container"""
        async with self._lock:
            # Check both pools
            for pool, name in [(self._pool, "standard"), (self._gpu_pool, "GPU")]:
                if warm_id in pool:
                    pool[warm_id].tunnel_url = tunnel_url
                    pool[warm_id].ready = True
                    logger.info(f"{name} warm container {warm_id} ready with tunnel: {tunnel_url}")
                    return True
        return False

    async def claim_container(self, use_gpu: bool = False) -> Optional[WarmContainer]:
        """Claim a ready warm container"""
        pool = self._gpu_pool if use_gpu else self._pool
        gpu_label = "GPU " if use_gpu else ""

        async with self._lock:
            for warm_id, container in list(pool.items()):
                if container.ready and container.tunnel_url:
                    del pool[warm_id]
                    logger.info(f"Claimed {gpu_label}warm container {warm_id} with tunnel {container.tunnel_url}")
                    return container

        return None

    async def get_pool_status(self) -> Dict[str, Any]:
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
                "gpu_enabled": self.gpu_enabled,
                "gpu_target_size": self.gpu_pool_size,
                "gpu_total_containers": gpu_total,
                "gpu_ready_containers": gpu_ready,
                "gpu_warming_containers": gpu_total - gpu_ready,
            }

    def is_warm_id(self, sandbox_id: str) -> bool:
        """Check if a sandbox_id is a warm pool ID"""
        return sandbox_id.startswith("warm-")

    async def return_container(self, warm_container: WarmContainer):
        """Return an unclaimed container back to pool"""
        async with self._lock:
            pool = self._gpu_pool if warm_container.gpu_enabled else self._pool
            if warm_container.warm_id not in pool:
                pool[warm_container.warm_id] = warm_container
                logger.info(f"Returned {'GPU ' if warm_container.gpu_enabled else ''}warm container {warm_container.warm_id} to pool")


def get_warm_pool_service() -> WarmPoolService:
    """Get the warm pool service singleton"""
    return WarmPoolService.get_instance()
