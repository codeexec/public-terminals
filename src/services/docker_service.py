"""
Docker Container Service - Manages terminal container lifecycle using Docker SDK
"""

import docker
import os
import logging
import asyncio
from typing import Optional, Dict, Any

from src.config import settings
from src.services.interfaces import BaseContainerService
from src.exceptions import ContainerCreationError, ContainerError, SandboxLimitReachedError, ContainerStatusError
from src.constants import SandboxType, LABEL_APP, LABEL_SANDBOX_ID, LABEL_SANDBOX_TYPE

logger = logging.getLogger(__name__)


class DockerContainerService(BaseContainerService):
    """Docker-based container management"""

    def __init__(self):
        # Use APIClient (low-level) instead of DockerClient
        try:
            # Ensure DOCKER_HOST is not set to avoid URL parsing issues
            if "DOCKER_HOST" in os.environ and os.environ["DOCKER_HOST"]:
                del os.environ["DOCKER_HOST"]

            self.client = docker.APIClient(version="1.41")
            # Test the connection
            self.client.ping()
            logger.info("Docker container service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise ContainerError(f"Docker SDK initialization failed: {e}") from e

    def _get_api_server_ip(self) -> str:
        """Get the internal IP of the api-server container"""
        try:
            container_info = self.client.inspect_container("sandbox-server-api")
            networks = container_info.get("NetworkSettings", {}).get("Networks", {})
            for net_name, net_info in networks.items():
                ip = net_info.get("IPAddress")
                if ip:
                    logger.info(f"Discovered api-server IP on network '{net_name}': {ip}")
                    return ip
            raise ContainerError("Could not find IP for api-server in any network")
        except Exception as e:
            logger.error(f"Could not dynamically resolve api-server IP: {e}")
            # Fallback to service name, relying on Docker DNS
            return "api-server"

    async def get_container_ip(self, container_id: str) -> Optional[str]:
        """Get Docker container IP"""
        try:
            container_info = await asyncio.to_thread(self.client.inspect_container, container=container_id)
            # Try to get IP from NetworkSettings
            ip = container_info.get("NetworkSettings", {}).get("IPAddress")
            if ip:
                return str(ip)

            # If empty, check networks
            networks = container_info.get("NetworkSettings", {}).get("Networks", {})
            for net in networks.values():
                ip = net.get("IPAddress")
                if ip:
                    return str(ip)

            return None
        except Exception as e:
            logger.error(f"Failed to get IP for container {container_id}: {e}")
            return None

    async def count_active_containers(self) -> int:
        try:
            containers = await asyncio.to_thread(
                self.client.containers,
                filters={"label": f"app={LABEL_APP}", "status": "running"}
            )
            return len(containers)
        except Exception as e:
            logger.error(f"Failed to count active containers: {e}")
            raise ContainerStatusError(f"Failed to count active containers: {e}") from e

    async def get_container_stats(self, container_id: str) -> Optional[Dict[str, Any]]:
        """Get container resource usage statistics"""
        try:
            # Use docker stats (stream=False)
            stats = await asyncio.to_thread(self.client.stats, container_id, stream=False)

            # Check if required keys exist
            if "cpu_stats" not in stats or "precpu_stats" not in stats:
                return None

            cpu_usage = stats["cpu_stats"].get("cpu_usage", {}).get("total_usage", 0)
            precpu_usage = (
                stats["precpu_stats"].get("cpu_usage", {}).get("total_usage", 0)
            )

            system_cpu_usage = stats["cpu_stats"].get("system_cpu_usage", 0)
            presystem_cpu_usage = stats["precpu_stats"].get("system_cpu_usage", 0)

            online_cpus = stats["cpu_stats"].get("online_cpus", 1)

            cpu_delta = cpu_usage - precpu_usage
            system_cpu_delta = system_cpu_usage - presystem_cpu_usage

            cpu_percent = 0.0
            if system_cpu_delta > 0.0 and cpu_delta > 0.0:
                cpu_percent = (cpu_delta / system_cpu_delta) * online_cpus * 100.0

            memory_usage = stats.get("memory_stats", {}).get("usage", 0)
            memory_limit = stats.get("memory_stats", {}).get("limit", 1)

            memory_percent = (memory_usage / memory_limit) * 100.0 if memory_limit > 0 else 0.0
            memory_mb = memory_usage / (1024 * 1024)

            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_mb": round(memory_mb, 2),
                "memory_percent": round(memory_percent, 2),
            }
        except Exception as e:
            logger.error(f"Failed to get container stats for {container_id}: {e}")
            return None

    async def create_sandbox_container(
        self,
        sandbox_id: str,
        use_gpu: bool = False,
        sandbox_type: str | SandboxType = SandboxType.TERMINAL,
    ) -> Dict[str, str]:
        """Create a new Docker container for sandbox."""
        # Check container limit
        active_count = await self.count_active_containers()
        if active_count >= settings.MAX_CONTAINERS_PER_SERVER:
            raise SandboxLimitReachedError(
                f"Max container limit reached ({settings.MAX_CONTAINERS_PER_SERVER})"
            )

        container_name = f"sandbox-{sandbox_id}"
        type_str = self.resolve_sandbox_type(sandbox_type)
        image = self.select_image(type_str, use_gpu)

        try:
            api_ip = await asyncio.to_thread(self._get_api_server_ip)

            # Docker needs callback URL dynamically pointing to api-server IP internally
            api_callback_url = f"http://{api_ip}:8000/api/v1/callbacks"
            env_dict = self.build_environment_dict(sandbox_id, type_str, api_callback_url)
            environment = [f"{k}={v}" for k, v in env_dict.items()]

            host_config = await asyncio.to_thread(
                self.client.create_host_config,
                mem_limit=settings.CONTAINER_MEMORY_LIMIT,
                nano_cpus=int(settings.CONTAINER_CPU_LIMIT * 1_000_000_000),
                network_mode=settings.DOCKER_NETWORK,
                extra_hosts={"api-server": api_ip},
            )

            container = await asyncio.to_thread(
                self.client.create_container,
                image=image,
                name=container_name,
                environment=environment,
                detach=True,
                host_config=host_config,
                labels={
                    "app": LABEL_APP,
                    LABEL_SANDBOX_ID: sandbox_id,
                    LABEL_SANDBOX_TYPE: type_str,
                },
            )

            container_id = str(container.get("Id"))
            await asyncio.to_thread(self.client.start, container=container_id)

            logger.info(f"Created Docker container: {container_id} for sandbox {sandbox_id}")
            return {"container_id": container_id, "container_name": container_name}
        except Exception as e:
            logger.error(f"Failed to create Docker container for sandbox {sandbox_id}: {e}")
            raise ContainerCreationError(f"Failed to create Docker container: {e}") from e

    async def delete_sandbox_container(self, container_id: str) -> bool:
        """Delete a Docker container"""
        try:
            await asyncio.to_thread(self.client.stop, container=container_id, timeout=10)
            await asyncio.to_thread(self.client.remove_container, container=container_id)
            logger.info(f"Deleted Docker container: {container_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Docker container {container_id}: {e}")
            return False

    async def stop_sandbox_container(self, container_id: str) -> bool:
        """Stop a Docker container for idle timeout"""
        try:
            await asyncio.to_thread(self.client.stop, container=container_id, timeout=10)
            await asyncio.to_thread(self.client.remove_container, container=container_id)
            logger.info(f"Stopped Docker container for idle timeout: {container_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop Docker container {container_id}: {e}")
            return False

    async def get_container_status(self, container_id: str) -> Optional[str]:
        """Get Docker container status"""
        try:
            container_info = await asyncio.to_thread(self.client.inspect_container, container=container_id)
            status = container_info.get("State", {}).get("Status")
            return str(status) if status is not None else None
        except Exception as e:
            logger.error(f"Failed to get status for container {container_id}: {e}")
            return None
