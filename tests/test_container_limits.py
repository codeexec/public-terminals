import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException, status
from src.api.routes.terminals import create_terminal, TerminalStatus
from src.config import settings


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_terminal_limit_exceeded_db():
    """Test that create_terminal raises 503 if DB count exceeds limit"""

    # Mock DB session
    mock_db = MagicMock()
    # Mock count to be at the limit
    mock_db.query.return_value.filter.return_value.count.return_value = (
        settings.MAX_CONTAINERS_PER_SERVER
    )

    # Mock background tasks
    mock_background_tasks = MagicMock()

    # Mock container service (should not be called if DB check fails, but just in case)
    mock_container_service = AsyncMock()
    mock_container_service.count_active_containers.return_value = 0

    with patch(
        "src.api.routes.terminals.get_container_service",
        return_value=mock_container_service,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_terminal(
                terminal_create=MagicMock(),
                background_tasks=mock_background_tasks,
                x_guest_id="test",
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "active terminals" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_terminal_limit_exceeded_real():
    """Test that create_terminal raises 503 if real container count exceeds limit"""

    # Mock DB session
    mock_db = MagicMock()
    # Mock count to be below limit
    mock_db.query.return_value.filter.return_value.count.return_value = (
        settings.MAX_CONTAINERS_PER_SERVER - 1
    )

    # Mock background tasks
    mock_background_tasks = MagicMock()

    # Mock container service to return limit reached
    mock_container_service = AsyncMock()
    mock_container_service.count_active_containers.return_value = (
        settings.MAX_CONTAINERS_PER_SERVER
    )

    with patch(
        "src.api.routes.terminals.get_container_service",
        return_value=mock_container_service,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_terminal(
                terminal_create=MagicMock(),
                background_tasks=mock_background_tasks,
                x_guest_id="test",
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "Server capacity reached" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_terminal_success():
    """Test that create_terminal succeeds if under limit"""

    # Mock DB session
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.count.return_value = 10

    # Mock background tasks
    mock_background_tasks = MagicMock()

    # Mock container service
    mock_container_service = AsyncMock()
    mock_container_service.count_active_containers.return_value = 10

    with patch(
        "src.api.routes.terminals.get_container_service",
        return_value=mock_container_service,
    ):
        result = await create_terminal(
            terminal_create=MagicMock(),
            background_tasks=mock_background_tasks,
            x_guest_id="test",
            db=mock_db,
        )

        assert result.status == TerminalStatus.PENDING
