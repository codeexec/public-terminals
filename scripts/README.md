# Scripts Directory

This directory contains shell scripts for managing, testing, and developing the Terminal Server.

## Main Scripts

### `start_services.sh` ⭐ **Primary Script**
Unified script for all service management tasks.

**Usage:**
```bash
# First time setup (checks prerequisites, builds images, starts services)
./scripts/start_services.sh

# Quick restart after code changes
./scripts/start_services.sh --restart

# Full rebuild after dependency changes
./scripts/start_services.sh --rebuild

# Show all options
./scripts/start_services.sh --help
```

**Features:**
- Automatic prerequisite checking (Docker, Docker Compose)
- Environment file creation and JWT secret generation
- Image building and service orchestration
- Health check verification
- Clean, color-coded output

---

### `run_test.sh`
Full integration test script for end-to-end verification.

**Usage:**
```bash
./scripts/run_test.sh          # Run full integration test
./scripts/run_test.sh --stop   # Stop services only
```

**What it tests:**
- Starts all services (API, Web, DB, Redis, Celery)
- Creates a test terminal
- Waits for terminal to reach "started" state
- Verifies all health endpoints
- Tests admin API (login and terminals list)
- Displays access URLs
- Prompts for cleanup

---

## Development Scripts

### `check_python.sh`
Code quality checks using Ruff and MyPy.

**Prerequisites:**
```bash
pip install -r requirements-dev.txt
```

**Usage:**
```bash
./scripts/check_python.sh
```

**Checks:**
- Code formatting (ruff format)
- Linting (ruff check)
- Type checking (mypy)

---

## Using with Make

Scripts can be run via Makefile targets:
```bash
make test          # Run integration test (run_test.sh)
make logs          # View all service logs
make logs-api      # View API server logs only
make down          # Stop all services
```

## Quick Reference

| Task | Command |
|------|---------|
| First time setup | `./scripts/start_services.sh` |
| Restart after code changes | `./scripts/start_services.sh --restart` |
| Rebuild after deps change | `./scripts/start_services.sh --rebuild` |
| Run integration tests | `./scripts/run_test.sh` |
| Check code quality | `./scripts/check_python.sh` |
| View logs | `make logs` |
| Stop services | `make down` |
