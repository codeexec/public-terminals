import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

from src.api.routes.admin import get_admin_stats
from src.api.routes.sandboxes import start_sandbox
from src.database.models import Sandbox, SandboxStatus
from fastapi import HTTPException


@pytest.mark.unit
@pytest.mark.asyncio
async def test_admin_stats_includes_stopped_active_sandboxes():
    """Test that admin stats include stopped but not expired sandboxes"""
    mock_db = MagicMock()

    # Create timestamps
    now = datetime.now(timezone.utc)
    future = now + timedelta(hours=1)

    # 1. Active started sandbox
    s1 = MagicMock(spec=Sandbox)
    s1.id = "s1"
    s1.type = "terminal"
    s1.status = SandboxStatus.STARTED
    s1.user_id = "u1"
    s1.container_id = "c1"
    s1.container_name = "n1"
    s1.tunnel_url = "http://t1"
    s1.host_port = "8001"
    s1.created_at = now
    s1.updated_at = now
    s1.expires_at = future
    s1.last_activity_at = None
    s1.error_message = None
    s1.gpu_enabled = False
    s1.gpu_type = None
    s1.gpu_count = None

    # 2. Stopped but valid sandbox
    s2 = MagicMock(spec=Sandbox)
    s2.id = "s2"
    s2.type = "terminal"
    s2.status = SandboxStatus.STOPPED
    s2.user_id = "u2"
    s2.container_id = "c2"
    s2.container_name = "n2"
    s2.tunnel_url = None
    s2.host_port = None
    s2.created_at = now
    s2.updated_at = now
    s2.expires_at = future
    s2.last_activity_at = None
    s2.error_message = None
    s2.gpu_enabled = False
    s2.gpu_type = None
    s2.gpu_count = None

    # We will simulate the DB returning the list that matches the filter.
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        s1,
        s2,
    ]

    with patch(
        "src.services.stats_service.stats_service.get_system_stats", return_value={}
    ):
        result = await get_admin_stats(current_admin="admin", db=mock_db)

        ids = [s["id"] for s in result["sandboxes"]]
        assert "s1" in ids
        assert "s2" in ids
        assert len(ids) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_sandbox_endpoint():
    """Test the start_sandbox endpoint logic"""
    mock_db = MagicMock()
    mock_bg_tasks = MagicMock()

    # Case 1: Sandbox found and stopped
    sandbox = MagicMock(spec=Sandbox)
    sandbox.id = "s1"
    sandbox.status = SandboxStatus.STOPPED
    sandbox.is_expired.return_value = False
    sandbox.gpu_enabled = False  # Add GPU enabled attribute

    mock_db.query.return_value.filter.return_value.first.return_value = sandbox

    await start_sandbox("s1", mock_bg_tasks, db=mock_db)

    assert sandbox.status == SandboxStatus.PENDING
    assert sandbox.error_message is None
    mock_db.commit.assert_called()

    # Check background task was added with restart=True and use_gpu from sandbox
    from src.api.routes.sandboxes import _create_sandbox_background

    mock_bg_tasks.add_task.assert_called_with(
        _create_sandbox_background,
        "s1",
        mock_db,
        restart=True,
        use_gpu=False,
        sandbox_type=sandbox.type,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_sandbox_endpoint_expired():
    """Test starting an expired sandbox fails"""
    mock_db = MagicMock()
    mock_bg_tasks = MagicMock()

    sandbox = MagicMock(spec=Sandbox)
    sandbox.id = "s1"
    sandbox.status = SandboxStatus.STOPPED
    sandbox.is_expired.return_value = True

    mock_db.query.return_value.filter.return_value.first.return_value = sandbox

    with pytest.raises(HTTPException) as exc:
        await start_sandbox("s1", mock_bg_tasks, db=mock_db)

    assert exc.value.status_code == 400
    assert "expired" in exc.value.detail.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_sandbox_endpoint_wrong_status():
    """Test starting a started sandbox fails"""
    mock_db = MagicMock()
    mock_bg_tasks = MagicMock()

    sandbox = MagicMock(spec=Sandbox)
    sandbox.id = "s1"
    sandbox.status = SandboxStatus.STARTED
    sandbox.is_expired.return_value = False

    mock_db.query.return_value.filter.return_value.first.return_value = sandbox

    with pytest.raises(HTTPException) as exc:
        await start_sandbox("s1", mock_bg_tasks, db=mock_db)

    assert exc.value.status_code == 400
