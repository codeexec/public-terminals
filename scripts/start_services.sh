#!/bin/bash
# Script to start all Terminal Server services safely

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}   Starting Terminal Server Services     ${NC}"
echo -e "${BLUE}=========================================${NC}"

# 1. Check for .env file
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env from .env.example...${NC}"
    cp .env.example .env
fi

# 2. Build Terminal Container if it doesn't exist
echo -e "${YELLOW}Ensuring terminal-server image exists...${NC}"
if [[ "$(sudo docker images -q terminal-server:latest 2> /dev/null)" == "" ]]; then
    echo -e "${YELLOW}Building terminal-server image (this may take a minute)...${NC}"
    cd terminal-container && sudo docker build -t terminal-server:latest . && cd ..
else
    echo -e "${GREEN}✓ terminal-server image found${NC}"
fi

# 3. Start Core Services
echo -e "${YELLOW}Starting services via Docker Compose...${NC}"
sudo docker compose up -d

# 4. Wait and Verify Health (with potential restart for transient DNS issues)
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"

# Helper to check and restart if needed
check_service() {
    local name=$1
    local port=$2
    local label=$3
    
    for i in {1..20}; do
        if curl -s "http://localhost:${port}/health" > /dev/null 2>&1; then
            echo -e "  ${label}: ${GREEN}ready ✓${NC}"
            return 0
        fi
        
        # After 5 attempts, if it's still failing, try restarting it 
        # (fixes transient DNS resolution issues in some Docker environments)
        if [ $i -eq 5 ]; then
            echo -e "  ${YELLOW}Restarting ${name} (possible transient startup error)...${NC}"
            sudo docker restart "${name}" > /dev/null
        fi
        
        sleep 2
    done
    
    echo -e "  ${label}: ${RED}failed ✗${NC}"
    return 1
}

check_service "terminal-server-api" "8000" "API Server" || exit 1
check_service "terminal-server-web" "8001" "Web Server" || exit 1

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}         SERVICES ARE RUNNING            ${NC}"
echo -e "${GREEN}=========================================${NC}"
echo -e "  Web UI:    ${BLUE}http://localhost:8001${NC}"
echo -e "  API:       ${BLUE}http://localhost:8000${NC}"
echo -e "  API Docs:  ${BLUE}http://localhost:8000/docs${NC}"
echo -e "========================================="
