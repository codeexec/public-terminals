# Terminal Server

A cloud-based terminal provisioning system that provides on-demand terminal access via web browsers using Terminado and localtunnel.

## Features

- **Web UI** - User-friendly web interface for terminal management
- **REST API** - Full-featured API for terminal lifecycle management
- **On-demand terminal creation** - Create isolated terminal instances instantly
- **Web-based access** - Access terminals through browser via tunnel URLs
- **24-hour TTL** - Automatic cleanup after expiration
- **Multi-platform support** - Docker or Kubernetes (GKE)
- **Status tracking** - Real-time status updates via callbacks
- **Health monitoring** - Container health checks and error reporting
- **Pre-installed tools** - Includes tmux, git, vim, nano, and development tools

## Architecture

The system consists of six main components:

1. **Web Server** (Port 8001) - Serves the web UI for terminal management
2. **API Server** (Port 8000) - FastAPI-based REST API for terminal operations
3. **Database** - PostgreSQL for storing terminal metadata
4. **Terminal Containers** - Docker/Kubernetes containers running Terminado + localtunnel
5. **Cleanup Service** - Celery-based background tasks for TTL enforcement
6. **Message Queue** - Redis for Celery task management

### Separated Architecture

```
┌─────────────┐         ┌─────────────┐
│  Web UI     │         │  API Server │
│  :8001      │ ──────► │  :8000      │
└─────────────┘  CORS   └─────────────┘
                              │
                              ├── PostgreSQL
                              ├── Redis
                              ├── Container Service
                              └── Celery Workers
```

## Project Structure

```
terminal-server/
├── src/
│   ├── api_server.py                # API Server entry point (port 8000)
│   ├── web_server.py                # Web Server entry point (port 8001)
│   ├── config.py                    # Configuration management
│   ├── celery_app.py                # Celery configuration
│   ├── database/
│   │   ├── models.py                # SQLAlchemy models
│   │   └── session.py               # Database session management
│   ├── api/
│   │   ├── schemas.py               # Pydantic schemas
│   │   └── routes/
│   │       ├── terminals.py         # Terminal CRUD endpoints
│   │       └── callbacks.py         # Container callback endpoints
│   ├── services/
│   │   ├── container_service.py     # Docker/K8s management
│   │   ├── cleanup_service.py       # TTL cleanup service
│   │   └── docker_cli_service.py    # Docker CLI wrapper
│   └── static/
│       └── index.html               # Web UI
├── terminal-container/
│   ├── Dockerfile                   # Terminal container image
│   ├── terminado_server.py          # Tornado-based terminal server
│   ├── index.html                   # Terminal web interface
│   ├── entrypoint.sh                # Container startup script
│   ├── motd.sh                      # Message of the day
│   └── requirements.txt             # Terminal dependencies
├── scripts/
│   ├── run_test.sh                  # Full integration test
│   └── setup.sh                     # Project setup script
├── tests/
│   ├── test_api.py                  # API integration tests
│   └── __init__.py                  # Test package marker
├── deprecated/
│   └── main.py                      # Legacy monolithic app (archived)
├── docker-compose.yml               # Local development setup
├── Dockerfile                       # API/Web server image
├── Makefile                         # Common commands
├── pytest.ini                       # Pytest configuration
└── requirements.txt                 # Python dependencies
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- curl and jq (for testing)

### Option 1: Using Makefile (Recommended)

```bash
# Initialize project (first time only)
make init

# Start all services
make up

# Access the application
# - Web UI: http://localhost:8001
# - API: http://localhost:8000
# - API Docs: http://localhost:8000/docs

# View logs
make logs          # All services
make logs-api      # API server only
make logs-web      # Web server only

# Run tests
make test          # Quick API test
make test-full     # Full integration test
make test-api      # Python API tests

# Stop services
make down
```

### Option 2: Automated Full Test

Run the unified test script that will:
1. Start all services (API, Web, DB, Redis, Celery)
2. Build the terminal container image
3. Create a test terminal
4. Verify health endpoints
5. Display access URLs
6. Optionally cleanup

```bash
./scripts/run_test.sh
```

To stop and clean up all services:
```bash
./scripts/run_test.sh --stop
```

### Option 3: Manual Setup

#### 1. Setup Environment

```bash
cp .env.example .env
```

#### 2. Build Terminal Container Image

```bash
cd terminal-container
docker build -t terminal-server:latest .
cd ..
```

#### 3. Start Services

```bash
docker compose up -d
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- API Server (port 8000)
- Web Server (port 8001)
- Celery Worker
- Celery Beat (scheduler)

