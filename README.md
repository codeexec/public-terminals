# Sandbox Server

A cloud-based sandbox provisioning system that provides on-demand environment access via web browsers.

## Demo

https://terminal.newsml.io

## Quick Start

### 1. Prerequisites
- Docker and Docker Compose
- `sudo` privileges for Docker commands (or Docker Desktop)

### 2. Start All Services
Use the unified start script that handles everything from first-time setup to rebuilds:

```bash
# First time setup (checks prerequisites, builds images, starts services)
./scripts/start_services.sh

# Restart existing containers (after code changes to mounted volumes)
./scripts/start_services.sh --restart

# Rebuild images and recreate containers (after dependency changes)
./scripts/start_services.sh --rebuild

# Show help and all options
./scripts/start_services.sh --help
```

The script automatically:
- Checks Docker and Docker Compose are installed and running
- Creates `.env` from `.env.example` if needed
- Generates JWT secret key for admin authentication
- Builds all required Docker images
- Starts all services and waits for them to be healthy

Alternatively, you can use the Makefile:

```bash
# Initialize and start all services
make init && make up

# Build the base sandbox image
make build-base
```

Once started, access the application at:
- **Web UI:** http://localhost:8001
- **Admin UI:** http://localhost:8001/admin (username: `admin`, password: see `.env`)
- **API Docs:** http://localhost:8000/docs

### 3. Verification
Run the full integration test to verify the entire flow:
```bash
./scripts/run_integration_tests.sh
```

---

## Environment Configuration

The system behaves differently based on whether it's running locally for development or in production at `terminal.newsml.io`.

| Component | Dev (Local) | Prod (`terminal.newsml.io`) | Config Variable |
| :--- | :--- | :--- | :--- |
| **API Server** | `http://localhost:8000` | `https://terminal.newsml.io/api` | `API_BASE_URL` |
| **Web UI** | `http://localhost:8001` | `https://terminal.newsml.io` | `WEB_BASE_URL` |
| **Tunnel Host** | `https://localtunnel.me` | `https://localtunnel.newsml.io` | `LOCALTUNNEL_HOST` |
| **DB Access** | `localhost:5432` | Internal Only | `DATABASE_URL` |

## Features
- **Instant Provisioning:** Isolated sandboxes created on-demand.
- **Web Access:** Access sandboxes via a browser through secure tunnel URLs.
- **Admin Dashboard:** JWT-authenticated admin UI to view and manage all sandboxes across all users.
- **Automatic Cleanup:** 24-hour TTL with Celery-based background cleanup.
- **Resource Monitoring:** Real-time CPU and Memory usage tracking.

## Architecture
- **Web Server (8001):** Vanilla JS frontend.
- **API Server (8000):** FastAPI backend managing container lifecycles.
- **Database:** PostgreSQL for sandbox metadata.
- **Worker:** Celery + Redis for background tasks and cleanup.
- **Sandboxes:** Ephemeral Docker containers running tools + localtunnel.

## Manual Cleanup
If you need to force-kill all active sandbox containers:
```bash
sudo docker ps -a --filter "name=sandbox-" -q | xargs -r sudo docker rm -f
```

## API Usage
**Create Sandbox:**
```bash
curl -X POST http://localhost:8000/api/v1/sandboxes -d '{}'
```

**List Sandboxes:**
```bash
curl http://localhost:8000/api/v1/sandboxes
```

## Admin Dashboard

The admin UI provides a centralized interface to manage all sandboxes across all users.

### Access
- **URL:** http://localhost:8001/admin
- **Default Credentials:**
  - Username: `admin`
  - Password: Set in `.env` file (`ADMIN_PASSWORD`)

### Admin API Endpoints
**Login:**
```bash
curl -X POST http://localhost:8000/api/v1/admin/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}'
```

**List All Sandboxes (requires JWT token):**
```bash
curl http://localhost:8000/api/v1/admin/sandboxes \
  -H "Authorization: Bearer <YOUR_JWT_TOKEN>"
```

**Terminate Sandbox (requires JWT token):**
```bash
curl -X DELETE http://localhost:8000/api/v1/admin/sandboxes/<SANDBOX_ID> \
  -H "Authorization: Bearer <YOUR_JWT_TOKEN>"
```

## Development

### Common Commands
```bash
# Start services
./scripts/start_services.sh

# Restart after code changes
./scripts/start_services.sh --restart

# Rebuild after dependency changes
./scripts/start_services.sh --rebuild

# Run tests
make test-api                # Unit tests
./scripts/run_integration_tests.sh        # Full integration test
```
