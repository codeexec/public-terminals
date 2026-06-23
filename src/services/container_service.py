"""
Container Service Factory - Manages container service selection
"""

from functools import lru_cache
from src.config import settings
from src.services.interfaces import ContainerServiceInterface


@lru_cache(maxsize=1)
def get_container_service() -> ContainerServiceInterface:
    """Get container service based on configuration"""
    if settings.CONTAINER_PLATFORM == "kubernetes":
        from src.services.kubernetes_service import KubernetesContainerService

        return KubernetesContainerService()
    else:
        from src.services.docker_service import DockerContainerService

        return DockerContainerService()
