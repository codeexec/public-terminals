# Deployment Guide - terminal.newsml.io

This guide provides step-by-step instructions for deploying the Terminal Server to production at `terminal.newsml.io` with SSL/TLS encryption.

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
         └─► [Terminal Containers]
```

## Prerequisites

- Ubuntu/Debian server with root access
- Domain: `newsml.io` with DNS control
- Docker and Docker Compose installed
- Ports 80 and 443 open on VM firewall
- Minimum 2GB RAM, 2 CPU cores
- At least 20GB disk space

## Step 1: DNS Configuration

Create an A record for the subdomain pointing to your server's public IP.

### Using your DNS provider (e.g., Cloudflare, Route53, etc.)

```
Type: A
Name: terminal
Value: <YOUR_SERVER_PUBLIC_IP>
TTL: 300 (5 minutes) or Auto
```

### Verify DNS propagation

```bash
# Check DNS resolution
dig terminal.newsml.io

# Or using nslookup
nslookup terminal.newsml.io

# Wait until the DNS propagates (can take 5-60 minutes)
```

## Step 2: Server Preparation

### Update system packages

```bash
sudo apt update
sudo apt upgrade -y
```

### Install required packages

```bash
sudo apt install -y \
    git \
    curl \
    make
```

## Step 3: Clone and Setup Application

### Clone repository

```bash
cd /opt
sudo git clone https://github.com/codeexec/public-terminals.git terminal-server
cd terminal-server
sudo chown -R $USER:$USER /opt/terminal-server
```

### Create production environment file

```bash
cp .env.example .env
```

### Edit `.env` for production

```bash
nano .env
```

**Update the following values:**

```bash
# API Server
API_HOST=0.0.0.0
API_PORT=8000
API_BASE_URL=https://terminal.newsml.io

# Web Server
WEB_HOST=0.0.0.0
WEB_PORT=8001
WEB_BASE_URL=https://terminal.newsml.io

# Database
DATABASE_URL=postgresql://terminaluser:CHANGE_THIS_PASSWORD@postgres:5432/terminal_server

# Redis
REDIS_URL=redis://redis:6379/0

# Container Platform
CONTAINER_PLATFORM=docker
TERMINAL_IMAGE=terminal-server:latest
TERMINAL_TTL_HOURS=24

# Localtunnel
LOCALTUNNEL_HOST=https://localtunnel.newsml.io

# Cleanup
CLEANUP_INTERVAL_MINUTES=5

# Logging
LOG_LEVEL=INFO
```

### Update frontend API URL

```bash
nano src/static/index.html
```

Change line 90 from:
```javascript
const API_BASE = 'http://localhost:8000/api/v1';
```

To:
```javascript
const API_BASE = 'https://terminal.newsml.io/api/v1';
```

Or use environment-based configuration:
```javascript
const API_BASE = (window.location.protocol + '//' + window.location.host) + '/api/v1';
```

## Step 4: Build Images

```bash
# Build terminal container image
cd terminal-container
docker build -t terminal-server:latest .
cd ..

# Build API/Web server image (if using separate Dockerfile)
docker build -t terminal-app:latest .
```

## Step 5: SSL Certificate with Let's Encrypt

### Obtain SSL certificate

You can use `certbot` on the host to obtain the certificates and then move/link them to the `./nginx/certs` directory.

```bash
# Install certbot if not present
sudo apt install -y certbot

# Obtain certificate
sudo certbot certonly --standalone \
  -d terminal.newsml.io \
  --email your-email@example.com \
  --agree-tos \
  --non-interactive

# Create the certs directory in the project
mkdir -p nginx/certs

# Copy the certificates (using -L to follow symlinks)
# This ensures the actual certificate files are available to the Docker container
sudo cp -rL /etc/letsencrypt/live nginx/certs/
sudo cp -rL /etc/letsencrypt/archive nginx/certs/
sudo cp -rL /etc/letsencrypt/renewal nginx/certs/
```

**Certificate files will be expected at:**
- `./nginx/certs/live/terminal.newsml.io/fullchain.pem`
- `./nginx/certs/live/terminal.newsml.io/privkey.pem`

### Set up automatic renewal

```bash
# Test renewal
sudo certbot renew --dry-run
```

## Step 6: Verify Nginx Configuration

The Nginx configuration is located at `nginx/nginx.conf`. It is already configured to proxy requests to the `web-server` and `api-server` containers.

### Edit Nginx configuration (if needed)

```bash
nano nginx/nginx.conf
```

Ensure the `server_name` matches your domain and the `proxy_pass` destinations match the service names in `docker-compose.yml`.

### Docker Volume Mapping

The configuration and certificates are mapped in `docker-compose.yml`:

```yaml
  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/certs:/etc/letsencrypt:ro
```

## Step 7: Start Application

### Start all services

```bash
cd /opt/terminal-server

# Build images
make build-terminal

# Start services
docker-compose up -d
```

### Verify services are running

```bash
# Check container status
docker-compose ps

# Check logs
docker-compose logs -f

# Test API locally
curl http://localhost:8000/health

# Test Web UI locally
curl http://localhost:8001/health
```

## Step 8: Verify Deployment

### Test SSL certificate

```bash
# Check SSL
curl -I https://terminal.newsml.io

# Test with SSL Labs (in browser)
# https://www.ssllabs.com/ssltest/analyze.html?d=terminal.newsml.io
```

### Test Web UI

Open in browser: `https://terminal.newsml.io`

