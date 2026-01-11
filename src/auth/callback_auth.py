"""
Callback Authentication
Generates and verifies HMAC-based tokens for container callbacks
"""

import hashlib
import hmac
from typing import Optional

from src.config import settings


def generate_callback_token(terminal_id: str) -> str:
    """
    Generate a unique callback authentication token for a terminal.

    Uses HMAC-SHA256 with the JWT secret key to create a token that:
    - Is unique per terminal
    - Cannot be forged without knowing the secret
    - Does not expire (terminal lifetime handles that)

    Args:
        terminal_id: The terminal ID to generate a token for

    Returns:
        Hexadecimal HMAC token
    """
    message = f"callback:{terminal_id}".encode('utf-8')
    secret = settings.JWT_SECRET_KEY.encode('utf-8')

    token = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return token


def verify_callback_token(terminal_id: str, token: str) -> bool:
    """
    Verify that a callback token is valid for the given terminal.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        terminal_id: The terminal ID from the callback
        token: The token provided in the callback

    Returns:
        True if token is valid, False otherwise
    """
    if not terminal_id or not token:
        return False

    expected_token = generate_callback_token(terminal_id)

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
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None

    return parts[1]
