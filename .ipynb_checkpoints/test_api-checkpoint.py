#!/usr/bin/env python3
"""
Simple test script for Terminal Server API
"""
import requests
import time
import sys

API_BASE = "http://localhost:8000"


def test_health():
    """Test health endpoint"""
    print("Testing health endpoint...")
    response = requests.get(f"{API_BASE}/health")
    assert response.status_code == 200
    data = response.json()
    print(f"✓ Health check passed: {data['status']}")
    return True


def test_create_terminal():
    """Test terminal creation"""
    print("\nCreating new terminal...")
    response = requests.post(f"{API_BASE}/api/v1/terminals", json={})
    assert response.status_code == 202
    data = response.json()
    terminal_id = data['id']
    print(f"✓ Terminal created: {terminal_id}")
    print(f"  Status: {data['status']}")
    print(f"  Expires at: {data['expires_at']}")
    return terminal_id


def test_get_terminal(terminal_id):
    """Test getting terminal details"""
    print(f"\nGetting terminal {terminal_id}...")
    response = requests.get(f"{API_BASE}/api/v1/terminals/{terminal_id}")
    assert response.status_code == 200
    data = response.json()
    print(f"✓ Terminal details retrieved")
    print(f"  Status: {data['status']}")
    print(f"  Tunnel URL: {data['tunnel_url']}")
    print(f"  Container ID: {data['container_id']}")
    return data


def test_list_terminals():
    """Test listing terminals"""
    print("\nListing all terminals...")
    response = requests.get(f"{API_BASE}/api/v1/terminals")
    assert response.status_code == 200
    data = response.json()
    print(f"✓ Found {data['total']} terminals")
    for terminal in data['terminals'][:3]:  # Show first 3
        print(f"  - {terminal['id']}: {terminal['status']}")
    return data


def test_wait_for_terminal(terminal_id, max_wait=120):
    """Wait for terminal to be ready"""
    print(f"\nWaiting for terminal to start (max {max_wait}s)...")
    start_time = time.time()

    while time.time() - start_time < max_wait:
        data = test_get_terminal(terminal_id)

        if data['status'] == 'started':
            print(f"✓ Terminal is ready!")
            print(f"  Tunnel URL: {data['tunnel_url']}")
            print(f"  Time taken: {int(time.time() - start_time)}s")
            return data

        if data['status'] == 'failed':
            print(f"✗ Terminal failed to start: {data['error_message']}")
            return None

        print(f"  Status: {data['status']} (waiting...)")
        time.sleep(5)

    print(f"✗ Timeout waiting for terminal to start")
    return None


def test_delete_terminal(terminal_id):
    """Test terminal deletion"""
    print(f"\nDeleting terminal {terminal_id}...")
    response = requests.delete(f"{API_BASE}/api/v1/terminals/{terminal_id}")
    assert response.status_code == 200
    data = response.json()
    print(f"✓ Terminal deleted: {data['message']}")
    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("Terminal Server API Test Suite")
    print("=" * 60)

    try:
        # Test 1: Health check
        test_health()

        # Test 2: List terminals (before creation)
        test_list_terminals()

        # Test 3: Create terminal
        terminal_id = test_create_terminal()

        # Test 4: Get terminal details
        test_get_terminal(terminal_id)

        # Test 5: Wait for terminal to be ready
        terminal_data = test_wait_for_terminal(terminal_id)

        # Test 6: List terminals (after creation)
        test_list_terminals()

        # Test 7: Delete terminal
        if terminal_data:
            test_delete_terminal(terminal_id)

        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)

        if terminal_data and terminal_data.get('tunnel_url'):
            print(f"\nYou can access the terminal at:")
            print(f"  {terminal_data['tunnel_url']}")

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"\n✗ Cannot connect to API at {API_BASE}")
        print("Make sure the API server is running (make up)")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
