# Tests Directory

This directory contains Python tests for the Terminal Server API.

## Test Files

### `test_api.py`
Integration tests for the Terminal Server API endpoints:
- Health check
- Terminal creation
- Terminal retrieval
- Terminal listing
- Terminal deletion
- Status polling

**Usage:**
```bash
# Direct execution
python3 tests/test_api.py

# Via make
make test-api

# Using pytest (recommended)
pytest tests/test_api.py
pytest tests/test_api.py -v          # Verbose
pytest tests/test_api.py -k "health"  # Run specific test
```

## Test Configuration

- **pytest.ini**: Located in project root, configures pytest behavior
- Test markers:
  - `@pytest.mark.integration`: Tests requiring running services
  - `@pytest.mark.unit`: Standalone unit tests

## Requirements

Ensure the API server is running before executing tests:
```bash
docker-compose up -d
# or
make up
```

API should be available at `http://localhost:8000`