#### 4. Access the Application

**Web UI:**
```
http://localhost:8001
```

**API Documentation:**
```
http://localhost:8000/docs
```

#### 5. Stop Services

```bash
docker compose down
```

## Web UI Usage

1. **Open Web UI** at `http://localhost:8001`
2. **Create Terminal** - Click "New Terminal" button
3. **Wait for Terminal** - Status will change from "pending" → "starting" → "started"
4. **Open Terminal** - Click "Open Terminal" button when ready
5. **Use Terminal** - Full bash terminal with tmux, git, vim, nano, and more
6. **Delete Terminal** - Click "Delete" button when done

## API Usage

### Create a Terminal

```bash
POST /api/v1/terminals
```

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/terminals \
  -H "Content-Type: application/json" \
  -H "X-Guest-ID: user-123" \
  -d '{}'
```

**Response (202 Accepted):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "tunnel_url": null,
  "container_id": null,
  "created_at": "2026-01-08T10:00:00Z",
  "expires_at": "2026-01-09T10:00:00Z"
}
```

### Get Terminal Details

```bash
GET /api/v1/terminals/{terminal_id}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "started",
  "tunnel_url": "https://abc123.loca.lt",
  "container_id": "terminal-550e8400",
  "container_name": "terminal-550e8400",
  "host_port": "32768",
  "created_at": "2026-01-08T10:00:00Z",
  "expires_at": "2026-01-09T10:00:00Z"
}
```

### List All Terminals

```bash
GET /api/v1/terminals
```

Optional query parameters:
- `skip` - Pagination offset (default: 0)
- `limit` - Number of results (default: 100)

Optional headers:
- `X-Guest-ID` - Filter by guest/user ID

### Delete a Terminal

```bash
DELETE /api/v1/terminals/{terminal_id}
```

**Response:**
```json
{
  "status": "success",
  "terminal_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Terminal deleted successfully"
}
```

### Health Check

