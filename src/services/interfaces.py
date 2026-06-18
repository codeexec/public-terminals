from abc import ABC, abstractmethod
from typing import Dict, Optional


class ContainerServiceInterface(ABC):
    """Abstract interface for container management"""

    @abstractmethod
    async def create_sandbox_container(
        self,
        sandbox_id: str,
        use_gpu: bool = False,
        sandbox_type: str = "terminal",
    ) -> Dict[str, str]:
        """
        Create a new sandbox container.

        Args:
            sandbox_id: Unique identifier for the sandbox
            use_gpu: Request GPU-enabled container (GKE Autopilot only)
            sandbox_type: Type of sandbox (terminal or jupyterlite)

        Returns:
            Dict with container_id and container_name
        """
        pass

    @abstractmethod
    async def delete_sandbox_container(self, container_id: str) -> bool:
        """Delete a sandbox container"""
        pass

    @abstractmethod
    async def stop_sandbox_container(self, container_id: str) -> bool:
        """Stop a sandbox container (used for idle timeout)"""
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
