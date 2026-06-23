"""
Kubernetes Container Service - Manages terminal container lifecycle using Kubernetes
"""

import os
import logging
import asyncio
from typing import Optional, Dict

from src.config import settings
from src.services.interfaces import BaseContainerService
from src.auth.callback_auth import generate_callback_token
from src.exceptions import ContainerCreationError, ContainerError, SandboxLimitReachedError, ContainerStatusError
from src.constants import SandboxType, LABEL_APP

logger = logging.getLogger(__name__)


class KubernetesContainerService(BaseContainerService):
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
                        raise ContainerError("Kubernetes config loading failed") from e
        except Exception as e:
            logger.error(f"Failed to load any Kubernetes config: {e}")
            raise ContainerError(f"Kubernetes initialization failed: {e}") from e

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
            pod = await asyncio.to_thread(
                self.v1.read_namespaced_pod,
                name=container_id,
                namespace=self.namespace
            )
            return str(pod.status.pod_ip) if pod.status.pod_ip else None
        except Exception as e:
            logger.error(f"Failed to get IP for pod {container_id}: {e}")
            return None

    async def count_active_containers(self) -> int:
        try:
            # We list pods with the specific label and check if they are running or pending (consuming resources)
            pods = await asyncio.to_thread(
                self.v1.list_namespaced_pod,
                namespace=self.namespace,
                label_selector=f"app={LABEL_APP}",
                field_selector="status.phase!=Succeeded,status.phase!=Failed",
            )
            return len(pods.items)
        except Exception as e:
            logger.error(f"Failed to count active pods: {e}")
            raise ContainerStatusError(f"Failed to count active pods: {e}") from e

    async def get_container_stats(self, container_id: str) -> Optional[Dict[str, float]]:
        """Get Kubernetes Pod resource usage statistics"""
        from kubernetes import client

        try:
            # We need the metrics API for this
            custom_api = client.CustomObjectsApi()

            # Retrieve metrics for the pod
            try:
                metrics = await asyncio.to_thread(
                    custom_api.get_namespaced_custom_object,
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
                nanocores = int(cpu_usage_str.replace("n", ""))
                cpu_percent = (nanocores / 1_000_000_000) * 100.0
            elif cpu_usage_str.endswith("m"):
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

            # Assuming 1Gi limit as per config for percent calculation
            memory_limit_mb = 1024.0
            memory_percent = (memory_mb / memory_limit_mb) * 100.0 if memory_limit_mb > 0 else 0.0

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

        # Convert CPU to millicores format
        cpu_millicores = int(settings.CONTAINER_CPU_LIMIT * 1000)
        cpu_str = f"{cpu_millicores}m"

        # Normalize memory format
        memory = settings.CONTAINER_MEMORY_LIMIT
        if memory.lower().endswith("g") and not memory.lower().endswith("gi"):
            memory = memory[:-1] + "Gi"
        elif memory.lower().endswith("m") and not memory.lower().endswith("mi"):
            memory = memory[:-1] + "Mi"

        requests = {"cpu": cpu_str, "memory": memory}
        limits = {"cpu": cpu_str, "memory": memory}

        if use_gpu:
            limits["nvidia.com/gpu"] = str(self.gpu_count)

        return client.V1ResourceRequirements(requests=requests, limits=limits)

    def _build_node_selector(self, use_gpu: bool) -> Optional[Dict[str, str]]:
        """Build node selector for GKE Autopilot GPU pods."""
        if not self.gke_autopilot or not use_gpu:
            return None

        return {
            "cloud.google.com/gke-accelerator": self.gpu_type,
            "cloud.google.com/gke-accelerator-count": str(self.gpu_count),
        }

    def _build_pod_spec(
        self, sandbox_id: str, use_gpu: bool = False, sandbox_type: str | SandboxType = SandboxType.TERMINAL
    ):
        """Build Kubernetes Pod specification."""
        from kubernetes import client

        pod_name = f"sandbox-{sandbox_id}"
        type_str = self.resolve_sandbox_type(sandbox_type)
        image = self.select_image(type_str, use_gpu)

        resources = self._build_resource_requirements(use_gpu)
        node_selector = self._build_node_selector(use_gpu)

        api_callback_url = f"{settings.API_BASE_URL}/api/v1/callbacks"
        env_dict = self.build_environment_dict(sandbox_id, type_str, api_callback_url)
        env_vars = [client.V1EnvVar(name=k, value=v) for k, v in env_dict.items()]

        if use_gpu:
            env_vars.append(client.V1EnvVar(name="GPU_ENABLED", value="true"))
            env_vars.append(client.V1EnvVar(name="NVIDIA_VISIBLE_DEVICES", value="all"))

        labels = {
            "app": LABEL_APP,
            "sandbox-id": sandbox_id,
            "sandbox-type": type_str,
        }
        if use_gpu:
            labels["gpu-enabled"] = "true"

        container = client.V1Container(
            name="sandbox",
            image=image,
            env=env_vars,
            ports=[client.V1ContainerPort(container_port=8888)],
            resources=resources,
        )

        pod_spec = client.V1PodSpec(restart_policy="Never", containers=[container])
        if node_selector:
            pod_spec.node_selector = node_selector

        return client.V1Pod(
            api_version="v1",
            kind="Pod",
            metadata=client.V1ObjectMeta(name=pod_name, labels=labels),
            spec=pod_spec,
        )

    async def create_sandbox_container(
        self,
        sandbox_id: str,
        use_gpu: bool = False,
        sandbox_type: str | SandboxType = SandboxType.TERMINAL,
    ) -> Dict[str, str]:
        """Create a new Kubernetes Pod for sandbox."""
        # Check container limit
        active_count = await self.count_active_containers()
        if active_count >= settings.MAX_CONTAINERS_PER_SERVER:
            raise SandboxLimitReachedError(
                f"Max container limit reached ({settings.MAX_CONTAINERS_PER_SERVER})"
            )

        should_use_gpu = use_gpu and self.gpu_enabled
        pod_name = f"sandbox-{sandbox_id}"
        pod_manifest = self._build_pod_spec(sandbox_id, should_use_gpu, sandbox_type)

        try:
            await asyncio.to_thread(
                self.v1.create_namespaced_pod,
                namespace=self.namespace,
                body=pod_manifest
            )
            logger.info(f"Created Kubernetes pod: {pod_name} for sandbox {sandbox_id} (gpu={should_use_gpu})")
            return {"container_id": pod_name, "container_name": pod_name}
        except Exception as e:
            logger.error(f"Failed to create Kubernetes pod for sandbox {sandbox_id}: {e}")
            raise ContainerCreationError(f"Failed to create Kubernetes pod: {e}") from e

    async def delete_sandbox_container(self, container_id: str) -> bool:
        """Delete a Kubernetes Pod"""
        try:
            await asyncio.to_thread(
                self.v1.delete_namespaced_pod,
                name=container_id,
                namespace=self.namespace
            )
            logger.info(f"Deleted Kubernetes pod: {container_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Kubernetes pod {container_id}: {e}")
            return False

    async def stop_sandbox_container(self, container_id: str) -> bool:
        """Stop a Kubernetes Pod for idle timeout"""
        try:
            await asyncio.to_thread(
                self.v1.delete_namespaced_pod,
                name=container_id,
                namespace=self.namespace
            )
            logger.info(f"Stopped Kubernetes pod for idle timeout: {container_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop Kubernetes pod {container_id}: {e}")
            return False

    async def get_container_status(self, container_id: str) -> Optional[str]:
        """Get Kubernetes Pod status"""
        try:
            pod = await asyncio.to_thread(
                self.v1.read_namespaced_pod,
                name=container_id,
                namespace=self.namespace
            )
            return str(pod.status.phase) if pod.status.phase else None
        except Exception as e:
            logger.error(f"Failed to get status for pod {container_id}: {e}")
            return None