```bash
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

## Terminal Lifecycle

1. **User requests terminal** → API creates database record (status: `pending`)
2. **Background task starts** → Container creation begins (status: `starting`)
3. **Container starts** → Terminado + localtunnel launch
4. **Tunnel established** → Container calls back with URL (status: `started`)
5. **User accesses terminal** → Opens tunnel URL in browser
6. **24 hours later** → Cleanup service expires terminal
7. **Container deleted** → Resources cleaned up (status: `stopped`)

## Container Callback Flow

The terminal container reports back to the API server:

### 1. Report Tunnel URL

```bash
POST /api/v1/callbacks/tunnel
```

**Request:**
```json
{
  "terminal_id": "550e8400-e29b-41d4-a716-446655440000",
  "tunnel_url": "https://abc123.loca.lt"
}
```

### 2. Report Status/Errors

```bash
POST /api/v1/callbacks/status
```

**Request:**
```json
{
  "terminal_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "error_message": "Failed to start localtunnel"
}
```

### 3. Health Ping

```bash
POST /api/v1/callbacks/health
```

**Request:**
```json
{
  "terminal_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Configuration

### Environment Variables

See `.env.example` for all available configuration options.

**Key settings:**

**API Server:**
- `API_HOST` - API server host (default: 0.0.0.0)
- `API_PORT` - API server port (default: 8000)
- `API_BASE_URL` - API server URL (default: http://localhost:8000)

**Web Server:**
- `WEB_HOST` - Web server host (default: 0.0.0.0)
- `WEB_PORT` - Web server port (default: 8001)
- `WEB_BASE_URL` - Web server URL (default: http://localhost:8001)

**Container Platform:**
- `CONTAINER_PLATFORM` - `docker` or `kubernetes`
- `TERMINAL_IMAGE` - Terminal container image (default: terminal-server:latest)
- `TERMINAL_TTL_HOURS` - Terminal lifetime (default: 24)

**Cleanup:**
- `CLEANUP_INTERVAL_MINUTES` - How often to run cleanup (default: 5)

**Localtunnel:**
- `LOCALTUNNEL_HOST` - Localtunnel server URL (default: https://localtunnel.newsml.io)

**Database:**
- `DATABASE_URL` - PostgreSQL connection string

**Redis:**
- `REDIS_URL` - Redis connection string for Celery

### Docker vs Kubernetes

**For Docker (local development):**
```bash
CONTAINER_PLATFORM=docker
DOCKER_HOST=unix://var/run/docker.sock
```

**For Kubernetes (GKE production):**
```bash
CONTAINER_PLATFORM=kubernetes
K8S_NAMESPACE=default
K8S_IN_CLUSTER=true
```

## Pre-installed Tools in Terminals

Each terminal container comes with:

**Shell & Multiplexing:**
- bash
- tmux (terminal multiplexer)

**Editors:**
- vim
- nano

**Version Control:**
- git

**Network Tools:**
- curl
- dnsutils (dig, nslookup)
- iputils-ping
- net-tools (netstat, ifconfig)
- netcat

**System Tools:**
- procps (ps, top)
- htop

**Development:**
- Python 3.12
- Node.js & npm
- Claude CLI
- Gemini CLI
- localtunnel

## Makefile Commands

```bash
make help              # Show all available commands

# Build & Deploy
make build-terminal    # Build terminal container image
make build-api         # Build API server image
make build             # Build all images
make up                # Start all services
make down              # Stop all services
make init              # Initialize project (first time setup)
make setup             # Run setup script

# Logs & Monitoring
make logs              # View all logs
make logs-api          # View API server logs
make logs-web          # View Web server logs
make logs-celery       # View Celery worker logs

# Testing
make test              # Quick API test (create terminal)
make test-full         # Full integration test (bash script)
make test-api          # Run Python API tests

# Utilities
make shell             # Open shell in API container
make db-shell          # Open PostgreSQL shell
make clean             # Remove all containers and volumes
```

## Development

### Run API Server Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL and Redis
docker compose up -d postgres redis

# Run API server
python -m src.api_server
```

### Run Web Server Locally

```bash
# Run web server
python -m src.web_server
```

### Run Celery Worker Locally

```bash
celery -A src.celery_app worker --loglevel=info
```

### Run Celery Beat Locally

```bash
celery -A src.celery_app beat --loglevel=info
```

## Testing

### Quick API Test

```bash
make test
```

### Full Integration Test

```bash
make test-full
# or
./scripts/run_test.sh
```

### Python API Tests

```bash
make test-api
# or
python3 tests/test_api.py
# or
pytest tests/
```

### Manual API Testing

```bash
# Create terminal
TERMINAL_ID=$(curl -X POST http://localhost:8000/api/v1/terminals \
  -H "Content-Type: application/json" \
  -H "X-Guest-ID: test-user" \
  -d '{}' | jq -r '.id')

# Poll status
curl http://localhost:8000/api/v1/terminals/$TERMINAL_ID | jq

# Wait for tunnel URL
while true; do
  STATUS=$(curl -s http://localhost:8000/api/v1/terminals/$TERMINAL_ID | jq -r '.status')
  if [ "$STATUS" = "started" ]; then
    TUNNEL_URL=$(curl -s http://localhost:8000/api/v1/terminals/$TERMINAL_ID | jq -r '.tunnel_url')
    echo "Terminal ready: $TUNNEL_URL"
    break
  fi
  echo "Status: $STATUS"
  sleep 2
done

# Delete terminal
curl -X DELETE http://localhost:8000/api/v1/terminals/$TERMINAL_ID
```

## Database Schema

### `terminals` table

| Column | Type | Description |
|--------|------|-------------|
| id | VARCHAR(36) | Primary key (UUID) |
| user_id | VARCHAR(255) | User/Guest identifier |
| status | ENUM | Terminal status |
| tunnel_url | VARCHAR(512) | Public tunnel URL |
| container_id | VARCHAR(255) | Container/pod identifier |
| container_name | VARCHAR(255) | Container name |
| host_port | VARCHAR(10) | Host port mapping |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |
| expires_at | TIMESTAMP | Expiration time (created_at + TTL) |
| deleted_at | TIMESTAMP | Deletion time (soft delete) |
| error_message | VARCHAR(1024) | Error details if failed |

**Status values:** `pending`, `starting`, `started`, `stopped`, `expired`, `failed`

## Deployment to GCP

### Option 1: GKE (Recommended)

1. **Create GKE cluster:**
```bash
gcloud container clusters create terminal-server \
  --region us-central1 \
  --num-nodes 3 \
  --machine-type n1-standard-2
```

2. **Build and push images:**
```bash
# Build and push API/Web server image
docker build -t gcr.io/[PROJECT-ID]/terminal-app:latest .
docker push gcr.io/[PROJECT-ID]/terminal-app:latest

# Build and push terminal container image
cd terminal-container
docker build -t gcr.io/[PROJECT-ID]/terminal-server:latest .
docker push gcr.io/[PROJECT-ID]/terminal-server:latest
```

3. **Deploy to GKE:**
```bash
kubectl apply -f k8s/
```

### Option 2: Cloud Run + GCE

1. Deploy API and Web servers to Cloud Run
2. Use GCE VMs with Docker for terminal containers
3. Configure VPC networking

## Monitoring and Logs

### View API Server Logs
```bash
docker compose logs -f api-server
```

### View Web Server Logs
```bash
docker compose logs -f web-server
```

### View Celery Worker Logs
```bash
docker compose logs -f celery-worker
```

### View Terminal Container Logs
```bash
docker logs terminal-{terminal_id}
```

### Access PostgreSQL
```bash
make db-shell
# or
docker compose exec postgres psql -U postgres -d terminal_server
```

## Security Considerations

1. **Network isolation** - Terminals run in isolated containers
2. **TTL enforcement** - Automatic cleanup prevents resource exhaustion
3. **No persistent storage** - Terminals are ephemeral
4. **CORS configuration** - Configure allowed origins in production
5. **Guest ID tracking** - Basic user tracking via X-Guest-ID header
6. **API authentication** - Add JWT/OAuth before production deployment
7. **Tunnel security** - Consider self-hosted localtunnel server
8. **Resource limits** - Set container CPU/memory limits

## Troubleshooting

### Terminal stuck in "pending" or "starting"

- Check API server logs: `make logs-api`
- Check container logs: `docker logs terminal-{id}`
- Verify Docker socket access: `ls -la /var/run/docker.sock`
- Check container service: `docker ps -a | grep terminal`

### Tunnel URL not appearing

- Check entrypoint.sh execution: `docker logs terminal-{id}`
- Verify localtunnel connectivity: `curl https://localtunnel.newsml.io`
- Check callback endpoint: `curl http://localhost:8000/api/v1/callbacks/tunnel`
- Verify API server is accessible from containers

### Web UI not loading

- Check web server logs: `make logs-web`
- Verify web server is running: `curl http://localhost:8001/health`
- Check browser console for CORS errors
- Verify API_BASE in index.html points to correct API server

### Cleanup not running

- Check Celery beat is running: `docker compose ps celery-beat`
- Check Celery worker logs: `make logs-celery`
- Verify Redis connectivity: `docker compose exec redis redis-cli ping`

### Terminal resolution issues

- The terminal uses xterm.js FitAddon for automatic sizing
- Resize browser window to trigger re-fit
- Check browser console for errors

## Recent Updates

### Version 2.0 - Architecture Separation
- ✅ Separated Web UI and API into independent servers
- ✅ Added comprehensive Web UI for terminal management
- ✅ Improved terminal sizing with xterm.js FitAddon
- ✅ Added tmux pre-installed in terminals
- ✅ Organized project with scripts/ and tests/ folders
- ✅ Enhanced Makefile with new commands
- ✅ Fixed double scroll bar issue in terminal UI

## Future Enhancements

- [ ] User authentication and multi-tenancy
- [ ] Terminal session recording
- [ ] Custom terminal environments (different base images)
- [ ] Horizontal autoscaling based on demand
- [ ] Metrics and monitoring (Prometheus/Grafana)
- [ ] WebSocket status updates instead of polling
- [ ] Self-hosted localtunnel server deployment
- [ ] Terminal sharing/collaboration features
- [ ] File upload/download in terminals

## License

MIT

## Support

For issues and questions, please open an issue on GitHub.
