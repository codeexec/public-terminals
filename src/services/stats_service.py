"""
Resource statistics service for monitoring system and container metrics
"""

import logging
import psutil
from typing import Dict, Optional
from datetime import datetime, timezone


logger = logging.getLogger(__name__)


class StatsService:
    """Service for collecting system and container resource statistics"""

    def __init__(self):
        """Initialize stats service with in-memory cache"""
        # In-memory cache for container stats: {container_id: {stats, timestamp}}
        self._stats_cache: Dict[str, Dict] = {}

    @staticmethod
    def get_system_stats() -> Dict:
        """
        Get overall system CPU and memory statistics

        Returns:
            Dictionary with system CPU and memory metrics
        """
        try:
            # Get CPU usage (percentage)
            # Use small interval to avoid blocking event loop for too long
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # Get memory usage
            memory = psutil.virtual_memory()
            memory_total_gb = memory.total / (1024**3)
            memory_used_gb = memory.used / (1024**3)
            memory_percent = memory.percent

            # Get disk usage
            disk = psutil.disk_usage("/")
            disk_total_gb = disk.total / (1024**3)
            disk_used_gb = disk.used / (1024**3)
            disk_percent = disk.percent

            return {
                "cpu": {
                    "percent": round(cpu_percent, 1),
                    "cores": psutil.cpu_count(),
                },
                "memory": {
                    "total_gb": round(memory_total_gb, 2),
                    "used_gb": round(memory_used_gb, 2),
                    "percent": round(memory_percent, 1),
                },
                "disk": {
                    "total_gb": round(disk_total_gb, 2),
                    "used_gb": round(disk_used_gb, 2),
                    "percent": round(disk_percent, 1),
                },
            }
        except Exception as e:
            logger.error(f"Failed to get system stats: {e}")
            return {
                "cpu": {"percent": 0, "cores": 0},
                "memory": {"total_gb": 0, "used_gb": 0, "percent": 0},
                "disk": {"total_gb": 0, "used_gb": 0, "percent": 0},
            }

    def update_container_stats(
        self,
        container_id: str,
        cpu_percent: float,
        memory_mb: float,
        memory_percent: float,
    ):
        """
        Update container statistics in cache (called by callback endpoint)

        Args:
            container_id: Docker container ID
            cpu_percent: CPU usage percentage
            memory_mb: Memory usage in MB
            memory_percent: Memory usage percentage
        """
        if not container_id:
            return

        self._stats_cache[container_id] = {
            "cpu_percent": round(cpu_percent, 1),
            "memory_mb": round(memory_mb, 1),
            "memory_percent": round(memory_percent, 1),
            "timestamp": datetime.now(timezone.utc),
        }

        logger.debug(f"Updated stats cache for container {container_id}")

    async def get_container_stats(self, container_id: str) -> Optional[Dict]:
        """
        Get CPU and memory statistics for a specific container from cache

        Args:
            container_id: Docker container ID

        Returns:
            Dictionary with container stats or None if not available
        """
        if not container_id:
            return None

        # Get stats from cache
        cached_stats = self._stats_cache.get(container_id)

        if cached_stats:
            # Return cached stats (excluding timestamp for backward compatibility)
            return {
                "cpu_percent": cached_stats["cpu_percent"],
                "memory_mb": cached_stats["memory_mb"],
                "memory_percent": cached_stats["memory_percent"],
            }

        # No cached stats available - container hasn't reported yet
        logger.debug(f"No cached stats available for container {container_id}")
        return None


stats_service = StatsService()