### Test API

```bash
# Health check
curl https://terminal.newsml.io/health

# API docs
# Open in browser: https://terminal.newsml.io/docs

# Create test terminal
curl -X POST https://terminal.newsml.io/api/v1/terminals \
  -H "Content-Type: application/json" \
  -H "X-Guest-ID: test-user" \
  -d '{}'
```

## Step 9: Setup Monitoring and Logging

### View Nginx logs

```bash
# Access logs
sudo tail -f /var/log/nginx/terminal.newsml.io.access.log

# Error logs
sudo tail -f /var/log/nginx/terminal.newsml.io.error.log
```

### View application logs

```bash
# API server
docker-compose logs -f api-server

# Web server
docker-compose logs -f web-server

# All services
docker-compose logs -f
```

### Setup log rotation

```bash
sudo nano /etc/logrotate.d/terminal-server
```

Add:
```
/var/log/nginx/terminal.newsml.io.*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        [ -f /var/run/nginx.pid ] && kill -USR1 `cat /var/run/nginx.pid`
    endscript
}
```

## Step 10: Setup Automatic Startup

### Enable Docker on boot

```bash
sudo systemctl enable docker
```

### Create systemd service for terminal-server

```bash
sudo nano /etc/systemd/system/terminal-server.service
```

Add:
```ini
[Unit]
Description=Terminal Server
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/terminal-server
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
User=root

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable terminal-server
sudo systemctl start terminal-server
sudo systemctl status terminal-server
```

## Security Considerations

### 1. Database Security

- Change default PostgreSQL password in `.env`
- Restrict PostgreSQL to localhost only (already configured in docker-compose)
- Regular backups

### 2. Docker Security

```bash
# Don't expose Docker socket to the internet
# Only mount to API container, not others
```

### 3. Rate Limiting (Nginx)

Add to nginx configuration:
```nginx
# Rate limiting zone
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=terminal_create:10m rate=2r/m;

# Apply in locations
location /api/v1/terminals {
    limit_req zone=terminal_create burst=5 nodelay;
    # ... rest of proxy config
}
```

### 5. Regular Updates

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Docker images
cd /opt/terminal-server
git pull
make build-terminal
docker-compose down
docker-compose up -d
```

## Backup Strategy

### Database Backup

```bash
# Create backup directory
sudo mkdir -p /opt/backups/terminal-server

# Manual backup
docker-compose exec postgres pg_dump -U postgres terminal_server > /opt/backups/terminal-server/backup-$(date +%Y%m%d-%H%M%S).sql

# Automated backup (cron)
sudo crontab -e
```

Add:
```bash
# Daily database backup at 2 AM
0 2 * * * cd /opt/terminal-server && docker-compose exec -T postgres pg_dump -U postgres terminal_server > /opt/backups/terminal-server/backup-$(date +\%Y\%m\%d).sql

# Weekly cleanup (keep last 30 days)
0 3 * * 0 find /opt/backups/terminal-server -name "backup-*.sql" -mtime +30 -delete
```

## Troubleshooting

### Issue: SSL certificate not working

```bash
# Check certificate
sudo certbot certificates

# Renew manually
sudo certbot renew --force-renewal

# Reload nginx
sudo systemctl reload nginx
```

### Issue: Services not starting

```bash
# Check Docker
sudo systemctl status docker

# Check logs
docker-compose logs

# Restart services
docker-compose down
docker-compose up -d
```

### Issue: 502 Bad Gateway

```bash
# Check if backend services are running
curl http://localhost:8000/health
curl http://localhost:8001/health

# Check nginx error logs
sudo tail -f /var/log/nginx/terminal.newsml.io.error.log

# Verify proxy_pass addresses in nginx config
```

### Issue: CORS errors

- Verify API_BASE in `src/static/index.html` uses HTTPS
- Check nginx CORS headers configuration
- Check browser console for specific error

## Maintenance Tasks

### Weekly Tasks

- Review logs for errors
- Check disk space: `df -h`
- Check running containers: `docker ps`
- Review terminal cleanup (expired terminals)

### Monthly Tasks

- Review and rotate logs
- Check SSL certificate expiry: `sudo certbot certificates`
- Update system packages
- Review security updates

### Quarterly Tasks

- Database optimization
- Audit user access and permissions
- Performance testing

## Quick Reference

### Common Commands

```bash
# Restart all services
cd /opt/terminal-server && docker-compose restart

# View logs
docker-compose logs -f api-server
docker-compose logs -f web-server

# Check nginx status
sudo systemctl status nginx
sudo nginx -t

# Reload nginx config
sudo systemctl reload nginx

# Renew SSL certificate
sudo certbot renew

# Database backup
docker-compose exec postgres pg_dump -U postgres terminal_server > backup.sql

# Database restore
docker-compose exec -T postgres psql -U postgres terminal_server < backup.sql
```

### URLs

- **Web UI:** https://terminal.newsml.io
- **API Docs:** https://terminal.newsml.io/docs
- **Health Check:** https://terminal.newsml.io/health
- **API Base:** https://terminal.newsml.io/api/v1

## Support

For issues during deployment, check:
1. Nginx error logs: `/var/log/nginx/terminal.newsml.io.error.log`
2. Application logs: `docker-compose logs`
3. System logs: `journalctl -xe`

For application issues, refer to the main README.md troubleshooting section.
