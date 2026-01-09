import pytest
from unittest.mock import patch, MagicMock
from src.config import Settings
from src.api.routes.admin import admin_login
from src.auth.schemas import LoginRequest
from fastapi import HTTPException

def test_jwt_secret_generation():
    """Test that JWT_SECRET_KEY is generated if empty"""
    # Create settings with empty secret
    # We need to bypass environment variables potentially setting it
    with patch.dict("os.environ", {}, clear=True):
        settings = Settings(JWT_SECRET_KEY="")
        assert settings.JWT_SECRET_KEY != ""
        assert len(settings.JWT_SECRET_KEY) > 0
        
        # Verify it generates different keys for different instances (wait, no, it should be stable per instance)
        # But if we instantiate it again, it will be different if we use secrets.token_urlsafe inside validator
        settings_2 = Settings(JWT_SECRET_KEY="")
        assert settings.JWT_SECRET_KEY != settings_2.JWT_SECRET_KEY

def test_jwt_secret_provided():
    """Test that provided JWT_SECRET_KEY is respected"""
    settings = Settings(JWT_SECRET_KEY="my-secret-key")
    assert settings.JWT_SECRET_KEY == "my-secret-key"

@pytest.mark.asyncio
async def test_admin_login_success():
    """Test successful admin login"""
    with patch("src.api.routes.admin.settings") as mock_settings:
        mock_settings.ADMIN_USERNAME = "admin"
        mock_settings.ADMIN_PASSWORD = "password"
        # Mock JWT settings
        mock_settings.JWT_SECRET_KEY = "secret"
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60
        
        req = LoginRequest(username="admin", password="password")
        resp = await admin_login(req)
        
        assert resp.access_token is not None
        assert resp.token_type == "bearer"

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
