"""
Configuration management for Terminal Server
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Literal


class Settings(BaseSettings):
    ADMIN_PASSWORD: str = "changeme"
    ADMIN_USERNAME: str = "admin"

    API_BASE_URL: str = "http://localhost:8000"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    CLEANUP_INTERVAL_MINUTES: int = 5
    CONTAINER_PLATFORM: Literal["docker", "kubernetes"] = "docker"

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/terminal_server"
    DOCKER_HOST: str = ""
    DOCKER_NETWORK: str = "public-terminals_default"

    GCP_PROJECT_ID: str = ""
    GCP_REGION: str = "us-central1"

    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_ALGORITHM: str = "HS256"
    JWT_SECRET_KEY: str = ""

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def ensure_jwt_secret(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "JWT_SECRET_KEY must be explicitly set. "
                "Generate one using: openssl rand -hex 32"
            )
        if len(v) < 32:
            raise ValueError(
                f"JWT_SECRET_KEY is too short ({len(v)} characters). "
                "Minimum length is 32 characters for security. "
                "Generate one using: openssl rand -hex 32"
            )
        return v

    K8S_IN_CLUSTER: bool = False
    K8S_NAMESPACE: str = "default"

    LOCALTUNNEL_HOST: str = "https://localtunnel.newsml.io"
    LOG_LEVEL: str = "INFO"

    REDIS_URL: str = "redis://localhost:6379/0"
    # Container path for resolv.conf files (mounted in API container)
    RESOLV_CONF_CONTAINER_DIR: str = "/app/terminal-container/tmp-resolv"
    # Host path for resolv.conf files (for gVisor DNS fix)
    RESOLV_CONF_HOST_DIR: str = (
        "/home/jupyter/public-terminals/terminal-container/tmp-resolv"
    )

    # Resource Limits
    MAX_CONTAINERS_PER_SERVER: int = 240
    CONTAINER_MEMORY_LIMIT: str = "1g"
    CONTAINER_CPU_LIMIT: float = 1.0

    TERMINAL_IDLE_TIMEOUT_SECONDS: int = 3600  # Default: 1 hour
    TERMINAL_IMAGE: str = "terminal-server:latest"
    TERMINAL_TTL_HOURS: int = 24

    @field_validator("TERMINAL_IDLE_TIMEOUT_SECONDS")
    @classmethod
    def validate_idle_timeout(cls, v: int) -> int:
        min_timeout = 600  # 10 minutes
        max_timeout = 86400  # 24 hours
        if v < min_timeout:
            raise ValueError(
                f"TERMINAL_IDLE_TIMEOUT_SECONDS must be at least {min_timeout} seconds (10 minutes)"
            )
        if v > max_timeout:
            raise ValueError(
                f"TERMINAL_IDLE_TIMEOUT_SECONDS must be at most {max_timeout} seconds (24 hours)"
            )
        return v

    # Enable gVisor for enhanced container isolation (requires runsc runtime)
    USE_GVISOR: bool = False
    WEB_BASE_URL: str = "http://localhost:8001"
    WEB_HOST: str = "0.0.0.0"
    WEB_PORT: int = 8001

    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}


settings = Settings()
