from abc import ABC, abstractmethod
from typing import Dict, Optional


class ContainerServiceInterface(ABC):
    """Abstract interface for container management"""

    @abstractmethod
    async def create_terminal_container(
        self, terminal_id: str, use_gpu: bool = False
    ) -> Dict[str, str]:
        """
        Create a new terminal container.

        Args:
            terminal_id: Unique identifier for the terminal
            use_gpu: Request GPU-enabled container (GKE Autopilot only)

        Returns:
            Dict with container_id and container_name
        """
        pass

    @abstractmethod
    async def delete_terminal_container(self, container_id: str) -> bool:
        """Delete a terminal container"""
        pass

    @abstractmethod
    async def stop_terminal_container(self, container_id: str) -> bool:
        """Stop a terminal container (used for idle timeout)"""
        pass

    @abstractmethod
    async def get_container_status(self, container_id: str) -> Optional[str]:
        """Get container status"""
        pass

    @abstractmethod
    async def count_active_containers(self) -> int:
        """Count number of active terminal containers"""
        pass

    @abstractmethod
    async def get_container_stats(self, container_id: str) -> Optional[Dict]:
        """Get container resource usage statistics"""
        pass

    @abstractmethod
    async def get_container_ip(self, container_id: str) -> Optional[str]:
        """Get container IP address"""
        pass
