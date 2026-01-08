"""
Configuration management for Terminal Server
"""
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_BASE_URL: str = "http://localhost:8000"

    # Database Configuration
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/terminal_server"

    # Container Configuration
    CONTAINER_PLATFORM: Literal["docker", "kubernetes"] = "docker"
    TERMINAL_IMAGE: str = "terminal-server:latest"
    TERMINAL_TTL_HOURS: int = 24

    # Kubernetes Configuration (if using GKE)
    K8S_NAMESPACE: str = "default"
    K8S_IN_CLUSTER: bool = False

    # Docker Configuration (if using Docker)
    DOCKER_HOST: str = "unix://var/run/docker.sock"

    # Localtunnel Configuration
    LOCALTUNNEL_HOST: str = "https://localtunnel.me"

    # Cleanup Service
    CLEANUP_INTERVAL_MINUTES: int = 5

    # Redis (for Celery)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Logging
    LOG_LEVEL: str = "INFO"

    # GCP Configuration
    GCP_PROJECT_ID: str = ""
    GCP_REGION: str = "us-central1"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
