import unittest
import pytest
from unittest.mock import MagicMock, patch
from src.services.container_service import KubernetesContainerService
from src.database.models import SandboxType

@pytest.mark.unit
class TestKubernetesContainerService(unittest.TestCase):
    def setUp(self):
        # Mock settings
        self.settings_patcher = patch('src.services.container_service.settings')
        self.mock_settings = self.settings_patcher.start()
        self.mock_settings.CONTAINER_PLATFORM = "kubernetes"
        self.mock_settings.CONTAINER_CPU_LIMIT = 1.0
        self.mock_settings.CONTAINER_MEMORY_LIMIT = "1G"
        self.mock_settings.SANDBOX_BASE_IMAGE = "base-image"
        self.mock_settings.JUPYTERLITE_IMAGE = "jupyter-image"
        self.mock_settings.GPU_TERMINAL_IMAGE = "gpu-image"
        self.mock_settings.API_BASE_URL = "http://api"
        self.mock_settings.LOCALTUNNEL_HOST = "http://tunnel"
        self.mock_settings.SANDBOX_IDLE_TIMEOUT_SECONDS = 3600
        self.mock_settings.GPU_TYPE = "nvidia-l4"
        self.mock_settings.GPU_COUNT = 1
        
        # Mock kubernetes config
        self.k8s_config_patcher = patch('kubernetes.config')
        self.mock_k8s_config = self.k8s_config_patcher.start()
        
        # Initialize service
        self.service = KubernetesContainerService()

    def tearDown(self):
        self.settings_patcher.stop()
        self.k8s_config_patcher.stop()

    def test_build_pod_spec_terminal(self):
        """Test building pod spec for a standard terminal"""
        sandbox_id = "test-sandbox"
        pod = self.service._build_pod_spec(sandbox_id, use_gpu=False, sandbox_type=SandboxType.TERMINAL)
        
        # Verify type_str was handled correctly and image is correct
        self.assertEqual(pod.metadata.name, f"sandbox-{sandbox_id}")
        self.assertEqual(pod.spec.containers[0].image, "base-image")
        
        # Verify labels (where the NameError was)
        labels = pod.metadata.labels
        self.assertEqual(labels["sandbox-type"], "terminal")
        self.assertEqual(labels["sandbox-id"], sandbox_id)

    def test_build_pod_spec_jupyterlite(self):
        """Test building pod spec for JupyterLite"""
        sandbox_id = "test-jupyter"
        pod = self.service._build_pod_spec(sandbox_id, use_gpu=False, sandbox_type=SandboxType.JUPYTERLITE)
        
        self.assertEqual(pod.spec.containers[0].image, "jupyter-image")
        self.assertEqual(pod.metadata.labels["sandbox-type"], "jupyterlite")

    def test_build_pod_spec_gpu(self):
        """Test building pod spec with GPU"""
        sandbox_id = "test-gpu"
        # Enable GPU in service
        self.service.gpu_enabled = True
        
        pod = self.service._build_pod_spec(sandbox_id, use_gpu=True, sandbox_type=SandboxType.TERMINAL)
        
        self.assertEqual(pod.spec.containers[0].image, "gpu-image")
        self.assertEqual(pod.metadata.labels["gpu-enabled"], "true")

if __name__ == '__main__':
    unittest.main()
