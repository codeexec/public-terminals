"""
Container Service - Manages terminal container lifecycle
Supports both Docker and Kubernetes
"""

import docker
import os
import logging
from typing import Optional, Dict

from src.config import settings
from src.services.interfaces import ContainerServiceInterface

logger = logging.getLogger(__name__)


class DockerContainerService(ContainerServiceInterface):
    """Docker-based container management"""

    def __init__(self):
        # Use APIClient (low-level) instead of DockerClient
        # Don't specify base_url - let docker SDK auto-detect via DOCKER_HOST env or defaults
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
            raise

    async def count_active_containers(self) -> int:
        """Count number of active terminal containers"""
        try:
            containers = self.client.containers(
                filters={"label": "app=terminal-server", "status": "running"}
            )
            return len(containers)
        except Exception as e:
            logger.error(f"Failed to count active containers: {e}")
            return 0

    async def create_terminal_container(self, terminal_id: str) -> Dict[str, str]:
        """
        Create a new Docker container for terminal

        Returns:
            Dict with container_id, container_name
        """
        # Check container limit
        active_count = await self.count_active_containers()
        if active_count >= settings.MAX_CONTAINERS_PER_SERVER:
            raise Exception(
                f"Max container limit reached ({settings.MAX_CONTAINERS_PER_SERVER})"
            )

        container_name = f"terminal-{terminal_id}"

        try:
            # Environment variables to pass to container
            environment = [
                f"TERMINAL_ID={terminal_id}",
                f"API_CALLBACK_URL={settings.API_BASE_URL}/api/v1/callbacks",
                f"LOCALTUNNEL_HOST={settings.LOCALTUNNEL_HOST}",
            ]

            # Resource limits
            host_config = self.client.create_host_config(
                mem_limit=settings.CONTAINER_MEMORY_LIMIT,
                nano_cpus=int(settings.CONTAINER_CPU_LIMIT * 1_000_000_000),
            )

            # Create container using low-level API
            container = self.client.create_container(
                image=settings.TERMINAL_IMAGE,
                name=container_name,
                environment=environment,
                detach=True,
                host_config=host_config,
                labels={
                    "app": "terminal-server",
                    "terminal_id": terminal_id,
                },
                networking_config=None,
            )

            container_id = str(container.get("Id"))

            # Start the container
            self.client.start(container=container_id)

            logger.info(
                f"Created Docker container: {container_id} for terminal {terminal_id}"
            )

            return {
                "container_id": container_id,
                "container_name": container_name,
            }

        except Exception as e:
            logger.error(
                f"Failed to create Docker container for terminal {terminal_id}: {e}"
            )
            raise

    async def delete_terminal_container(self, container_id: str) -> bool:
        """Delete a Docker container"""
        try:
            self.client.stop(container=container_id, timeout=10)
            self.client.remove_container(container=container_id)
            logger.info(f"Deleted Docker container: {container_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Docker container {container_id}: {e}")
            return False

    async def stop_terminal_container(self, container_id: str) -> bool:
        """Stop a Docker container for idle timeout"""
        try:
            self.client.stop(container=container_id, timeout=10)
            self.client.remove_container(container=container_id)
            logger.info(f"Stopped Docker container for idle timeout: {container_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop Docker container {container_id}: {e}")
            return False

    async def get_container_status(self, container_id: str) -> Optional[str]:
        """Get Docker container status"""
        try:
            container_info = self.client.inspect_container(container=container_id)
            status = container_info.get("State", {}).get("Status")
            if isinstance(status, str):
                return status
            return str(status) if status is not None else None
        except Exception as e:
            logger.error(f"Failed to get status for container {container_id}: {e}")
            return None


