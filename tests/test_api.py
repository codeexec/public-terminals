"""
Integration tests for Sandbox Server API
These tests require the API server to be running
"""

import pytest
import requests
import time
from typing import Generator

API_BASE = "http://localhost:8000"


@pytest.mark.integration
def test_health():
    """Test health endpoint"""
    response = requests.get(f"{API_BASE}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


@pytest.mark.integration
def test_list_sandboxes():
    """Test listing sandboxes"""
    response = requests.get(f"{API_BASE}/api/v1/sandboxes")
    assert response.status_code == 200
    data = response.json()
    assert "sandboxes" in data
    assert "total" in data
    assert isinstance(data["sandboxes"], list)
    assert isinstance(data["total"], int)


@pytest.mark.integration
def test_create_sandbox():
    """Test sandbox creation"""
    response = requests.post(f"{API_BASE}/api/v1/sandboxes", json={})
    assert response.status_code == 202
    data = response.json()

    sandbox_id = data.get("id")

    try:
        assert "id" in data
        assert "status" in data
        assert "expires_at" in data
        assert data["status"] in ["pending", "starting", "started"]
    finally:
        if sandbox_id:
            try:
                requests.delete(f"{API_BASE}/api/v1/sandboxes/{sandbox_id}")
            except Exception:
                pass  # Ignore cleanup errors


@pytest.fixture
def sandbox_id() -> Generator[str, None, None]:
    """Fixture to create a sandbox and return its ID"""
    response = requests.post(f"{API_BASE}/api/v1/sandboxes", json={})
    assert response.status_code == 202
    data = response.json()
    sandbox_id = data["id"]

    yield sandbox_id

    # Cleanup: delete the sandbox after test
    try:
        requests.delete(f"{API_BASE}/api/v1/sandboxes/{sandbox_id}")
    except Exception:
        pass  # Ignore cleanup errors


@pytest.mark.integration
def test_get_sandbox(sandbox_id: str):
    """Test getting sandbox details"""
    response = requests.get(f"{API_BASE}/api/v1/sandboxes/{sandbox_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sandbox_id
    assert "status" in data
    assert "container_id" in data


@pytest.mark.integration
def test_delete_sandbox(sandbox_id: str):
    """Test sandbox deletion"""
    response = requests.delete(f"{API_BASE}/api/v1/sandboxes/{sandbox_id}")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


@pytest.mark.integration
@pytest.mark.slow
def test_wait_for_sandbox_startup(sandbox_id: str):
    """Test waiting for sandbox to start (slow test)"""
    max_wait = 120
    start_time = time.time()

    while time.time() - start_time < max_wait:
        response = requests.get(f"{API_BASE}/api/v1/sandboxes/{sandbox_id}")
        data = response.json()

        if data["status"] == "started":
            assert data["tunnel_url"] is not None
            assert data["container_id"] is not None
            return

        if data["status"] == "failed":
            pytest.fail(f"Sandbox failed to start: {data.get('error_message')}")

        time.sleep(5)

    pytest.fail(f"Sandbox did not start within {max_wait} seconds")
