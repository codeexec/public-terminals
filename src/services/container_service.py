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
from src.auth.callback_auth import generate_callback_token

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

    async def get_container_ip(self, container_id: str) -> Optional[str]:
        """Get Docker container IP"""
        try:
            container_info = self.client.inspect_container(container=container_id)
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

    async def create_sandbox_container(
        self,
        sandbox_id: str,
        use_gpu: bool = False,
        sandbox_type: str = "terminal",
    ) -> Dict[str, str]:
        """
        Create a new Docker container for sandbox.

        Args:
            sandbox_id: Unique identifier for the sandbox
            use_gpu: Ignored for Docker (GPU only supported on GKE Autopilot)

        Returns:
            Dict with container_id, container_name
        """
        # Note: use_gpu is ignored for Docker containers
        # Check container limit
        active_count = await self.count_active_containers()
        if active_count >= settings.MAX_CONTAINERS_PER_SERVER:
            raise Exception(
                f"Max container limit reached ({settings.MAX_CONTAINERS_PER_SERVER})"
            )

        container_name = f"sandbox-{sandbox_id}"

        # Select the appropriate image based on sandbox_type
        # Handle both Enum objects and strings, case-insensitive
        type_str = sandbox_type.value if hasattr(sandbox_type, "value") else str(sandbox_type)
        type_str = type_str.lower()
        
        image = settings.SANDBOX_BASE_IMAGE
        if type_str == "jupyterlite":
            image = settings.JUPYTERLITE_IMAGE

        try:
            # Generate callback authentication token
            callback_token = generate_callback_token(sandbox_id)

            # Environment variables to pass to container
            environment = [
                f"TERMINAL_ID={sandbox_id}",  # Keep ENV as TERMINAL_ID for container compat for now
                f"API_CALLBACK_URL={settings.API_BASE_URL}/api/v1/callbacks",
                f"CALLBACK_TOKEN={callback_token}",
                f"LOCALTUNNEL_HOST={settings.LOCALTUNNEL_HOST}",
                f"TERMINAL_IDLE_TIMEOUT_SECONDS={settings.SANDBOX_IDLE_TIMEOUT_SECONDS}",
                f"SANDBOX_TYPE={sandbox_type}",
            ]

            # Resource limits
            host_config = self.client.create_host_config(
                mem_limit=settings.CONTAINER_MEMORY_LIMIT,
                nano_cpus=int(settings.CONTAINER_CPU_LIMIT * 1_000_000_000),
            )

            # Create container using low-level API
            container = self.client.create_container(
                image=image,
                name=container_name,
                environment=environment,
                detach=True,
                host_config=host_config,
                labels={
                    "app": "sandbox-server",
                    "sandbox_id": sandbox_id,
                    "sandbox_type": sandbox_type,
                },
                networking_config=None,
            )

            container_id = str(container.get("Id"))

            # Start the container
            self.client.start(container=container_id)

            logger.info(
                f"Created Docker container: {container_id} for sandbox {sandbox_id}"
            )

            return {
                "container_id": container_id,
                "container_name": container_name,
            }

        except Exception as e:
            logger.error(
                f"Failed to create Docker container for sandbox {sandbox_id}: {e}"
            )
            raise

    async def delete_sandbox_container(self, container_id: str) -> bool:
        """Delete a Docker container"""
        try:
            self.client.stop(container=container_id, timeout=10)
            self.client.remove_container(container=container_id)
            logger.info(f"Deleted Docker container: {container_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Docker container {container_id}: {e}")
            return False

    async def stop_sandbox_container(self, container_id: str) -> bool:
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

        # Load k8s config with fallback
        try:
            if settings.K8S_IN_CLUSTER:
                try:
                    config.load_incluster_config()
                    logger.info("Loaded in-cluster Kubernetes config")
                except Exception as e:
                    logger.warning(
                        f"Failed to load in-cluster config: {e}. Trying kube-config..."
                    )
                    config.load_kube_config()
                    logger.info("Loaded kube-config as fallback")
            else:
                try:
                    config.load_kube_config()
                    logger.info("Loaded standard kube-config")
                except Exception as e:
                    logger.warning(
                        f"Failed to load kube-config: {e}. Checking for in-cluster environment..."
                    )
                    if os.environ.get("KUBERNETES_SERVICE_HOST"):
                        config.load_incluster_config()
                        logger.info("Loaded in-cluster config as fallback")
                    else:
                        logger.error(
                            "Not running in K8s cluster (no KUBERNETES_SERVICE_HOST) and kube-config failed."
                        )
                        raise e
        except Exception as e:
            logger.error(f"Failed to load any Kubernetes config: {e}")
            raise

        self.v1 = client.CoreV1Api()
        self.namespace = settings.K8S_NAMESPACE

        # GKE Autopilot configuration
        self.gke_autopilot = settings.GKE_AUTOPILOT_ENABLED
        self.gpu_enabled = settings.GPU_ENABLED and self.gke_autopilot
        self.gpu_type = settings.GPU_TYPE
        self.gpu_count = settings.GPU_COUNT

        logger.info(
            f"Kubernetes container service initialized "
            f"(namespace: {self.namespace}, autopilot: {self.gke_autopilot}, gpu: {self.gpu_enabled})"
        )

    async def get_container_ip(self, container_id: str) -> Optional[str]:
        """Get Kubernetes Pod IP"""
        try:
            pod = self.v1.read_namespaced_pod(
                name=container_id, namespace=self.namespace
            )
            return str(pod.status.pod_ip) if pod.status.pod_ip else None
        except Exception as e:
            logger.error(f"Failed to get IP for pod {container_id}: {e}")
            return None

    async def count_active_containers(self) -> int:
        try:
            # We list pods with the specific label and check if they are running or pending (consuming resources)
            pods = self.v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector="app=sandbox-server",
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
            # Format example: {'containers': [{'name': 'sandbox', 'usage': {'cpu': '10n', 'memory': '10Ki'}}]}

            containers = metrics.get("containers", [])
            if not containers:
                return None

            # We assume one container per pod named 'sandbox'
            container_metrics = next(
                (c for c in containers if c["name"] == "sandbox"), containers[0]
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

    def _build_resource_requirements(self, use_gpu: bool):
        """Build resource requirements including GPU if needed."""
        from kubernetes import client

        # Convert CPU to millicores format (e.g., 1.0 -> "1000m", 0.5 -> "500m")
        cpu_millicores = int(settings.CONTAINER_CPU_LIMIT * 1000)
        cpu_str = f"{cpu_millicores}m"

        # Normalize memory format for Kubernetes (e.g., "1g" -> "1Gi")
        memory = settings.CONTAINER_MEMORY_LIMIT
        if memory.lower().endswith("g") and not memory.lower().endswith("gi"):
            memory = memory[:-1] + "Gi"
        elif memory.lower().endswith("m") and not memory.lower().endswith("mi"):
            memory = memory[:-1] + "Mi"

        requests = {
            "cpu": cpu_str,
            "memory": memory,
        }
        limits = {
            "cpu": cpu_str,
            "memory": memory,
        }

        if use_gpu:
            # Add GPU resource limit (required for GKE Autopilot GPU scheduling)
            limits["nvidia.com/gpu"] = str(self.gpu_count)

        return client.V1ResourceRequirements(
            requests=requests,
            limits=limits,
        )

    def _build_node_selector(self, use_gpu: bool) -> Optional[Dict[str, str]]:
        """Build node selector for GKE Autopilot GPU pods."""
        if not self.gke_autopilot or not use_gpu:
            return None

        return {
            "cloud.google.com/gke-accelerator": self.gpu_type,
            "cloud.google.com/gke-accelerator-count": str(self.gpu_count),
        }

    def _build_pod_spec(
        self, sandbox_id: str, use_gpu: bool = False, sandbox_type: str = "terminal"
    ):
        """
        Build Kubernetes Pod specification.

        Args:
            sandbox_id: The sandbox identifier
            use_gpu: Whether to enable GPU for this pod

        Returns:
            V1Pod object ready for creation
        """
        from kubernetes import client

        pod_name = f"sandbox-{sandbox_id}"

        # Select the appropriate image
        # Handle both Enum objects and strings, case-insensitive
        type_str = (
            sandbox_type.value
            if hasattr(sandbox_type, "value")
            else str(sandbox_type)
        ).lower()

        image = settings.SANDBOX_BASE_IMAGE
        if type_str == "jupyterlite":
            image = settings.JUPYTERLITE_IMAGE
        elif use_gpu and settings.GPU_TERMINAL_IMAGE:
            image = settings.GPU_TERMINAL_IMAGE

        # Build resource requirements
        resources = self._build_resource_requirements(use_gpu)

        # Build node selector (for GKE Autopilot GPU scheduling)
        node_selector = self._build_node_selector(use_gpu)

        # Build environment variables
        env_vars = [
            client.V1EnvVar(name="TERMINAL_ID", value=sandbox_id),
            client.V1EnvVar(
                name="API_CALLBACK_URL",
                value=f"{settings.API_BASE_URL}/api/v1/callbacks",
            ),
            client.V1EnvVar(
                name="CALLBACK_TOKEN",
                value=generate_callback_token(sandbox_id),
            ),
            client.V1EnvVar(name="LOCALTUNNEL_HOST", value=settings.LOCALTUNNEL_HOST),
            client.V1EnvVar(
                name="TERMINAL_IDLE_TIMEOUT_SECONDS",
                value=str(settings.SANDBOX_IDLE_TIMEOUT_SECONDS),
            ),
            client.V1EnvVar(name="SANDBOX_TYPE", value=sandbox_type),
        ]

        # Add GPU-related env vars if using GPU
        if use_gpu:
            env_vars.append(client.V1EnvVar(name="GPU_ENABLED", value="true"))
            env_vars.append(client.V1EnvVar(name="NVIDIA_VISIBLE_DEVICES", value="all"))

        # Build labels
        labels = {
            "app": "sandbox-server",
            "sandbox-id": sandbox_id,
            "sandbox-type": type_str,
        }
        if use_gpu:
            labels["gpu-enabled"] = "true"

        # Build container
        container = client.V1Container(
            name="sandbox",
            image=image,
            env=env_vars,
            ports=[client.V1ContainerPort(container_port=8888)],
            resources=resources,
        )

        # Build pod spec
        pod_spec = client.V1PodSpec(
            restart_policy="Never",
            containers=[container],
        )

        # Add node selector if set (for GPU pods on GKE Autopilot)
        if node_selector:
            pod_spec.node_selector = node_selector

        # Note: Tolerations are automatically added by GKE Autopilot
        # for GPU workloads, no need to manually specify them

        return client.V1Pod(
            api_version="v1",
            kind="Pod",
            metadata=client.V1ObjectMeta(
                name=pod_name,
                labels=labels,
            ),
            spec=pod_spec,
        )

    async def create_sandbox_container(
        self,
        sandbox_id: str,
        use_gpu: bool = False,
        sandbox_type: str = "terminal",
    ) -> Dict[str, str]:
        """
        Create a new Kubernetes Pod for sandbox.

        Args:
            sandbox_id: Unique identifier for the sandbox
            use_gpu: Request GPU-enabled container (GKE Autopilot only)

        Returns:
            Dict with container_id (pod_name), container_name
        """
        # Check container limit
        active_count = await self.count_active_containers()
        if active_count >= settings.MAX_CONTAINERS_PER_SERVER:
            raise Exception(
                f"Max container limit reached ({settings.MAX_CONTAINERS_PER_SERVER})"
            )

        # Determine if GPU should be used
        should_use_gpu = use_gpu and self.gpu_enabled

        pod_name = f"sandbox-{sandbox_id}"

        # Build pod specification
        pod_manifest = self._build_pod_spec(sandbox_id, should_use_gpu, sandbox_type)

        try:
            # Create the pod
            self.v1.create_namespaced_pod(namespace=self.namespace, body=pod_manifest)

            logger.info(
                f"Created Kubernetes pod: {pod_name} for sandbox {sandbox_id} "
                f"(gpu={should_use_gpu})"
            )

            return {
                "container_id": pod_name,
                "container_name": pod_name,
            }

        except Exception as e:
            logger.error(
                f"Failed to create Kubernetes pod for sandbox {sandbox_id}: {e}"
            )
            raise

    async def delete_sandbox_container(self, container_id: str) -> bool:
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

    async def stop_sandbox_container(self, container_id: str) -> bool:
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
