"""
Unit tests for Pydantic API schemas.

Tests cover: SandboxCreate, SandboxResponse, SandboxCallbackRequest.
Validates default values, field validators, enum handling, bounds, and errors.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.api.schemas import SandboxCreate, SandboxResponse, SandboxCallbackRequest
from src.constants import SandboxStatus, SandboxType


# ===========================================================================
# SandboxCreate tests
# ===========================================================================


@pytest.mark.unit
def test_create_default_type_is_terminal():
    """Creating with no arguments should default type to TERMINAL."""
    schema = SandboxCreate()
    assert schema.type == SandboxType.TERMINAL


@pytest.mark.unit
def test_create_type_case_insensitive():
    """Lowercase type string should be uppercased by the field validator."""
    schema = SandboxCreate(type="terminal")
    assert schema.type == SandboxType.TERMINAL


@pytest.mark.unit
def test_create_jupyterlite_type():
    """JUPYTERLITE type should be accepted (case-insensitive)."""
    schema = SandboxCreate(type="jupyterlite")
    assert schema.type == SandboxType.JUPYTERLITE


@pytest.mark.unit
def test_create_invalid_type_raises():
    """An invalid sandbox type string should raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        SandboxCreate(type="INVALID_TYPE")
    assert "type" in str(exc_info.value)


@pytest.mark.unit
def test_create_gpu_optional():
    """use_gpu should default to None and accept True/False."""
    default = SandboxCreate()
    assert default.use_gpu is None

    with_gpu = SandboxCreate(use_gpu=True)
    assert with_gpu.use_gpu is True

    without_gpu = SandboxCreate(use_gpu=False)
    assert without_gpu.use_gpu is False


# ===========================================================================
# SandboxResponse tests
# ===========================================================================

_NOW_ISO = datetime.now(timezone.utc)

_VALID_RESPONSE_DATA = {
    "id": "sandbox-abc",
    "type": "TERMINAL",
    "status": "STARTED",
    "created_at": _NOW_ISO.isoformat(),
    "updated_at": _NOW_ISO.isoformat(),
}


@pytest.mark.unit
def test_response_validates_from_orm_attributes():
    """SandboxResponse should accept an ORM-like object via from_attributes."""

    class FakeSandboxORM:
        id = "orm-id-1"
        user_id = None
        type = SandboxType.TERMINAL
        status = SandboxStatus.STARTED
        tunnel_url = None
        container_id = None
        container_name = None
        host_port = None
        created_at = _NOW_ISO
        updated_at = _NOW_ISO
        expires_at = None
        last_activity_at = None
        error_message = None
        gpu_enabled = False
        gpu_type = None
        gpu_count = None

    response = SandboxResponse.model_validate(FakeSandboxORM(), from_attributes=True)

    assert response.id == "orm-id-1"
    assert response.type == SandboxType.TERMINAL
    assert response.status == SandboxStatus.STARTED
    assert response.gpu_enabled is False


@pytest.mark.unit
def test_response_accepts_lowercase_status():
    """Lowercase status/type strings should be uppercased by the validator."""
    data = {**_VALID_RESPONSE_DATA, "status": "started", "type": "terminal"}
    response = SandboxResponse(**data)
    assert response.status == SandboxStatus.STARTED
    assert response.type == SandboxType.TERMINAL


@pytest.mark.unit
def test_response_accepts_enum_value_directly():
    """Enum instances should be accepted directly."""
    data = {
        **_VALID_RESPONSE_DATA,
        "status": SandboxStatus.PENDING,
        "type": SandboxType.JUPYTERLITE,
    }
    response = SandboxResponse(**data)
    assert response.status == SandboxStatus.PENDING
    assert response.type == SandboxType.JUPYTERLITE


@pytest.mark.unit
def test_response_rejects_invalid_status():
    """An invalid status string should raise ValidationError."""
    data = {**_VALID_RESPONSE_DATA, "status": "NONEXISTENT"}
    with pytest.raises(ValidationError) as exc_info:
        SandboxResponse(**data)
    assert "status" in str(exc_info.value)


# ===========================================================================
# SandboxCallbackRequest tests
# ===========================================================================


@pytest.mark.unit
def test_callback_valid_tunnel_url_http():
    """HTTP tunnel URL should be accepted."""
    req = SandboxCallbackRequest(tunnel_url="http://localhost:8888")
    assert req.tunnel_url == "http://localhost:8888"


@pytest.mark.unit
def test_callback_valid_tunnel_url_https():
    """HTTPS tunnel URL should be accepted."""
    req = SandboxCallbackRequest(tunnel_url="https://my-tunnel.example.com")
    assert req.tunnel_url == "https://my-tunnel.example.com"


@pytest.mark.unit
def test_callback_invalid_tunnel_url_no_protocol():
    """Tunnel URL without http/https protocol should raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        SandboxCallbackRequest(tunnel_url="ftp://bad-protocol.com")
    assert "tunnel_url" in str(exc_info.value)


@pytest.mark.unit
def test_callback_allows_none_tunnel_url():
    """None tunnel_url should be allowed (it is optional)."""
    req = SandboxCallbackRequest(tunnel_url=None)
    assert req.tunnel_url is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "value,should_pass",
    [
        (0, True),
        (50.5, True),
        (100, True),
        (-0.1, False),
        (100.1, False),
    ],
    ids=["min=0", "mid=50.5", "max=100", "below_min", "above_max"],
)
def test_callback_cpu_percent_bounds(value, should_pass):
    """cpu_percent must be between 0 and 100 inclusive."""
    if should_pass:
        req = SandboxCallbackRequest(cpu_percent=value)
        assert req.cpu_percent == value
    else:
        with pytest.raises(ValidationError) as exc_info:
            SandboxCallbackRequest(cpu_percent=value)
        assert "cpu_percent" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "value,should_pass",
    [
        (0, True),
        (512.0, True),
        (100000, True),
        (-1, False),
        (100001, False),
    ],
    ids=["min=0", "mid=512", "max=100000", "below_min", "above_max"],
)
def test_callback_memory_mb_bounds(value, should_pass):
    """memory_mb must be between 0 and 100000 inclusive."""
    if should_pass:
        req = SandboxCallbackRequest(memory_mb=value)
        assert req.memory_mb == value
    else:
        with pytest.raises(ValidationError) as exc_info:
            SandboxCallbackRequest(memory_mb=value)
        assert "memory_mb" in str(exc_info.value)


@pytest.mark.unit
def test_callback_extra_fields_ignored():
    """Extra fields should be silently ignored (model_config extra='ignore')."""
    req = SandboxCallbackRequest(
        tunnel_url="https://example.com",
        some_unknown_field="should be ignored",
        another_extra=42,
    )
    assert req.tunnel_url == "https://example.com"
    assert not hasattr(req, "some_unknown_field")
    assert not hasattr(req, "another_extra")
