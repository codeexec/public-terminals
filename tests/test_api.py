"""
Integration tests for Terminal Server API
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
def test_list_terminals():
    """Test listing terminals"""
    response = requests.get(f"{API_BASE}/api/v1/terminals")
    assert response.status_code == 200
    data = response.json()
    assert "terminals" in data
    assert "total" in data
    assert isinstance(data["terminals"], list)
    assert isinstance(data["total"], int)


@pytest.mark.integration
def test_create_terminal():
    """Test terminal creation"""
    response = requests.post(f"{API_BASE}/api/v1/terminals", json={})
    assert response.status_code == 202
    data = response.json()

    terminal_id = data.get("id")

    try:
        assert "id" in data
        assert "status" in data
        assert "expires_at" in data
        assert data["status"] in ["pending", "starting"]
    finally:
        if terminal_id:
            try:
                requests.delete(f"{API_BASE}/api/v1/terminals/{terminal_id}")
            except Exception:
                pass  # Ignore cleanup errors


@pytest.fixture
def terminal_id() -> Generator[str, None, None]:
    """Fixture to create a terminal and return its ID"""
    response = requests.post(f"{API_BASE}/api/v1/terminals", json={})
    assert response.status_code == 202
    data = response.json()
    terminal_id = data["id"]

    yield terminal_id

    # Cleanup: delete the terminal after test
    try:
        requests.delete(f"{API_BASE}/api/v1/terminals/{terminal_id}")
    except Exception:
        pass  # Ignore cleanup errors


@pytest.mark.integration
def test_get_terminal(terminal_id: str):
    """Test getting terminal details"""
    response = requests.get(f"{API_BASE}/api/v1/terminals/{terminal_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == terminal_id
    assert "status" in data
    assert "container_id" in data


@pytest.mark.integration
def test_delete_terminal(terminal_id: str):
    """Test terminal deletion"""
    response = requests.delete(f"{API_BASE}/api/v1/terminals/{terminal_id}")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


@pytest.mark.integration
@pytest.mark.slow
def test_wait_for_terminal_startup(terminal_id: str):
    """Test waiting for terminal to start (slow test)"""
    max_wait = 120
    start_time = time.time()

    while time.time() - start_time < max_wait:
        response = requests.get(f"{API_BASE}/api/v1/terminals/{terminal_id}")
        data = response.json()

        if data["status"] == "started":
            assert data["tunnel_url"] is not None
            assert data["container_id"] is not None
            return

        if data["status"] == "failed":
            pytest.fail(f"Terminal failed to start: {data.get('error_message')}")

        time.sleep(5)

    pytest.fail(f"Terminal did not start within {max_wait} seconds")
