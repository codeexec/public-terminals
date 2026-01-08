# Terminal Server

A cloud-based terminal provisioning system that provides on-demand terminal access via web browsers using Terminado and localtunnel.

## Architecture

The system consists of four main components:

1. **API Server** - FastAPI-based REST API for terminal management
2. **Database** - PostgreSQL for storing terminal metadata
3. **Terminal Container** - Docker/Kubernetes containers running Terminado + localtunnel
4. **Cleanup Service** - Celery-based background tasks for TTL enforcement

## Features

- **On-demand terminal creation** - Create isolated terminal instances via API
- **Web-based access** - Access terminals through browser via tunnel URLs
- **24-hour TTL** - Automatic cleanup after expiration
- **Multi-platform support** - Docker or Kubernetes (GKE)
- **Status tracking** - Real-time status updates via callbacks
- **Health monitoring** - Container health checks and error reporting

## Project Structure

```
terminal-server/
├── src/
│   ├── main.py                      # FastAPI application
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
│   └── services/
│       ├── container_service.py     # Docker/K8s management
│       └── cleanup_service.py       # TTL cleanup service
├── terminal-container/
│   ├── Dockerfile                   # Terminal container image
│   ├── entrypoint.sh                # Container startup script
│   └── requirements.txt             # Terminal dependencies
├── docker compose.yml               # Local development setup
├── Dockerfile.api                   # API server image
└── requirements.txt                 # API server dependencies
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- curl and jq (for testing)

### Option 1: Automated Full Test (Recommended)

Run the unified test script that will:
1. Start all services (API, DB, Redis, Celery)
2. Build the terminal container image
3. Create a test terminal
4. Verify health endpoints
5. Display tunnel URL for browser access
6. Optionally stop and cleanup

```bash
./run_test.sh
```

This script handles everything automatically and provides a complete end-to-end test.

To stop and clean up all services and terminal containers:
```bash
./run_test.sh --stop
```

### Option 2: Manual Setup

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
./start.sh
```

Or manually:
```bash
docker compose up -d
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- API Server (port 8000)
- Celery Worker
- Celery Beat (scheduler)

#### 4. Verify Services

```bash
# Check API health
curl http://localhost:8000/health

# View API docs
open http://localhost:8000/docs
```

#### 5. Stop Services

```bash
./stop.sh
```

Or manually:
```bash
docker compose down
```

## API Usage

### Create a Terminal

```bash
POST /api/v1/terminals
```

**Response (202 Accepted):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "tunnel_url": null,
  "created_at": "2026-01-07T10:00:00Z",
  "expires_at": "2026-01-08T10:00:00Z"
}
```

### Poll Terminal Status

```bash
GET /api/v1/terminals/{terminal_id}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "started",
  "tunnel_url": "https://abc123.loca.lt",
  "container_id": "container-550e8400",
  "created_at": "2026-01-07T10:00:00Z",
  "expires_at": "2026-01-08T10:00:00Z"
}
```

### List All Terminals

```bash
GET /api/v1/terminals
```

### Delete a Terminal

```bash
DELETE /api/v1/terminals/{terminal_id}
```

## Terminal Lifecycle

1. **User requests terminal** → API creates database record (status: `pending`)
2. **Background task starts** → Container creation begins (status: `starting`)
3. **Container starts** → Terminado + localtunnel launch
4. **Tunnel established** → Container calls back with URL (status: `started`)
5. **User accesses terminal** → Opens tunnel URL in browser
6. **24 hours later** → Cleanup service expires terminal
7. **Container deleted** → Resources cleaned up (status: `expired`)

## Container Callback Flow

The terminal container reports back to the API server:

### 1. Report Tunnel URL

```bash
POST /api/v1/callbacks/tunnel
{
  "terminal_id": "550e8400-e29b-41d4-a716-446655440000",
  "tunnel_url": "https://abc123.loca.lt"
}
```

### 2. Report Status/Errors

```bash
POST /api/v1/callbacks/status
{
  "terminal_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "error_message": "Failed to start localtunnel"
}
```

## Configuration

### Environment Variables

See `.env.example` for all available configuration options.

**Key settings:**

