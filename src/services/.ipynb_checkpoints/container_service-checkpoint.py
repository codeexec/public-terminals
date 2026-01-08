"""
Container Service - Manages terminal container lifecycle
Supports both Docker and Kubernetes
"""
import logging
from typing import Optional, Dict
from abc import ABC, abstractmethod

from src.config import settings

logger = logging.getLogger(__name__)


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
    async def get_container_status(self, container_id: str) -> Optional[str]:
        """Get container status"""
        pass


class DockerContainerService(ContainerServiceInterface):
    """Docker-based container management"""

    def __init__(self):
        import docker
        self.client = docker.DockerClient(base_url=settings.DOCKER_HOST)
        logger.info("Docker container service initialized")

    async def create_terminal_container(self, terminal_id: str) -> Dict[str, str]:
        """
        Create a new Docker container for terminal

        Returns:
            Dict with container_id, container_name
        """
        container_name = f"terminal-{terminal_id}"

        try:
            # Environment variables to pass to container
            environment = {
                "TERMINAL_ID": terminal_id,
                "API_CALLBACK_URL": f"{settings.API_BASE_URL}/api/v1/callbacks",
                "LOCALTUNNEL_HOST": settings.LOCALTUNNEL_HOST,
            }

            # Create and start container
            container = self.client.containers.run(
                image=settings.TERMINAL_IMAGE,
                name=container_name,
                environment=environment,
                detach=True,
                remove=False,  # Don't auto-remove so we can check logs
                labels={
                    "app": "terminal-server",
                    "terminal_id": terminal_id,
                },
                # Network mode for accessing localtunnel
                network_mode="bridge",
            )

            logger.info(f"Created Docker container: {container.id} for terminal {terminal_id}")

            return {
                "container_id": container.id,
                "container_name": container_name,
            }

        except Exception as e:
            logger.error(f"Failed to create Docker container for terminal {terminal_id}: {e}")
            raise

    async def delete_terminal_container(self, container_id: str) -> bool:
        """Delete a Docker container"""
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=10)
            container.remove()
            logger.info(f"Deleted Docker container: {container_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Docker container {container_id}: {e}")
            return False

    async def get_container_status(self, container_id: str) -> Optional[str]:
        """Get Docker container status"""
        try:
            container = self.client.containers.get(container_id)
            return container.status
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
        logger.info(f"Kubernetes container service initialized (namespace: {self.namespace})")

    async def create_terminal_container(self, terminal_id: str) -> Dict[str, str]:
        """
        Create a new Kubernetes Pod for terminal

        Returns:
            Dict with container_id (pod_name), container_name
        """
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
                }
            ),
            spec=client.V1PodSpec(
                restart_policy="Never",
                containers=[
                    client.V1Container(
                        name="terminal",
                        image=settings.TERMINAL_IMAGE,
                        env=[
                            client.V1EnvVar(name="TERMINAL_ID", value=terminal_id),
                            client.V1EnvVar(name="API_CALLBACK_URL",
                                          value=f"{settings.API_BASE_URL}/api/v1/callbacks"),
                            client.V1EnvVar(name="LOCALTUNNEL_HOST",
                                          value=settings.LOCALTUNNEL_HOST),
                        ],
                        ports=[client.V1ContainerPort(container_port=8888)],
                    )
                ]
            )
        )

        try:
            # Create the pod
            self.v1.create_namespaced_pod(
                namespace=self.namespace,
                body=pod_manifest
            )

            logger.info(f"Created Kubernetes pod: {pod_name} for terminal {terminal_id}")

            return {
                "container_id": pod_name,
                "container_name": pod_name,
            }

        except Exception as e:
            logger.error(f"Failed to create Kubernetes pod for terminal {terminal_id}: {e}")
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

    async def get_container_status(self, container_id: str) -> Optional[str]:
        """Get Kubernetes Pod status"""
        try:
            pod = self.v1.read_namespaced_pod(
                name=container_id,
                namespace=self.namespace
            )
            return pod.status.phase
        except Exception as e:
            logger.error(f"Failed to get status for pod {container_id}: {e}")
            return None


# Factory function to get the appropriate container service
def get_container_service() -> ContainerServiceInterface:
    """Get container service based on configuration"""
    if settings.CONTAINER_PLATFORM == "kubernetes":
        return KubernetesContainerService()
    else:
        return DockerContainerService()