class KubernetesContainerService(ContainerServiceInterface):
    """Kubernetes-based container management (for GKE)"""

    def __init__(self):
        from kubernetes import client, config

        # Load k8s config
        if settings.K8S_IN_CLUSTER:
            config.load_incluster_config()
        else:
            config.load_kube_config()

        self.v1 = client.CoreV1Api()
        self.namespace = settings.K8S_NAMESPACE
        logger.info(
            f"Kubernetes container service initialized (namespace: {self.namespace})"
        )

    async def count_active_containers(self) -> int:
        """Count number of active terminal pods"""
        try:
            # We list pods with the specific label and check if they are running or pending (consuming resources)
            pods = self.v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector="app=terminal-server",
                field_selector="status.phase!=Succeeded,status.phase!=Failed",
            )
            return len(pods.items)
        except Exception as e:
            logger.error(f"Failed to count active pods: {e}")
            return 0

    async def create_terminal_container(self, terminal_id: str) -> Dict[str, str]:
        """
        Create a new Kubernetes Pod for terminal

        Returns:
            Dict with container_id (pod_name), container_name
        """
        # Check container limit
        active_count = await self.count_active_containers()
        if active_count >= settings.MAX_CONTAINERS_PER_SERVER:
            raise Exception(
                f"Max container limit reached ({settings.MAX_CONTAINERS_PER_SERVER})"
            )

        from kubernetes import client

        pod_name = f"terminal-{terminal_id}"

        # Define Pod specification
        pod_manifest = client.V1Pod(
            api_version="v1",
            kind="Pod",
            metadata=client.V1ObjectMeta(
                name=pod_name,
                labels={
                    "app": "terminal-server",
                    "terminal-id": terminal_id,
                },
            ),
            spec=client.V1PodSpec(
                restart_policy="Never",
                containers=[
                    client.V1Container(
                        name="terminal",
                        image=settings.TERMINAL_IMAGE,
                        env=[
                            client.V1EnvVar(name="TERMINAL_ID", value=terminal_id),
                            client.V1EnvVar(
                                name="API_CALLBACK_URL",
                                value=f"{settings.API_BASE_URL}/api/v1/callbacks",
                            ),
                            client.V1EnvVar(
                                name="LOCALTUNNEL_HOST", value=settings.LOCALTUNNEL_HOST
                            ),
                        ],
                        ports=[client.V1ContainerPort(container_port=8888)],
                        resources=client.V1ResourceRequirements(
                            requests={
                                "cpu": str(settings.CONTAINER_CPU_LIMIT),
                                "memory": settings.CONTAINER_MEMORY_LIMIT,
                            },
                            limits={
                                "cpu": str(settings.CONTAINER_CPU_LIMIT),
                                "memory": settings.CONTAINER_MEMORY_LIMIT,
                            },
                        ),
                    )
                ],
            ),
        )

        try:
            # Create the pod
            self.v1.create_namespaced_pod(namespace=self.namespace, body=pod_manifest)

            logger.info(
                f"Created Kubernetes pod: {pod_name} for terminal {terminal_id}"
            )

            return {
                "container_id": pod_name,
                "container_name": pod_name,
            }

        except Exception as e:
            logger.error(
                f"Failed to create Kubernetes pod for terminal {terminal_id}: {e}"
            )
            raise

    async def delete_terminal_container(self, container_id: str) -> bool:
        """Delete a Kubernetes Pod"""
        try:
            self.v1.delete_namespaced_pod(
                name=container_id,
                namespace=self.namespace,
            )
            logger.info(f"Deleted Kubernetes pod: {container_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Kubernetes pod {container_id}: {e}")
            return False

    async def stop_terminal_container(self, container_id: str) -> bool:
        """Stop a Kubernetes Pod for idle timeout"""
        try:
            self.v1.delete_namespaced_pod(
                name=container_id,
                namespace=self.namespace,
            )
            logger.info(f"Stopped Kubernetes pod for idle timeout: {container_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop Kubernetes pod {container_id}: {e}")
            return False

    async def get_container_status(self, container_id: str) -> Optional[str]:
        """Get Kubernetes Pod status"""
        try:
            pod = self.v1.read_namespaced_pod(
                name=container_id, namespace=self.namespace
            )
            phase = pod.status.phase
            return str(phase) if phase else None
        except Exception as e:
            logger.error(f"Failed to get status for pod {container_id}: {e}")
            return None


# Factory function to get the appropriate container service
def get_container_service() -> ContainerServiceInterface:
    """Get container service based on configuration"""
    if settings.CONTAINER_PLATFORM == "kubernetes":
        return KubernetesContainerService()
    else:
        # Use CLI-based service to avoid urllib3 compatibility issues
        from src.services.docker_cli_service import DockerCLIService

        return DockerCLIService()
