# Deployment Guide - terminal.newsml.io

This guide provides step-by-step instructions for deploying the Sandbox Server to production at `terminal.newsml.io` with SSL/TLS encryption.

## Architecture Overview

```
Internet
    │
    ▼
[Docker: Nginx] :80/:443 (SSL Termination)
    │
    ├─► [Docker: Web Server] :8001 (terminal.newsml.io/)
    └─► [Docker: API Server] :8000 (terminal.newsml.io/api)
         │
         ├─► [Docker: PostgreSQL] :5432
         ├─► [Docker: Redis] :6379
         └─► [Sandbox Containers]
```

## Prerequisites

- Ubuntu/Debian server with root access
- Domain: `newsml.io` with DNS control
- Docker and Docker Compose installed
- Ports 80 and 443 open on VM firewall
- Minimum 2GB RAM, 2 CPU cores

## Step 1: DNS Configuration

Create an A record for the subdomain pointing to your server's public IP.

```
Type: A
Name: sandbox
Value: <YOUR_SERVER_PUBLIC_IP>
TTL: 300 (5 minutes) or Auto
```

## Step 2: Server Preparation

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y git curl make
```

## Step 3: Clone and Setup Application

```bash
cd /opt
sudo git clone https://github.com/codeexec/public-terminals.git sandbox-server
cd sandbox-server
sudo chown -R $USER:$USER /opt/sandbox-server
cp .env.example .env
```

### Edit `.env` for production

```bash
# API Server
API_BASE_URL=https://terminal.newsml.io
WEB_BASE_URL=https://terminal.newsml.io

# Database
DATABASE_URL=postgresql://sandboxuser:CHANGE_THIS_PASSWORD@postgres:5432/sandbox_server

# Container Configuration
SANDBOX_BASE_IMAGE=terminal-server:latest
SANDBOX_TTL_HOURS=24
```

## Step 4: Build Images

```bash
make build-base
docker build -t sandbox-api:latest .
```

## Step 5: SSL Certificate with Let's Encrypt

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d terminal.newsml.io
mkdir -p nginx/certs
sudo cp -rL /etc/letsencrypt/live nginx/certs/
```

## Step 6: Verify Nginx Configuration

Ensure `nginx/nginx.conf` matches your domain.

## Step 7: Start Application

```bash
make up
```

## Step 8: Verify Deployment

Check `https://terminal.newsml.io/health`

## Maintenance

### Backup Database

```bash
docker-compose exec postgres pg_dump -U postgres sandbox_server > backup.sql
```

### Systemd Service

Create `/etc/systemd/system/sandbox-server.service`:

```ini
[Unit]
Description=Sandbox Server
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/sandbox-server
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
User=root

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable sandbox-server
sudo systemctl start sandbox-server
```
