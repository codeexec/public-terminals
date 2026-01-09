"""
Pydantic schemas for authentication
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Request schema for admin login"""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Response schema for successful login"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
