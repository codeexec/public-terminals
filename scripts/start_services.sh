#!/bin/bash
# Script to start all Terminal Server services safely

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Parse command line arguments
MODE="start"
SKIP_CHECKS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --restart)
            MODE="restart"
            shift
            ;;
        --rebuild)
            MODE="rebuild"
            shift
            ;;
        --skip-checks)
            SKIP_CHECKS=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Start and manage Terminal Server services"
            echo ""
            echo "Options:"
            echo "  (no options)   Start services (checks prerequisites on first run)"
            echo "  --restart      Restart existing containers"
            echo "  --rebuild      Rebuild images and recreate containers"
            echo "  --skip-checks  Skip prerequisite checks (faster restarts)"
            echo "  --help, -h     Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                  # Start services (first time setup)"
            echo "  $0 --restart        # Quick restart after code changes"
            echo "  $0 --rebuild        # Full rebuild after dependency changes"
            echo "  $0 --skip-checks    # Start without prerequisite checks"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

if [ "$MODE" == "restart" ]; then
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}   Restarting Terminal Server Services   ${NC}"
    echo -e "${BLUE}=========================================${NC}"
elif [ "$MODE" == "rebuild" ]; then
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}   Rebuilding Terminal Server Services   ${NC}"
    echo -e "${BLUE}=========================================${NC}"
else
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}   Starting Terminal Server Services     ${NC}"
    echo -e "${BLUE}=========================================${NC}"
fi

# 0. Check prerequisites (skip for restart mode or if --skip-checks)
if [ "$MODE" != "restart" ] && [ "$SKIP_CHECKS" != "true" ]; then
    echo -e "${YELLOW}Checking prerequisites...${NC}"

    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}✗ Docker is not installed. Please install Docker first.${NC}"
        echo "  Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi
    echo -e "${GREEN}✓ Docker is installed${NC}"

    # Check Docker Compose
    if ! docker compose version &> /dev/null; then
        echo -e "${RED}✗ Docker Compose is not installed.${NC}"
        echo "  Docker Compose should be included with Docker Desktop."
        exit 1
    fi
    echo -e "${GREEN}✓ Docker Compose is installed${NC}"

    # Check if Docker is running
    if ! docker info &> /dev/null 2>&1; then
        echo -e "${RED}✗ Docker is not running. Please start Docker.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Docker is running${NC}"

    echo ""
fi

# 1. Check for .env file
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env from .env.example...${NC}"
    cp .env.example .env
fi

# 2. Check/Generate JWT Secret Key
if ! grep -q "^JWT_SECRET_KEY=.\+" .env 2>/dev/null; then
    echo -e "${YELLOW}Generating JWT secret key for admin authentication...${NC}"
    JWT_SECRET=$(openssl rand -hex 32)
    if grep -q "^JWT_SECRET_KEY=" .env; then
        # Replace existing empty value
        sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${JWT_SECRET}|" .env
    else
        # Add if not present
        echo "JWT_SECRET_KEY=${JWT_SECRET}" >> .env
    fi
    echo -e "${GREEN}✓ JWT secret key generated${NC}"
fi

# 3. Build Terminal Container if needed
if [ "$MODE" == "rebuild" ]; then
    echo -e "${YELLOW}Rebuilding terminal-server image...${NC}"
    cd terminal-container && sudo docker build -t terminal-server:latest . && cd ..
    echo -e "${GREEN}✓ terminal-server image rebuilt${NC}"
elif [ "$MODE" == "start" ]; then
    echo -e "${YELLOW}Ensuring terminal-server image exists...${NC}"
    if [[ "$(sudo docker images -q terminal-server:latest 2> /dev/null)" == "" ]]; then
        echo -e "${YELLOW}Building terminal-server image (this may take a minute)...${NC}"
        cd terminal-container && sudo docker build -t terminal-server:latest . && cd ..
    else
        echo -e "${GREEN}✓ terminal-server image found${NC}"
    fi
fi

# 4. Start/Restart/Rebuild Core Services
if [ "$MODE" == "restart" ]; then
    echo -e "${YELLOW}Restarting services via Docker Compose...${NC}"
    sudo docker compose restart > /dev/null 2>&1
    echo ""