- `CONTAINER_PLATFORM` - `docker` or `kubernetes`
- `TERMINAL_TTL_HOURS` - Terminal lifetime (default: 24)
- `CLEANUP_INTERVAL_MINUTES` - How often to run cleanup (default: 5)
- `LOCALTUNNEL_HOST` - Localtunnel server URL

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
# Build API image
docker build -f Dockerfile.api -t gcr.io/[PROJECT-ID]/terminal-api:latest .
docker push gcr.io/[PROJECT-ID]/terminal-api:latest

# Build terminal container image
cd terminal-container
docker build -t gcr.io/[PROJECT-ID]/terminal-server:latest .
docker push gcr.io/[PROJECT-ID]/terminal-server:latest
```

3. **Deploy to GKE:**
```bash
kubectl apply -f k8s/
```

### Option 2: Cloud Run + GCE

1. Deploy API to Cloud Run
2. Use GCE VMs with Docker for terminal containers
3. Configure VPC networking

## Database Schema

### `terminals` table

| Column | Type | Description |
|--------|------|-------------|
| id | VARCHAR(36) | Primary key (UUID) |
| status | ENUM | Terminal status |
| tunnel_url | VARCHAR(512) | Public tunnel URL |
| container_id | VARCHAR(255) | Container/pod identifier |
| container_name | VARCHAR(255) | Container name |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |
| expires_at | TIMESTAMP | Expiration time (created_at + TTL) |
| deleted_at | TIMESTAMP | Deletion time |
| error_message | VARCHAR(1024) | Error details if failed |

**Status values:** `pending`, `starting`, `started`, `stopped`, `expired`, `failed`

## Monitoring and Logs

### View API logs
```bash
docker compose logs -f api
```

### View Celery worker logs
```bash
docker compose logs -f celery-worker
```

### View terminal container logs
```bash
docker logs terminal-{terminal_id}
```

## Development

### Run API server locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL and Redis
docker compose up -d postgres redis

# Run API server
cd src
python -m uvicorn main:app --reload --port 8000
```

### Run Celery worker locally

```bash
celery -A src.celery_app worker --loglevel=info
```

### Run Celery beat locally

```bash
celery -A src.celery_app beat --loglevel=info
```

## Testing

### Manual API Testing

```bash
# Create terminal
TERMINAL_ID=$(curl -X POST http://localhost:8000/api/v1/terminals | jq -r '.id')

# Poll status
curl http://localhost:8000/api/v1/terminals/$TERMINAL_ID

# Wait for tunnel URL
while true; do
  STATUS=$(curl -s http://localhost:8000/api/v1/terminals/$TERMINAL_ID | jq -r '.status')
  if [ "$STATUS" = "started" ]; then
    TUNNEL_URL=$(curl -s http://localhost:8000/api/v1/terminals/$TERMINAL_ID | jq -r '.tunnel_url')
    echo "Terminal ready: $TUNNEL_URL"
    break
  fi
  sleep 2
done

# Delete terminal
curl -X DELETE http://localhost:8000/api/v1/terminals/$TERMINAL_ID
```

## Security Considerations

1. **Network isolation** - Terminals run in isolated containers
2. **TTL enforcement** - Automatic cleanup prevents resource exhaustion
3. **No persistent storage** - Terminals are ephemeral
4. **CORS configuration** - Restrict allowed origins in production
5. **API authentication** - Add JWT/OAuth before production deployment
6. **Tunnel security** - Consider self-hosted localtunnel server

## Troubleshooting

### Terminal stuck in "pending" or "starting"

- Check API server logs: `docker compose logs api`
- Check container logs: `docker logs terminal-{id}`
- Verify Docker socket access: `ls -la /var/run/docker.sock`

### Tunnel URL not appearing

- Check entrypoint.sh execution: `docker logs terminal-{id}`
- Verify localtunnel connectivity
- Check callback endpoint: `curl http://localhost:8000/api/v1/callbacks/tunnel`

### Cleanup not running

- Check Celery beat is running: `docker compose ps celery-beat`
- Check Celery worker logs: `docker compose logs celery-worker`
- Verify Redis connectivity

## Future Enhancements

- [ ] Web UI for terminal management
- [ ] User authentication and multi-tenancy
- [ ] Terminal session recording
- [ ] Custom terminal environments (different base images)
- [ ] Horizontal autoscaling based on demand
- [ ] Metrics and monitoring (Prometheus/Grafana)
- [ ] WebSocket status updates instead of polling
- [ ] Self-hosted localtunnel server deployment

## License

MIT

## Support

For issues and questions, please open an issue on GitHub.
