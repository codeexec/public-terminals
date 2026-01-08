"""
Configuration management for Terminal Server
"""

from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # ========================================
    # Settings in alphabetical order
    # ========================================

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

    K8S_IN_CLUSTER: bool = False
    K8S_NAMESPACE: str = "default"

    LOCALTUNNEL_HOST: str = "https://localtunnel.newsml.io"
    LOG_LEVEL: str = "INFO"

    REDIS_URL: str = "redis://localhost:6379/0"
    # Container path for resolv.conf files (mounted in API container)
    RESOLV_CONF_CONTAINER_DIR: str = "/app/terminal-container/tmp-resolv"
    # Host path for resolv.conf files (for gVisor DNS fix)
    RESOLV_CONF_HOST_DIR: str = "/home/jupyter/public-terminals/terminal-container/tmp-resolv"
    TERMINAL_IMAGE: str = "terminal-server:latest"
    TERMINAL_TTL_HOURS: int = 24

    # Enable gVisor for enhanced container isolation (requires runsc runtime)
    USE_GVISOR: bool = False
    WEB_BASE_URL: str = "http://localhost:8001"
    WEB_HOST: str = "0.0.0.0"
    WEB_PORT: int = 8001

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }


settings = Settings()
