# Scripts Directory

This directory contains shell scripts for managing and testing the Terminal Server.

## Available Scripts

### `run_test.sh`
Full integration test script that:
- Starts all services (API, Web, DB, Redis, Celery)
- Creates a test terminal
- Waits for terminal to be ready
- Verifies health endpoints
- Displays access URLs
- Prompts for cleanup

**Usage:**
```bash
./scripts/run_test.sh          # Run full test
./scripts/run_test.sh --stop   # Stop services only
```

### `setup.sh`
Initial setup script for project initialization.

**Usage:**
```bash
./scripts/setup.sh
```

## Using with Make

All scripts can be run via Makefile targets:
```bash
make test-full    # Run run_test.sh
make setup        # Run setup.sh
```