elif [ "$MODE" == "rebuild" ]; then
    echo -e "${YELLOW}Stopping existing services...${NC}"
    sudo docker compose down > /dev/null 2>&1
    echo -e "${YELLOW}Rebuilding and recreating services...${NC}"
    sudo docker compose build --no-cache > /dev/null 2>&1
    sudo docker compose up -d > /dev/null 2>&1
    echo ""
else
    echo -e "${YELLOW}Starting services via Docker Compose...${NC}"
    sudo docker compose up -d > /dev/null 2>&1
    echo ""
fi

# 5. Wait and Verify Health (with potential restart for transient DNS issues)
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
echo ""

# Helper to check Docker container health
check_container_health() {
    local name=$1
    local label=$2

    echo -n "  ${label}: "
    for i in {1..30}; do
        local health=$(sudo docker inspect --format='{{.State.Health.Status}}' "${name}" 2>/dev/null || echo "none")
        if [ "$health" == "healthy" ]; then
            echo -e "${GREEN}ready ✓${NC}"
            return 0
        elif [ "$health" == "none" ]; then
            # Container doesn't have healthcheck, check if it's running
            local status=$(sudo docker inspect --format='{{.State.Status}}' "${name}" 2>/dev/null || echo "stopped")
            if [ "$status" == "running" ]; then
                echo -e "${GREEN}running ✓${NC}"
                return 0
            fi
        fi
        sleep 1
    done

    echo -e "${RED}failed ✗${NC}"
    return 1
}

# Helper to check HTTP endpoint
check_http_endpoint() {
    local name=$1
    local port=$2
    local label=$3

    echo -n "  ${label}: "
    for i in {1..30}; do
        if curl -s "http://localhost:${port}/health" > /dev/null 2>&1; then
            echo -e "${GREEN}ready ✓${NC}"
            return 0
        fi

        # After 10 attempts, if it's still failing, try restarting it
        # (fixes transient DNS resolution issues in some Docker environments)
        if [ $i -eq 10 ]; then
            echo -e "${YELLOW}restarting...${NC}"
            echo -n "  ${label}: "
            sudo docker restart "${name}" > /dev/null 2>&1
        fi

        sleep 1
    done

    echo -e "${RED}failed ✗${NC}"
    return 1
}

# Wait for base services first
check_container_health "terminal-server-db" "PostgreSQL" || exit 1
check_container_health "terminal-server-redis" "Redis" || exit 1

# Then wait for application services
check_http_endpoint "terminal-server-api" "8000" "API Server" || exit 1
check_http_endpoint "terminal-server-web" "8001" "Web Server" || exit 1

echo ""

if [ "$MODE" == "restart" ]; then
    echo -e "${GREEN}=========================================${NC}"
    echo -e "${GREEN}       SERVICES RESTARTED SUCCESSFULLY   ${NC}"
    echo -e "${GREEN}=========================================${NC}"
elif [ "$MODE" == "rebuild" ]; then
    echo -e "${GREEN}=========================================${NC}"
    echo -e "${GREEN}       SERVICES REBUILT SUCCESSFULLY     ${NC}"
    echo -e "${GREEN}=========================================${NC}"
else
    echo -e "${GREEN}=========================================${NC}"
    echo -e "${GREEN}         SERVICES ARE RUNNING            ${NC}"
    echo -e "${GREEN}=========================================${NC}"
fi
echo -e "  Web UI:    ${BLUE}http://localhost:8001${NC}"
echo -e "  Admin UI:  ${BLUE}http://localhost:8001/admin${NC}"
echo -e "  API:       ${BLUE}http://localhost:8000${NC}"
echo -e "  API Docs:  ${BLUE}http://localhost:8000/docs${NC}"
echo -e "========================================="
echo -e "${YELLOW}Admin Credentials:${NC}"
ADMIN_USER=$(grep "^ADMIN_USERNAME=" .env 2>/dev/null | cut -d= -f2 || echo "admin")
ADMIN_PASS=$(grep "^ADMIN_PASSWORD=" .env 2>/dev/null | cut -d= -f2 || echo "(not set)")
echo -e "  Username:  ${BLUE}${ADMIN_USER}${NC}"
echo -e "  Password:  ${BLUE}${ADMIN_PASS}${NC}"
echo -e "========================================="
