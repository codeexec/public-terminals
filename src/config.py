"""
Configuration management for Terminal Server
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from typing import Literal


class Settings(BaseSettings):
    ADMIN_PASSWORD: str = "changeme"
    ADMIN_USERNAME: str = "admin"
    ENV: str = "development"

    API_BASE_URL: str = "http://localhost:8000"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    CLEANUP_INTERVAL_MINUTES: int = 5
    CONTAINER_PLATFORM: Literal["docker", "kubernetes"] = "kubernetes"

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/terminal_server"
    DOCKER_HOST: str = ""
    DOCKER_NETWORK: str = "public-terminals_default"

    GCP_PROJECT_ID: str = "beatrix-user-project"
    GCP_REGION: str = "us-central1"

    # GKE Autopilot Configuration
    GKE_AUTOPILOT_ENABLED: bool = (
        True  # Enable GKE Autopilot mode (sub-mode of kubernetes)
    )

    # GPU Configuration (only applies when GKE_AUTOPILOT_ENABLED=True)
    GPU_ENABLED: bool = False  # Enable GPU support for terminals
    GPU_TYPE: str = "nvidia-l4"  # GPU type: nvidia-l4, nvidia-t4, nvidia-a100-80gb, nvidia-h100-80gb
    GPU_COUNT: int = 1  # Number of GPUs per terminal
    GPU_TERMINAL_IMAGE: str = (
        ""  # Optional GPU-specific image (falls back to TERMINAL_IMAGE)
    )

    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_ALGORITHM: str = "HS256"
    JWT_SECRET_KEY: str = ""
    CALLBACK_SECRET: str = ""
    ALLOWED_CORS_ORIGINS: list[str] = ["*"]
    POLL_INTERVAL_BASE: float = 0.5
    WARM_POOL_REPLENISH_INTERVAL: int = 5
    WARM_POOL_MAX_PARALLEL_CREATES: int = 2

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if self.ENV == "production" and self.ADMIN_PASSWORD == "changeme":
            raise ValueError(
                "ADMIN_PASSWORD must be changed from the default 'changeme' in production environment!"
            )
        if not self.CALLBACK_SECRET:
            self.CALLBACK_SECRET = self.JWT_SECRET_KEY
        return self

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
    K8S_NAMESPACE: str = "terminals"

    LOCALTUNNEL_HOST: str = "https://localtunnel.newsml.io"
    LOG_LEVEL: str = "INFO"

    REDIS_URL: str = "redis://localhost:6379/0"
    # Container path for resolv.conf files (mounted in API container)
    RESOLV_CONF_CONTAINER_DIR: str = "/app/containers/base/tmp-resolv"
    # Host path for resolv.conf files (for gVisor DNS fix)
    RESOLV_CONF_HOST_DIR: str = (
        "/home/jupyter/public-terminals/containers/base/tmp-resolv"
    )

    # Resource Limits
    MAX_CONTAINERS_PER_SERVER: int = 240
    CONTAINER_MEMORY_LIMIT: str = "1g"
    CONTAINER_CPU_LIMIT: float = 1.0

    SANDBOX_IDLE_TIMEOUT_SECONDS: int = 3600  # Default: 1 hour
    SANDBOX_BASE_IMAGE: str = "us-central1-docker.pkg.dev/beatrix-user-project/terminals/terminal-server:latest"
    JUPYTERLITE_IMAGE: str = "us-central1-docker.pkg.dev/beatrix-user-project/terminals/jupyterlite-server:latest"
    SANDBOX_TTL_HOURS: int = 24

    # Warm Pool Configuration
    WARM_POOL_ENABLED: bool = True  # Enable pre-warmed container pool
    WARM_POOL_SIZE: int = 2  # Number of containers to keep warm
    WARM_POOL_GPU_SIZE: int = (
        1  # Number of GPU containers to keep warm (smaller due to cost)
    )

    @field_validator("SANDBOX_IDLE_TIMEOUT_SECONDS")
    @classmethod
    def validate_idle_timeout(cls, v: int) -> int:
        min_timeout = 600  # 10 minutes
        max_timeout = 86400  # 24 hours
        if v < min_timeout:
            raise ValueError(
                f"SANDBOX_IDLE_TIMEOUT_SECONDS must be at least {min_timeout} seconds (10 minutes)"
            )
        if v > max_timeout:
            raise ValueError(
                f"SANDBOX_IDLE_TIMEOUT_SECONDS must be at most {max_timeout} seconds (24 hours)"
            )
        return v

    @field_validator("GPU_TYPE")
    @classmethod
    def validate_gpu_type(cls, v: str) -> str:
        valid_types = [
            "nvidia-l4",
            "nvidia-t4",
            "nvidia-a100-80gb",
            "nvidia-h100-80gb",
            "nvidia-tesla-t4",
            "nvidia-tesla-a100",
        ]
        if v not in valid_types:
            raise ValueError(f"GPU_TYPE must be one of: {valid_types}")
        return v

    @field_validator("GPU_COUNT")
    @classmethod
    def validate_gpu_count(cls, v: int) -> int:
        if v < 1 or v > 8:
            raise ValueError("GPU_COUNT must be between 1 and 8")
        return v

    # Enable gVisor for enhanced container isolation (requires runsc runtime)
    USE_GVISOR: bool = False
    WEB_BASE_URL: str = "http://localhost:8001"
    WEB_HOST: str = "0.0.0.0"
    WEB_PORT: int = 8001

    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}


settings = Settings()
