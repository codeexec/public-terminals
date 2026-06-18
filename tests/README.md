# Sandbox Server Tests

This directory contains Python tests for the Sandbox Server API.

## Running Tests

### 1. Unit Tests
Tests that don't require external services (Docker, DB):
```bash
pytest -m unit
```

### 2. Integration Tests
Tests that require a running API server and database:
```bash
pytest -m integration
```

### 3. Run All Tests
```bash
pytest
```

## Test Files

- `test_api.py`: Core Sandbox CRUD operations.
- `test_admin_security.py`: Admin login and JWT verification.
- `test_admin_stats.py`: System and sandbox resource usage stats.
- `test_container_limits.py`: Max container capacity enforcement.
- `test_stopped_sandboxes.py`: Auto-restart and lifecycle of stopped sandboxes.

## Requirements
- `pytest`
- `pytest-asyncio`
- `httpx`
- `sqlalchemy`
- `pydantic`
