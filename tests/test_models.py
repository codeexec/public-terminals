"""
Unit tests for Sandbox database model methods.

Tests cover: is_expired, is_idle, set_expiry, set_last_activity, to_dict.
All time-dependent tests freeze datetime.now() via unittest.mock.patch.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.database.models import Sandbox
from src.constants import SandboxStatus, SandboxType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FROZEN_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
MODEL_DATETIME_MODULE = "src.database.models.datetime"


def _make_sandbox(**overrides) -> Sandbox:
    """Create a Sandbox instance with sensible defaults.

    server_default columns (created_at, updated_at) are not populated
    outside a DB session, so we set them manually when needed.
    """
    defaults = {
        "id": "test-sandbox-id",
        "status": SandboxStatus.PENDING,
        "type": SandboxType.TERMINAL,
        "gpu_enabled": False,
    }
    defaults.update(overrides)
    sandbox = Sandbox()
    for key, value in defaults.items():
        setattr(sandbox, key, value)
    # Ensure optional fields default to None when not provided
    for attr in (
        "user_id",
        "tunnel_url",
        "container_id",
        "container_name",
        "host_port",
        "created_at",
        "updated_at",
        "expires_at",
        "deleted_at",
        "last_activity_at",
        "error_message",
        "gpu_type",
        "gpu_count",
    ):
        if attr not in defaults:
            setattr(sandbox, attr, None)
    return sandbox


# ===========================================================================
# is_expired tests
# ===========================================================================


@pytest.mark.unit
def test_is_expired_returns_false_when_no_expiry():
    """Sandbox with no expires_at should never be considered expired."""
    sandbox = _make_sandbox(expires_at=None)
    assert sandbox.is_expired() is False


@pytest.mark.unit
def test_is_expired_returns_false_when_future():
    """Sandbox whose expiry is in the future should not be expired."""
    future = FROZEN_NOW + timedelta(hours=1)
    sandbox = _make_sandbox(expires_at=future)
    with patch(MODEL_DATETIME_MODULE) as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert sandbox.is_expired() is False


@pytest.mark.unit
def test_is_expired_returns_true_when_past():
    """Sandbox whose expiry is in the past should be expired."""
    past = FROZEN_NOW - timedelta(hours=1)
    sandbox = _make_sandbox(expires_at=past)
    with patch(MODEL_DATETIME_MODULE) as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert sandbox.is_expired() is True


@pytest.mark.unit
def test_is_expired_handles_naive_datetime():
    """When expires_at has no tzinfo the method should still compare correctly."""
    naive_past = FROZEN_NOW.replace(tzinfo=None) - timedelta(hours=1)
    sandbox = _make_sandbox(expires_at=naive_past)
    with patch(MODEL_DATETIME_MODULE) as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert sandbox.is_expired() is True


@pytest.mark.unit
def test_is_expired_boundary_just_expired():
    """When expires_at is exactly now the sandbox should not be expired (> not >=)."""
    sandbox = _make_sandbox(expires_at=FROZEN_NOW)
    with patch(MODEL_DATETIME_MODULE) as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # now > expires_at is False when they are equal
        assert sandbox.is_expired() is False


# ===========================================================================
# is_idle tests
# ===========================================================================


@pytest.mark.unit
def test_is_idle_returns_false_when_no_activity_and_no_created_at():
    """If both last_activity_at and created_at are None, sandbox is not idle."""
    sandbox = _make_sandbox(last_activity_at=None, created_at=None)
    assert sandbox.is_idle(idle_timeout_minutes=30) is False


@pytest.mark.unit
def test_is_idle_uses_created_at_when_no_activity():
    """Falls back to created_at when last_activity_at is None and it's old enough."""
    old_created = FROZEN_NOW - timedelta(minutes=60)
    sandbox = _make_sandbox(last_activity_at=None, created_at=old_created)
    with patch(MODEL_DATETIME_MODULE) as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert sandbox.is_idle(idle_timeout_minutes=30) is True


