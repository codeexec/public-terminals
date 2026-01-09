from abc import ABC, abstractmethod
from typing import Dict, Optional


class ContainerServiceInterface(ABC):
    """Abstract interface for container management"""

    @abstractmethod
    async def create_terminal_container(self, terminal_id: str) -> Dict[str, str]:
        """Create a new terminal container"""
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
