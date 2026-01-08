# Terminal Server

A cloud-based terminal provisioning system that provides on-demand terminal access via web browsers using Terminado and localtunnel.

## Quick Start

### 1. Prerequisites
- Docker and Docker Compose
- Python 3.11+
- `sudo` privileges for Docker commands

### 2. Start All Services
The easiest way to start everything is using the provided start script:

```bash
./scripts/start_services.sh
```

Alternatively, you can use the Makefile:

```bash
# Initialize and start all services
make init && make up

# Build the terminal image (required for terminal creation)
make build-terminal
```

Once started, access the application at:
- **Web UI:** http://localhost:8001
- **API Docs:** http://localhost:8000/docs

### 3. Verification
Run the full integration test to verify the entire flow:
```bash
./scripts/run_test.sh
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
- **Instant Provisioning:** Isolated bash terminals created on-demand.
- **Web Access:** Access terminals via a browser through secure tunnel URLs.
- **Automatic Cleanup:** 24-hour TTL with Celery-based background cleanup.
- **Full Toolset:** Terminals include `tmux`, `git`, `vim`, `python`, `node`, `claude-cli`, and `gemini-cli`.

## Architecture
- **Web Server (8001):** React-like vanilla JS frontend.
- **API Server (8000):** FastAPI backend managing container lifecycles.
- **Database:** PostgreSQL for terminal metadata.
- **Worker:** Celery + Redis for background tasks and cleanup.
- **Terminals:** Ephemeral Docker containers running Terminado + localtunnel.

## Recent Changes & Troubleshooting

### Fixed: Terminals stuck in "starting"
The terminal startup script (`entrypoint.sh`) was previously blocking on the `localtunnel` process. 

**Improvements made:**
- **Backgrounded Localtunnel:** The tunnel process now runs in the background, allowing the script to report the tunnel URL back to the API.
- **Enhanced Logging:** All container startup logs are now redirected to `stderr` to avoid shell pipe blocking.
- **Retry Logic:** Improved polling for the tunnel URL within the container.

### Manual Cleanup
If you need to force-kill all active terminal containers:
```bash
sudo docker ps -a --filter "name=terminal-" -q | xargs -r sudo docker rm -f
```

## API Usage
**Create Terminal:**
```bash
curl -X POST http://localhost:8000/api/v1/terminals -d '{}'
```

**List Terminals:**
```bash
curl http://localhost:8000/api/v1/terminals
```

## Development
- **Logs:** `make logs` (all) or `make logs-api`
- **Tests:** `make test-api` (unit) or `./scripts/run_test.sh` (integration)
- **Stop:** `make down`