@pytest.mark.unit
def test_is_idle_returns_false_when_recently_active():
    """Sandbox with recent activity should not be idle."""
    recent = FROZEN_NOW - timedelta(minutes=5)
    sandbox = _make_sandbox(last_activity_at=recent)
    with patch(MODEL_DATETIME_MODULE) as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert sandbox.is_idle(idle_timeout_minutes=30) is False


@pytest.mark.unit
def test_is_idle_returns_true_when_idle_too_long():
    """Sandbox idle beyond the timeout should be considered idle."""
    old_activity = FROZEN_NOW - timedelta(minutes=60)
    sandbox = _make_sandbox(last_activity_at=old_activity)
    with patch(MODEL_DATETIME_MODULE) as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert sandbox.is_idle(idle_timeout_minutes=30) is True


@pytest.mark.unit
def test_is_idle_handles_naive_datetime():
    """Naive last_activity_at should still compare correctly via the fallback branch."""
    naive_old = FROZEN_NOW.replace(tzinfo=None) - timedelta(minutes=60)
    sandbox = _make_sandbox(last_activity_at=naive_old)
    with patch(MODEL_DATETIME_MODULE) as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert sandbox.is_idle(idle_timeout_minutes=30) is True


# ===========================================================================
# set_expiry tests
# ===========================================================================


@pytest.mark.unit
def test_set_expiry_default_24_hours():
    """Default call sets expires_at to 24 hours from now."""
    sandbox = _make_sandbox()
    with patch(MODEL_DATETIME_MODULE) as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        sandbox.set_expiry()
    expected = FROZEN_NOW + timedelta(hours=24)
    assert sandbox.expires_at == expected


@pytest.mark.unit
def test_set_expiry_custom_hours():
    """Custom hours parameter is respected."""
    sandbox = _make_sandbox()
    with patch(MODEL_DATETIME_MODULE) as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        sandbox.set_expiry(hours=5)
    expected = FROZEN_NOW + timedelta(hours=5)
    assert sandbox.expires_at == expected


# ===========================================================================
# set_last_activity tests
# ===========================================================================


@pytest.mark.unit
def test_set_last_activity_sets_timestamp():
    """set_last_activity should set last_activity_at to the current UTC time."""
    sandbox = _make_sandbox(last_activity_at=None)
    with patch(MODEL_DATETIME_MODULE) as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        sandbox.set_last_activity()
    assert sandbox.last_activity_at == FROZEN_NOW


# ===========================================================================
# to_dict tests
# ===========================================================================


@pytest.mark.unit
def test_to_dict_returns_all_fields():
    """to_dict should return a dict containing every expected key with correct values."""
    now = FROZEN_NOW
    sandbox = _make_sandbox(
        id="abc-123",
        type=SandboxType.TERMINAL,
        status=SandboxStatus.STARTED,
        tunnel_url="https://example.com",
        container_id="cid-456",
        container_name="my-container",
        host_port="8888",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
        error_message=None,
        gpu_enabled=True,
        gpu_type="nvidia-tesla-t4",
        gpu_count=1,
    )

    result = sandbox.to_dict()

    assert result["id"] == "abc-123"
    assert result["type"] == "TERMINAL"
    assert result["status"] == "STARTED"
    assert result["tunnel_url"] == "https://example.com"
    assert result["container_id"] == "cid-456"
    assert result["container_name"] == "my-container"
    assert result["host_port"] == "8888"
    assert result["created_at"] == now.isoformat()
    assert result["updated_at"] == now.isoformat()
    assert result["expires_at"] == (now + timedelta(hours=24)).isoformat()
    assert result["error_message"] is None
    assert result["gpu_enabled"] is True
    assert result["gpu_type"] == "nvidia-tesla-t4"
    assert result["gpu_count"] == 1


@pytest.mark.unit
def test_to_dict_handles_none_timestamps():
    """to_dict should return None for timestamp fields that are not set."""
    sandbox = _make_sandbox(
        status=SandboxStatus.PENDING,
        type=SandboxType.TERMINAL,
        created_at=None,
        updated_at=None,
        expires_at=None,
    )

    result = sandbox.to_dict()

    assert result["created_at"] is None
    assert result["updated_at"] is None
    assert result["expires_at"] is None
