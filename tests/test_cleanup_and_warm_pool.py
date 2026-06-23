import pytest
import asyncio
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock

from src.database.models import Sandbox
from src.constants import SandboxStatus
from src.services.cleanup_service import CleanupService, run_cleanup_task, run_idle_timeout_task
from src.services.stats_service import StatsService
from src.services.warm_pool_service import WarmPoolService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cleanup_no_expire_on_delete_failure():
    """Verify that cleanup does not mark sandbox as EXPIRED if container deletion fails"""
    # Create mock sandbox
    sandbox = Sandbox(
        id="test-sandbox-expired",
        status=SandboxStatus.STARTED,
        container_id="cont-123",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        deleted_at=None,
    )

    # Mock DB session and repo
    db_mock = MagicMock()
    repo_mock = MagicMock()
    
    # Configure repo_mock.get_expired to return our sandbox
    repo_mock.get_expired = AsyncMock(return_value=[sandbox])
    
    # Mock container service to raise an error on container deletion
    container_service_mock = MagicMock()
    container_service_mock.delete_sandbox_container = AsyncMock(
        side_effect=Exception("Docker daemon down or container missing")
    )

    # Initialize CleanupService and patch its dependencies
    cleanup_service = CleanupService()
    cleanup_service.container_service = container_service_mock

    # Patch get_db_context and SandboxRepository
    with patch("src.services.cleanup_service.get_db_context") as mock_db_ctx, \
         patch("src.services.cleanup_service.SandboxRepository", return_value=repo_mock):
        
        # mock_db_ctx is an async context manager
        mock_db_ctx.return_value.__aenter__.return_value = db_mock

        # Run cleanup
        await cleanup_service.cleanup_expired_sandboxes()

        # Verify: container deletion was attempted
        container_service_mock.delete_sandbox_container.assert_called_once_with("cont-123")

        # Verify: status is NOT changed to EXPIRED, deleted_at is NOT set, and db.commit was NOT called
        assert sandbox.status == SandboxStatus.STARTED
        assert sandbox.deleted_at is None
        db_mock.commit.assert_not_called()


@pytest.mark.unit
def test_cleanup_tasks_retry_decorations():
    """Verify Celery task retry logic decorations are applied correctly"""
    # Check that decorators are properly set with retry parameters
    assert run_cleanup_task.max_retries == 3
    assert run_cleanup_task.default_retry_delay == 60
    
    assert run_idle_timeout_task.max_retries == 3
    assert run_idle_timeout_task.default_retry_delay == 60


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stats_service_cache_eviction():
    """Verify TTL-based and size-based cache eviction in StatsService"""
    stats_service = StatsService()
    # Set small size limit for testing
    stats_service._max_cache_size = 3
    stats_service._cache_ttl_seconds = 2

    # 1. Update stats for 3 containers
    stats_service.update_container_stats("c1", 10.0, 100.0, 10.0)
    stats_service.update_container_stats("c2", 20.0, 200.0, 20.0)
    stats_service.update_container_stats("c3", 30.0, 300.0, 30.0)

    # Verify they are in cache
    assert (await stats_service.get_container_stats("c1")) is not None
    assert (await stats_service.get_container_stats("c2")) is not None
    assert (await stats_service.get_container_stats("c3")) is not None

    # 2. Add 4th container, c1 (the oldest) should be evicted
    stats_service.update_container_stats("c4", 40.0, 400.0, 40.0)
    assert (await stats_service.get_container_stats("c1")) is None
    assert (await stats_service.get_container_stats("c4")) is not None

    # 3. Test TTL eviction
    # Insert stats with old timestamp manually
    stats_service._stats_cache["c2"]["timestamp"] = datetime.now(timezone.utc) - timedelta(seconds=5)
    # Retrieving c2 should return None and evict it from cache due to TTL > 2 seconds
    assert (await stats_service.get_container_stats("c2")) is None
    assert "c2" not in stats_service._stats_cache


@pytest.mark.unit
def test_warm_pool_singleton_thread_safe():
    """Verify WarmPoolService singleton get_instance is thread-safe and double-checked"""
    instances = []
    
    def get_instance_thread():
        instances.append(WarmPoolService.get_instance())

    # Start multiple threads to obtain the singleton instance concurrently
    threads = [threading.Thread(target=get_instance_thread) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All instances retrieved must be the exact same object
    assert len(instances) == 10
    first_instance = instances[0]
    for inst in instances:
        assert inst is first_instance
