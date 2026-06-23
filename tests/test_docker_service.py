"""
Tests for DockerContainerService.

Converted to pure pytest style with fixtures from conftest.py.
Async tests use @pytest.mark.asyncio on standalone async functions
so they are properly awaited (unlike when used on unittest.TestCase methods).
"""

import pytest
from unittest.mock import patch

from src.constants import SandboxType
from src.exceptions import SandboxLimitReachedError


@pytest.mark.unit
@pytest.mark.asyncio
async def test_count_active_containers_returns_correct_count(docker_service):
    """count_active_containers should return the number of running containers."""
    service, mock_docker_client = docker_service

    mock_docker_client.containers.return_value = [{}, {}, {}]
    count = await service.count_active_containers()

    assert count == 3
    mock_docker_client.containers.assert_called_once_with(
        filters={"label": "app=sandbox-server", "status": "running"}
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_sandbox_container_success(docker_service):
    """create_sandbox_container should create and start a container, returning its ID."""
    service, mock_docker_client = docker_service

    with patch.object(service, "count_active_containers", return_value=0), \
         patch.object(service, "_get_api_server_ip", return_value="172.18.0.5"):
        mock_docker_client.create_container.return_value = {"Id": "new-container-id"}

        result = await service.create_sandbox_container(
            sandbox_id="test-id",
            sandbox_type=SandboxType.TERMINAL,
        )

        assert result["container_id"] == "new-container-id"
        mock_docker_client.start.assert_called_once_with(container="new-container-id")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_sandbox_container_limit_reached(docker_service):
    """create_sandbox_container should raise SandboxLimitReachedError when at capacity."""
    service, _mock_docker_client = docker_service

    with patch.object(service, "count_active_containers", return_value=10):
        with pytest.raises(SandboxLimitReachedError):
            await service.create_sandbox_container(sandbox_id="test-id")
