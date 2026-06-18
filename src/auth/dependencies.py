"""
FastAPI dependencies for authentication
"""

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from src.auth.jwt_handler import verify_token
from src.auth.callback_auth import verify_callback_token, extract_bearer_token

security = HTTPBearer()


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Dependency to validate JWT token and ensure user is admin

    Args:
        credentials: HTTP Bearer token from Authorization header

    Returns:
        Admin username if valid

    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials
    username = verify_token(token)

    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return username


async def verify_callback_auth(
    sandbox_id: str,
    authorization: Optional[str] = Header(None),
) -> str:
    """
    Dependency to validate callback authentication token.

    Callbacks from containers must include a valid HMAC token in the
    Authorization header that matches the sandbox_id they're reporting for.

    Args:
        sandbox_id: The sandbox ID from the callback request body
        authorization: Authorization header (Bearer <token>)

    Returns:
        The sandbox_id if authentication succeeds

    Raises:
        HTTPException: If token is missing or invalid
    """
    # Extract token from Bearer header
    token = extract_bearer_token(authorization)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify the token matches the sandbox_id
    if not verify_callback_token(sandbox_id, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid callback token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return sandbox_id
