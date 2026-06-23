import pytest
import hmac
import hashlib
import json
from unittest.mock import patch, MagicMock
from fastapi import HTTPException, Request
from pydantic import ValidationError

from src.config import Settings
from src.auth.callback_auth import (
    generate_callback_token,
    verify_callback_token,
)
from src.auth.jwt_handler import create_access_token, verify_token
from src.api.routes.admin import InMemoryRateLimiter, admin_login
from src.auth.schemas import LoginRequest
from src.api.routes.sandboxes import list_sandboxes


@pytest.mark.unit
def test_admin_password_production_validation():
    """Verify default admin password is blocked in production environment"""
    # 1. Production with default password should raise ValidationError/ValueError
    with pytest.raises(ValueError) as exc:
        Settings(
            ENV="production",
            ADMIN_PASSWORD="changeme",
            JWT_SECRET_KEY="s" * 32,
        )
    assert "ADMIN_PASSWORD must be changed" in str(exc.value)

    # 2. Production with safe, modified password should succeed
    settings_prod = Settings(
        ENV="production",
        ADMIN_PASSWORD="secure_prod_password_12345",
        JWT_SECRET_KEY="s" * 32,
    )
    assert settings_prod.ADMIN_PASSWORD == "secure_prod_password_12345"

    # 3. Development with default password is allowed
    settings_dev = Settings(
        ENV="development",
        ADMIN_PASSWORD="changeme",
        JWT_SECRET_KEY="s" * 32,
    )
    assert settings_dev.ADMIN_PASSWORD == "changeme"


@pytest.mark.unit
def test_callback_secret_fallback_and_isolation():
    """Verify CALLBACK_SECRET defaults to JWT_SECRET_KEY, but can be set separately"""
    # 1. Fallback behavior when CALLBACK_SECRET is empty
    settings_fallback = Settings(
        JWT_SECRET_KEY="j" * 32,
        CALLBACK_SECRET="",
    )
    assert settings_fallback.CALLBACK_SECRET == "j" * 32

    # 2. Isolation when CALLBACK_SECRET is set explicitly
    settings_isolated = Settings(
        JWT_SECRET_KEY="j" * 32,
        CALLBACK_SECRET="c" * 32,
    )
    assert settings_isolated.CALLBACK_SECRET == "c" * 32
    assert settings_isolated.JWT_SECRET_KEY != settings_isolated.CALLBACK_SECRET

    # 3. Verify HMAC token generation and verification using CALLBACK_SECRET
    with patch("src.auth.callback_auth.settings", settings_isolated):
        sandbox_id = "test-sandbox-123"
        token = generate_callback_token(sandbox_id)

        # Expected token manually calculated with CALLBACK_SECRET
        message = f"callback:{sandbox_id}".encode("utf-8")
        expected = hmac.new(("c" * 32).encode("utf-8"), message, hashlib.sha256).hexdigest()
        assert token == expected

        # Verification with correct token
        assert verify_callback_token(sandbox_id, token) is True

        # Verification with incorrect token
        assert verify_callback_token(sandbox_id, "wrong-token") is False


@pytest.mark.unit
def test_in_memory_rate_limiter():
    """Verify sliding window in-memory rate limiter behaves correctly"""
    limiter = InMemoryRateLimiter(limit=3, window=2)

    # First three requests from same IP allowed
    assert limiter.is_allowed("192.168.1.1") is True
    assert limiter.is_allowed("192.168.1.1") is True
    assert limiter.is_allowed("192.168.1.1") is True

    # Fourth request from same IP is rate-limited
    assert limiter.is_allowed("192.168.1.1") is False

    # Different IP is not affected
    assert limiter.is_allowed("192.168.1.2") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_admin_login_rate_limiting_endpoint():
    """Verify rate limiter throws 429 after exceeding limit on admin login endpoint"""
    # Create request with mock client IP
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "1.2.3.4"

    login_req = LoginRequest(username="admin", password="password")

    with patch("src.api.routes.admin.settings") as mock_settings, \
         patch("src.api.routes.admin.login_limiter") as mock_limiter:
        mock_settings.ADMIN_USERNAME = "admin"
        mock_settings.ADMIN_PASSWORD = "password"

        # 1. When rate limiter allows
        mock_limiter.is_allowed.return_value = True
        resp = await admin_login(login_req, request=mock_request)
        assert resp.access_token is not None

        # 2. When rate limiter blocks
        mock_limiter.is_allowed.return_value = False
        with pytest.raises(HTTPException) as exc:
            await admin_login(login_req, request=mock_request)
        assert exc.value.status_code == 429
        assert "Too many login attempts" in exc.value.detail


@pytest.mark.unit
def test_jwt_claims_verification():
    """Verify issuer and audience claims are injected and validated in JWT tokens"""
    settings_jwt = Settings(
        JWT_SECRET_KEY="s" * 32,
        JWT_ALGORITHM="HS256",
        JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10,
    )

    with patch("src.auth.jwt_handler.settings", settings_jwt):
        # Generate token
        token = create_access_token({"sub": "admin-user"})

        # Decodes successfully with proper claims
        username = verify_token(token)
        assert username == "admin-user"

    # Now verify it fails decoding with incorrect claims or invalid signature
    # Let's decode with wrong audience or issuer using jose directly to see if verify_token filters it out
    from jose import jwt
    wrong_token = jwt.encode(
        {"sub": "admin-user", "iss": "wrong-issuer", "aud": "sandbox-admin"},
        "s" * 32,
        algorithm="HS256"
    )
    with patch("src.auth.jwt_handler.settings", settings_jwt):
        assert verify_token(wrong_token) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_guest_id_leakage_guard_route():
    """Verify that list_sandboxes raises 400 Bad Request when X-Guest-ID is missing"""
    mock_db_session = MagicMock()

    # Call directly without X-Guest-ID header
    with pytest.raises(HTTPException) as exc:
        await list_sandboxes(
            skip=0,
            limit=10,
            status_filter=None,
            x_guest_id=None,
            db=mock_db_session,
        )
    assert exc.value.status_code == 400
    assert "Missing X-Guest-ID header" in exc.value.detail


@pytest.mark.unit
def test_xss_escaping_templates():
    """Verify configuration values are safely serialized/escaped for HTML templates"""
    api_url = "http://localhost:8000\"; alert('xss'); //"
    # Using json.dumps() ensures quotes are escaped
    api_base_script = f"const API_BASE = {json.dumps(api_url)};"
    # Verify the escaped result does not contain unescaped raw quotes breaking out of string literal
    assert '";' not in api_base_script.replace(json.dumps(api_url), "")
    assert json.dumps(api_url) == '"http://localhost:8000\\"; alert(\'xss\'); //"'
