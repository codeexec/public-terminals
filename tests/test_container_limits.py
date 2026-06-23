import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException, status
from src.api.routes.sandboxes import create_sandbox, SandboxStatus
from src.config import settings


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_sandbox_limit_exceeded_db():
    """Test that create_sandbox raises 503 if DB count exceeds limit"""

    # Mock DB session
    mock_db = MagicMock()
    
    # Mock SandboxRepository count_active_total to be at limit
    mock_repo = MagicMock()
    mock_repo.count_active_total = AsyncMock(return_value=settings.MAX_CONTAINERS_PER_SERVER)

    # Mock background tasks
    mock_background_tasks = MagicMock()

    # Mock container service (should not be called if DB check fails, but just in case)
    mock_container_service = AsyncMock()
    mock_container_service.count_active_containers.return_value = 0

    # Mock sandbox_create with use_gpu=None and type=TERMINAL
    mock_sandbox_create = MagicMock()
    mock_sandbox_create.use_gpu = None
    mock_sandbox_create.type = "terminal"

    with patch(
        "src.services.sandbox_service.get_container_service",
        return_value=mock_container_service,
    ), patch(
        "src.services.sandbox_service.SandboxRepository",
        return_value=mock_repo,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_sandbox(
                sandbox_create=mock_sandbox_create,
                background_tasks=mock_background_tasks,
                x_guest_id="test",
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "active sandboxes" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_sandbox_limit_exceeded_real():
    """Test that create_sandbox raises 503 if real container count exceeds limit"""

    # Mock DB session
    mock_db = MagicMock()
    
    # Mock count to be below limit
    mock_repo = MagicMock()
    mock_repo.count_active_total = AsyncMock(return_value=settings.MAX_CONTAINERS_PER_SERVER - 1)

    # Mock background tasks
    mock_background_tasks = MagicMock()

    # Mock container service to return limit reached
    mock_container_service = AsyncMock()
    mock_container_service.count_active_containers.return_value = (
        settings.MAX_CONTAINERS_PER_SERVER
    )

    # Mock sandbox_create with use_gpu=None and type=TERMINAL
    mock_sandbox_create = MagicMock()
    mock_sandbox_create.use_gpu = None
    mock_sandbox_create.type = "terminal"

    with patch(
        "src.services.sandbox_service.get_container_service",
        return_value=mock_container_service,
    ), patch(
        "src.services.sandbox_service.SandboxRepository",
        return_value=mock_repo,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_sandbox(
                sandbox_create=mock_sandbox_create,
                background_tasks=mock_background_tasks,
                x_guest_id="test",
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "Server capacity reached" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_sandbox_success():
    """Test that create_sandbox succeeds if under limit"""

    # Mock DB session
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    
    # Mock Repository methods
    mock_repo = MagicMock()
    mock_repo.count_active_total = AsyncMock(return_value=10)
    mock_repo.create = AsyncMock()

    # Mock background tasks
    mock_background_tasks = MagicMock()

    # Mock container service
    mock_container_service = AsyncMock()
    mock_container_service.count_active_containers.return_value = 10

    # Mock warm pool service
    mock_warm_pool = AsyncMock()
    mock_warm_pool.claim_container.return_value = None

    # Mock sandbox_create with use_gpu=None and type=TERMINAL
    mock_sandbox_create = MagicMock()
    mock_sandbox_create.use_gpu = None
    mock_sandbox_create.type = "terminal"

    with patch(
        "src.services.sandbox_service.get_container_service",
        return_value=mock_container_service,
    ), patch(
        "src.services.sandbox_service.get_warm_pool_service",
        return_value=mock_warm_pool,
    ), patch(
        "src.services.sandbox_service.SandboxRepository",
        return_value=mock_repo,
    ):
        result = await create_sandbox(
            sandbox_create=mock_sandbox_create,
            background_tasks=mock_background_tasks,
            x_guest_id="test",
            db=mock_db,
        )

        assert result.status == SandboxStatus.PENDING
