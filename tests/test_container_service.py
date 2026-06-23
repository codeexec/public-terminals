"""
Tests for KubernetesContainerService._build_pod_spec.

Converted to pure pytest style with fixtures from conftest.py.
Imports SandboxType from src.constants (the canonical source).
"""

import pytest

from src.constants import SandboxType


@pytest.mark.unit
def test_build_pod_spec_terminal_metadata_and_image(k8s_service):
    """_build_pod_spec should set correct pod name, image, and labels for TERMINAL type."""
    service, mock_settings = k8s_service
    sandbox_id = "test-sandbox"

    pod = service._build_pod_spec(
        sandbox_id, use_gpu=False, sandbox_type=SandboxType.TERMINAL
    )

    assert pod.metadata.name == f"sandbox-{sandbox_id}"
    assert pod.spec.containers[0].image == "base-image"
    assert pod.metadata.labels["sandbox-type"] == "terminal"
    assert pod.metadata.labels["sandbox-id"] == sandbox_id


@pytest.mark.unit
def test_build_pod_spec_jupyterlite_uses_jupyter_image(k8s_service):
    """_build_pod_spec should use the JUPYTERLITE_IMAGE for JUPYTERLITE sandbox type."""
    service, _mock_settings = k8s_service
    sandbox_id = "test-jupyter"

    pod = service._build_pod_spec(
        sandbox_id, use_gpu=False, sandbox_type=SandboxType.JUPYTERLITE
    )

    assert pod.spec.containers[0].image == "jupyter-image"
    assert pod.metadata.labels["sandbox-type"] == "jupyterlite"


@pytest.mark.unit
def test_build_pod_spec_gpu_uses_gpu_image_and_label(k8s_service):
    """_build_pod_spec should use GPU image and set gpu-enabled label when GPU is requested."""
    service, _mock_settings = k8s_service
    sandbox_id = "test-gpu"
    service.gpu_enabled = True

    pod = service._build_pod_spec(
        sandbox_id, use_gpu=True, sandbox_type=SandboxType.TERMINAL
    )

    assert pod.spec.containers[0].image == "gpu-image"
    assert pod.metadata.labels["gpu-enabled"] == "true"
