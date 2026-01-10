# Terminal Server

A cloud-based terminal provisioning system that provides on-demand terminal access via web browsers using Terminado and localtunnel.

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

# Build the terminal image (required for terminal creation)
make build-terminal
```

Once started, access the application at:
- **Web UI:** http://localhost:8001
- **Admin UI:** http://localhost:8001/admin (username: `admin`, password: see `.env`)
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
- **Admin Dashboard:** JWT-authenticated admin UI to view and manage all terminals across all users.
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

## Admin Dashboard

The admin UI provides a centralized interface to manage all terminals across all users.

### Access
- **URL:** http://localhost:8001/admin
- **Default Credentials:**
  - Username: `admin`
  - Password: Set in `.env` file (`ADMIN_PASSWORD`)

### Features
- View all active terminals regardless of user/guest ID
- Real-time stats: Total, Active, Starting, Failed terminals
- Terminate any terminal with one click
- Auto-refresh every 10 seconds
- JWT-based authentication with 60-minute session timeout

### Admin API Endpoints
**Login:**
```bash
curl -X POST http://localhost:8000/api/v1/admin/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}'
```

**List All Terminals (requires JWT token):**
```bash
curl http://localhost:8000/api/v1/admin/terminals \
  -H "Authorization: Bearer <YOUR_JWT_TOKEN>"
```

**Terminate Terminal (requires JWT token):**
```bash
curl -X DELETE http://localhost:8000/api/v1/admin/terminals/<TERMINAL_ID> \
  -H "Authorization: Bearer <YOUR_JWT_TOKEN>"
```

### Configuration
Admin settings are configured via environment variables in `.env`:

```bash
# Admin Authentication
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password_here
JWT_SECRET_KEY=generate_with_openssl_rand_hex_32
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
```

**Security Notes:**
- Change the default admin password in production
- Generate a secure JWT secret key: `openssl rand -hex 32`
- The setup script will automatically generate these if missing

## Development

### Common Commands
```bash
# Start services
./scripts/start_services.sh

# Restart after code changes (hot reload for mounted volumes)
./scripts/start_services.sh --restart

# Rebuild after dependency changes (requirements.txt, Dockerfile)
./scripts/start_services.sh --rebuild

# View logs
make logs              # All services
make logs-api          # API server only
docker compose logs -f # Follow logs

# Stop services
make down
docker compose down

# Run tests
make test-api                # Unit tests
./scripts/run_test.sh        # Full integration test
```
