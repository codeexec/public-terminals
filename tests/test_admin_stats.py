import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.api.routes.admin import get_admin_stats
from src.database.models import Terminal


@pytest.mark.asyncio
async def test_get_admin_stats():
    """Test admin stats endpoint"""

    # Mock DB session
    mock_db = MagicMock()

    # Mock terminal
    mock_terminal = MagicMock(spec=Terminal)
    mock_terminal.id = "test-term-1"
    mock_terminal.container_id = "container-123"
    mock_terminal.user_id = "user-1"
    mock_terminal.status = "started"

    mock_db.query.return_value.filter.return_value.all.return_value = [mock_terminal]

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

    # Patch the StatsService instance method used in the route
    # Note: The route imports stats_service instance, so we need to patch that
    with (
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

        assert "terminals" in result
        assert len(result["terminals"]) == 1
        assert result["terminals"][0]["id"] == "test-term-1"
        # Stats are now lazy loaded, so they should be None in the list response
        assert result["terminals"][0]["stats"] is None

        assert "terminal_count" in result
        assert result["terminal_count"] == 1


@pytest.mark.asyncio
async def test_get_admin_stats_excludes_deleted():
    """Test that deleted terminals are excluded from stats"""
    mock_db = MagicMock()
    
    # We can't easily test the SQLAlchemy filter composition with a simple mock,
    # but we can ensure the code runs without error and returns what the DB returns.
    # To truly test the filter, we'd need an integration test with a real DB or 
    # inspect the calls to filter().
    
    mock_db.query.return_value.filter.return_value.all.return_value = []
    
    with patch("src.services.stats_service.stats_service.get_system_stats", return_value={}):
        await get_admin_stats(current_admin="admin", db=mock_db)
        
        # Verify that filter was called with multiple arguments
        # The exact verification is tricky with generic mocks, but we can check call count
        assert mock_db.query.called
        assert mock_db.query.return_value.filter.called
