from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from src.constants import SandboxType
from src.auth.callback_auth import generate_callback_token


class ContainerServiceInterface(ABC):
    """Abstract interface for container management"""

    @abstractmethod
    async def create_sandbox_container(
        self,
        sandbox_id: str,
        use_gpu: bool = False,
        sandbox_type: str | SandboxType = SandboxType.TERMINAL,
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
    async def get_container_stats(self, container_id: str) -> Optional[Dict[str, Any]]:
        """Get container resource usage statistics"""
        pass

    @abstractmethod
    async def get_container_ip(self, container_id: str) -> Optional[str]:
        """Get container IP address"""
        pass


class BaseContainerService(ContainerServiceInterface, ABC):
    """Base class with shared logic for container services"""

    def resolve_sandbox_type(self, sandbox_type: str | SandboxType) -> str:
        """Resolve the sandbox type enum or string to a lowercase string."""
        type_str = sandbox_type.value if hasattr(sandbox_type, "value") else str(sandbox_type)
        return type_str.lower()

    def select_image(self, type_str: str, use_gpu: bool = False) -> str:
        """Select the container image based on type and GPU settings."""
        from src.config import settings
        if use_gpu and settings.GPU_TERMINAL_IMAGE:
            return settings.GPU_TERMINAL_IMAGE
            
        if type_str == SandboxType.JUPYTERLITE.value.lower():
            return settings.JUPYTERLITE_IMAGE
            
        return settings.SANDBOX_BASE_IMAGE

    def build_environment_dict(self, sandbox_id: str, type_str: str, api_callback_url: str) -> dict[str, str]:
        """Construct unified environment variables for containers."""
        from src.config import settings
        callback_token = generate_callback_token(sandbox_id)
        timeout = str(settings.SANDBOX_IDLE_TIMEOUT_SECONDS)
        
        return {
            "SANDBOX_ID": sandbox_id,
            "TERMINAL_ID": sandbox_id,
            "API_CALLBACK_URL": api_callback_url,
            "CALLBACK_TOKEN": callback_token,
            "LOCALTUNNEL_HOST": settings.LOCALTUNNEL_HOST,
            "SANDBOX_IDLE_TIMEOUT_SECONDS": timeout,
            "TERMINAL_IDLE_TIMEOUT_SECONDS": timeout,
            "SANDBOX_TYPE": type_str,
        }
