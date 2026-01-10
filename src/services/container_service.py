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

    async def get_container_stats(self, container_id: str) -> Optional[Dict]:
        """Get container resource usage statistics"""
        try:
            # Use docker stats (stream=False)
            stats = self.client.stats(container_id, stream=False)

            # Docker returns raw stats, we need to calculate percentages
            # This calculation is complex and depends on API version
            # Simplified version:

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

            memory_percent = 0.0
            if memory_limit > 0:
                memory_percent = (memory_usage / memory_limit) * 100.0

            memory_mb = memory_usage / (1024 * 1024)

            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_mb": round(memory_mb, 2),
                "memory_percent": round(memory_percent, 2),
            }
        except Exception as e:
            logger.error(f"Failed to get container stats for {container_id}: {e}")
            return None

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
                f"TERMINAL_IDLE_TIMEOUT_SECONDS={settings.TERMINAL_IDLE_TIMEOUT_SECONDS}",
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

    async def get_container_stats(self, container_id: str) -> Optional[Dict]:
        """Get Kubernetes Pod resource usage statistics"""
        from kubernetes import client

        try:
            # We need the metrics API for this
            custom_api = client.CustomObjectsApi()

            # Retrieve metrics for the pod
            # container_id is the pod name
            try:
                metrics = custom_api.get_namespaced_custom_object(
                    group="metrics.k8s.io",
                    version="v1beta1",
                    namespace=self.namespace,
                    plural="pods",
                    name=container_id,
                )
            except Exception:
                # Metrics API might not be available
                return None

            # Parse metrics
            # Format example: {'containers': [{'name': 'terminal', 'usage': {'cpu': '10n', 'memory': '10Ki'}}]}

            containers = metrics.get("containers", [])
            if not containers:
                return None

            # We assume one container per pod named 'terminal'
            container_metrics = next(
                (c for c in containers if c["name"] == "terminal"), containers[0]
            )
            usage = container_metrics.get("usage", {})

            # Parse CPU
            cpu_usage_str = usage.get("cpu", "0")
            cpu_percent = 0.0
            if cpu_usage_str.endswith("n"):
                # nanocores
                nanocores = int(cpu_usage_str.replace("n", ""))
                # Convert to cores then percent (assuming 1 core limit for simple calc, or just raw cores)
                # 1000000000n = 1 core = 100%
                cpu_percent = (nanocores / 1_000_000_000) * 100.0
            elif cpu_usage_str.endswith("m"):
                # millicores
                millicores = int(cpu_usage_str.replace("m", ""))
                cpu_percent = (millicores / 1000) * 100.0

            # Parse Memory
            mem_usage_str = usage.get("memory", "0")
            memory_mb = 0.0
            if mem_usage_str.endswith("Ki"):
                memory_mb = int(mem_usage_str.replace("Ki", "")) / 1024
            elif mem_usage_str.endswith("Mi"):
                memory_mb = int(mem_usage_str.replace("Mi", ""))
            elif mem_usage_str.endswith("Gi"):
                memory_mb = int(mem_usage_str.replace("Gi", "")) * 1024

            # We don't easily know the limit here without looking up the pod spec again,
            # so we might skip memory_percent or approximate it based on our known config
            memory_percent = 0.0
            # Assuming 1Gi limit as per config
            memory_limit_mb = 1024.0
            if memory_limit_mb > 0:
                memory_percent = (memory_mb / memory_limit_mb) * 100.0

            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_mb": round(memory_mb, 2),
                "memory_percent": round(memory_percent, 2),
            }

        except Exception as e:
            logger.warning(f"Failed to get pod stats for {container_id}: {e}")
            return None

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
                            client.V1EnvVar(
                                name="TERMINAL_IDLE_TIMEOUT_SECONDS",
                                value=str(settings.TERMINAL_IDLE_TIMEOUT_SECONDS),
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
