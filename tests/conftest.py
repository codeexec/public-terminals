"""
Shared test fixtures for the public-terminals test suite.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


from src.constants import SandboxStatus, SandboxType


@pytest.fixture
def mock_settings():
    """Fixture that patches common settings with test values.

    Patches the global ``settings`` object from ``src.config`` and
    returns the mock so tests can override individual attributes.
    """
    with patch("src.config.settings") as _mock_settings:
        _mock_settings.CONTAINER_PLATFORM = "kubernetes"
        _mock_settings.CONTAINER_CPU_LIMIT = 1.0
        _mock_settings.CONTAINER_MEMORY_LIMIT = "1G"
        _mock_settings.MAX_CONTAINERS_PER_SERVER = 10
        _mock_settings.DOCKER_NETWORK = "test-network"
        _mock_settings.SANDBOX_BASE_IMAGE = "base-image"
        _mock_settings.JUPYTERLITE_IMAGE = "jupyter-image"
        _mock_settings.GPU_TERMINAL_IMAGE = "gpu-image"
        _mock_settings.API_BASE_URL = "http://api"
        _mock_settings.LOCALTUNNEL_HOST = "http://tunnel"
        _mock_settings.SANDBOX_IDLE_TIMEOUT_SECONDS = 3600
        _mock_settings.GPU_ENABLED = False
        _mock_settings.GPU_TYPE = "nvidia-l4"
        _mock_settings.GPU_COUNT = 1
        _mock_settings.GKE_AUTOPILOT_ENABLED = True
        _mock_settings.K8S_NAMESPACE = "test-namespace"
        _mock_settings.K8S_IN_CLUSTER = False
        _mock_settings.SANDBOX_TTL_HOURS = 24
        yield _mock_settings


@pytest.fixture
def mock_db():
    """A MagicMock SQLAlchemy session with common query-chain setup.

    Provides ``query().filter().first()`` and
    ``query().filter().all()`` chaining out of the box.
    """
    session = MagicMock()
    query_mock = MagicMock()
    session.query.return_value = query_mock
    query_mock.filter.return_value = query_mock
    query_mock.filter_by.return_value = query_mock
    query_mock.first.return_value = None
    query_mock.all.return_value = []
    query_mock.count.return_value = 0
    return session


@pytest.fixture
def mock_sandbox_factory():
    """Factory fixture that creates mock Sandbox objects with configurable attributes.

    Call the returned callable with keyword arguments to override any
    default attribute.  The mock also wires up ``is_expired()`` and
    ``is_idle()`` return values.
    """

    def _factory(**kwargs):
        now = datetime.now(timezone.utc)
        defaults = {
            "id": "test-sandbox-1",
            "status": SandboxStatus.STARTED,
            "type": SandboxType.TERMINAL,
            "user_id": "test-user-1",
            "container_id": "container-1",
            "container_name": "sandbox-test-sandbox-1",
            "tunnel_url": "http://test-tunnel.example.com",
            "host_port": "8001",
            "created_at": now,
            "updated_at": now,
            "expires_at": now + timedelta(hours=24),
            "last_activity_at": None,
            "error_message": None,
            "gpu_enabled": False,
            "gpu_type": None,
            "gpu_count": None,
            "deleted_at": None,
        }
        defaults.update(kwargs)

        sandbox = MagicMock()
        for attr, value in defaults.items():
            setattr(sandbox, attr, value)

        # Wire up method return values
        sandbox.is_expired.return_value = defaults.get("_is_expired", False)
        sandbox.is_idle.return_value = defaults.get("_is_idle", False)

        return sandbox

    return _factory


@pytest.fixture
def docker_service(mock_settings):
    """Fixture that creates a DockerContainerService with mocked Docker client and settings.

    The ``mock_settings`` fixture is used to patch ``src.config.settings``,
    and the Docker ``APIClient`` is fully mocked so no real daemon is needed.
    Returns a ``(service, mock_docker_client)`` tuple.
    """
    with patch("src.services.docker_service.settings", mock_settings), \
         patch("docker.APIClient") as mock_docker_cls:
        mock_docker_client = mock_docker_cls.return_value
        from src.services.docker_service import DockerContainerService

        service = DockerContainerService()
        yield service, mock_docker_client


@pytest.fixture
def k8s_service(mock_settings):
    """Fixture that creates a KubernetesContainerService with mocked K8s config and settings.

    The ``mock_settings`` fixture is used to patch ``src.config.settings``,
    and ``kubernetes.config`` is fully mocked so no real cluster is needed.
    Returns a ``(service, mock_settings)`` tuple.
    """
    with patch("src.services.kubernetes_service.settings", mock_settings), \
         patch("kubernetes.config"):
        from src.services.kubernetes_service import KubernetesContainerService

        service = KubernetesContainerService()
        yield service, mock_settings
