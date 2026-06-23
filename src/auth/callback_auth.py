"""
Callback Authentication
Generates and verifies HMAC-based tokens for container callbacks
"""

import hashlib
import hmac
from typing import Optional

from src.config import settings


def generate_callback_token(sandbox_id: str) -> str:
    """
    Generate a unique callback authentication token for a sandbox.

    Uses HMAC-SHA256 with the JWT secret key to create a token that:
    - Is unique per sandbox
    - Cannot be forged without knowing the secret
    - Does not expire (sandbox lifetime handles that)

    Args:
        sandbox_id: The sandbox ID to generate a token for

    Returns:
        Hexadecimal HMAC token
    """
    message = f"callback:{sandbox_id}".encode("utf-8")
    secret = settings.CALLBACK_SECRET.encode("utf-8")

    token = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return token


def verify_callback_token(sandbox_id: str, token: str) -> bool:
    """
    Verify that a callback token is valid for the given sandbox.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        sandbox_id: The sandbox ID from the callback
        token: The token provided in the callback

    Returns:
        True if token is valid, False otherwise
    """
    if not sandbox_id or not token:
        return False

    expected_token = generate_callback_token(sandbox_id)

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(token, expected_token)


def extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """
    Extract the token from an Authorization header.

    Args:
        authorization: The Authorization header value (e.g., "Bearer <token>")

    Returns:
        The token if present, None otherwise
    """
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]
