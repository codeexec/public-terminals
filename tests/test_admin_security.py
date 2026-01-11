import pytest
from unittest.mock import patch
from src.config import Settings
from src.api.routes.admin import admin_login
from src.auth.schemas import LoginRequest
from fastapi import HTTPException


@pytest.mark.unit
def test_jwt_secret_missing():
    """Test that JWT_SECRET_KEY validation fails if empty"""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError) as exc:
            Settings(JWT_SECRET_KEY="")
        assert "must be explicitly set" in str(exc.value)


@pytest.mark.unit
def test_jwt_secret_too_short():
    """Test that JWT_SECRET_KEY validation fails if too short"""
    with pytest.raises(ValueError) as exc:
        Settings(JWT_SECRET_KEY="too-short")
    assert "is too short" in str(exc.value)


@pytest.mark.unit
def test_jwt_secret_provided():
    """Test that provided JWT_SECRET_KEY is respected"""
    secret = "a" * 32
    settings = Settings(JWT_SECRET_KEY=secret)
    assert settings.JWT_SECRET_KEY == secret


@pytest.mark.unit
@pytest.mark.asyncio
async def test_admin_login_success():
    """Test successful admin login"""
    with patch("src.api.routes.admin.settings") as mock_settings:
        mock_settings.ADMIN_USERNAME = "admin"
        mock_settings.ADMIN_PASSWORD = "password"
        # Mock JWT settings
        mock_settings.JWT_SECRET_KEY = "s" * 32
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60

        req = LoginRequest(username="admin", password="password")
        resp = await admin_login(req)

        assert resp.access_token is not None
        assert resp.token_type == "bearer"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_admin_login_failure():
    """Test failed admin login"""
    with patch("src.api.routes.admin.settings") as mock_settings:
        mock_settings.ADMIN_USERNAME = "admin"
        mock_settings.ADMIN_PASSWORD = "password"

        # Wrong password
        req = LoginRequest(username="admin", password="wrong")
        with pytest.raises(HTTPException) as exc:
            await admin_login(req)
        assert exc.value.status_code == 401

        # Wrong username
        req = LoginRequest(username="wrong", password="password")
        with pytest.raises(HTTPException) as exc:
            await admin_login(req)
        assert exc.value.status_code == 401
