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

# 4. Wait for Health
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"

# Wait for API
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "  API Server: ${GREEN}ready ✓${NC}"
        break
    fi
    [ $i -eq 30 ] && echo -e "  API Server: ${RED}failed ✗${NC}" && exit 1
    sleep 1
done

# Wait for Web
for i in {1..10}; do
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo -e "  Web Server: ${GREEN}ready ✓${NC}"
        break
    fi
    [ $i -eq 10 ] && echo -e "  Web Server: ${RED}failed ✗${NC}" && exit 1
    sleep 1
done

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}         SERVICES ARE RUNNING            ${NC}"
echo -e "${GREEN}=========================================${NC}"
echo -e "  Web UI:    ${BLUE}http://localhost:8001${NC}"
echo -e "  API:       ${BLUE}http://localhost:8000${NC}"
echo -e "  API Docs:  ${BLUE}http://localhost:8000/docs${NC}"
echo -e "========================================="
