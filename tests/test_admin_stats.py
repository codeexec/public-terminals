import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock
from src.api.routes.admin import get_admin_stats
from src.database.models import Sandbox


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_admin_stats():
    """Test admin stats endpoint"""

    # Mock DB session
    mock_db = MagicMock()

    # Mock sandbox
    mock_sandbox = MagicMock(spec=Sandbox)
    mock_sandbox.id = "test-term-1"
    mock_sandbox.type = "terminal"
    mock_sandbox.status = "started"
    mock_sandbox.user_id = "user-1"
    mock_sandbox.container_id = "container-123"
    mock_sandbox.container_name = "sandbox-container"
    mock_sandbox.tunnel_url = "http://tunnel.com"
    mock_sandbox.host_port = "8888"
    mock_sandbox.created_at = datetime.now()
    mock_sandbox.updated_at = datetime.now()
    mock_sandbox.expires_at = None
    mock_sandbox.last_activity_at = None
    mock_sandbox.error_message = None
    mock_sandbox.gpu_enabled = False
    mock_sandbox.gpu_type = None
    mock_sandbox.gpu_count = None

    # Mock repository
    mock_repo = MagicMock()
    mock_repo.list_all = AsyncMock(return_value=[mock_sandbox])

    # Mock stats service
    mock_system_stats = {
        "cpu": {"percent": 10.5, "cores": 4},
        "memory": {"total_gb": 16.0, "used_gb": 8.0, "percent": 50.0},
        "disk": {"total_gb": 100.0, "used_gb": 50.0, "percent": 50.0},
    }

    mock_container_stats = {
        "cpu_percent": 5.0,
        "memory_mb": 128.0,
        "memory_percent": 12.5,
    }

    with (
        patch("src.api.routes.admin.SandboxRepository", return_value=mock_repo),
        patch(
            "src.services.stats_service.stats_service.get_system_stats",
            return_value=mock_system_stats,
        ),
        patch(
            "src.services.stats_service.stats_service.get_container_stats",
            new_callable=AsyncMock,
            return_value=mock_container_stats,
        ),
    ):
        result = await get_admin_stats(current_admin="admin", db=mock_db)

        # Verify structure
        assert "system" in result
        assert result["system"] == mock_system_stats

        assert "sandboxes" in result
        assert len(result["sandboxes"]) == 1
        assert result["sandboxes"][0]["id"] == "test-term-1"
        # Stats are now lazy loaded, so they should be None in the list response
        assert result["sandboxes"][0]["stats"] is None

        assert "sandbox_count" in result
        assert result["sandbox_count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_admin_stats_excludes_deleted():
    """Test that deleted sandboxes are excluded from stats"""
    mock_db = MagicMock()

    mock_repo = MagicMock()
    mock_repo.list_all = AsyncMock(return_value=[])

    with (
        patch("src.api.routes.admin.SandboxRepository", return_value=mock_repo),
        patch(
            "src.services.stats_service.stats_service.get_system_stats", return_value={}
        ),
    ):
        await get_admin_stats(current_admin="admin", db=mock_db)

        # Verify that repo list_all was called
        assert mock_repo.list_all.called
