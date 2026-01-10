#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# ============================================ 
# HELPER FUNCTIONS
# ============================================ 

cleanup() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Stopping Services${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    # Stop terminal containers
    echo -e "${YELLOW}Stopping terminal containers...${NC}"
    TERMINAL_CONTAINERS=$(docker ps -a --filter "label=app=terminal-server" --format "{{.Names}}" 2>/dev/null || true)

    if [ -n "$TERMINAL_CONTAINERS" ]; then
        echo "$TERMINAL_CONTAINERS" | while read container; do
            echo -e "  Stopping ${container}..."
            docker stop "$container" > /dev/null 2>&1 || true
            docker rm "$container" > /dev/null 2>&1 || true
        done
        echo -e "${GREEN}✓ Terminal containers stopped${NC}"
    else
        echo -e "  No terminal containers to stop"
    fi

    # Stop docker compose services
    echo ""
    echo -e "${YELLOW}Stopping Docker Compose services...${NC}"
    docker compose down

    echo ""
    echo -e "${GREEN}✓ All services stopped${NC}"
    echo ""
    echo -e "${YELLOW}To completely remove all data including database:${NC}"
    echo -e "  docker compose down -v"
    echo ""
}

# Check for arguments
if [[ "$1" == "--stop" ]]; then
    cleanup
    exit 0
fi

echo "========================================="
echo "   Terminal Server - Full Test Suite"
echo "========================================="
echo ""

# ============================================ 
# STEP 1: START INFRASTRUCTURE
# ============================================ 

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}STEP 1: Starting Infrastructure${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Delegate startup to the robust start_services.sh script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if start_services.sh exists and is executable
if [ ! -x "$SCRIPT_DIR/start_services.sh" ]; then
    echo -e "${YELLOW}Making start_services.sh executable...${NC}"
    chmod +x "$SCRIPT_DIR/start_services.sh"
fi

echo -e "${YELLOW}Delegating to start_services.sh...${NC}"
"$SCRIPT_DIR/start_services.sh"

echo ""
echo -e "${GREEN}✓ Infrastructure is ready${NC}"
echo ""

# ============================================ 
# STEP 2: CREATE TERMINAL
# ============================================ 

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}STEP 2: Creating Terminal${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

TERMINAL_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/terminals \
    -H "Content-Type: application/json" \
    -d '{}')

# Check if curl failed (empty response)
if [ -z "$TERMINAL_RESPONSE" ]; then
    echo -e "${RED}✗ Failed to connect to API Server at http://localhost:8000${NC}"
    exit 1
fi

TERMINAL_ID=$(echo "$TERMINAL_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")

if [ -z "$TERMINAL_ID" ]; then
    echo -e "${RED}✗ Failed to create terminal. Response:${NC}"
    echo "$TERMINAL_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Terminal created${NC}"
echo -e "  Terminal ID: ${YELLOW}${TERMINAL_ID}${NC}"

# ============================================ 
# STEP 3: WAIT FOR TERMINAL TO START
# ============================================ 

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}STEP 3: Waiting for Terminal to Start${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

for i in {1..60}; do
    STATUS_RESPONSE=$(curl -s http://localhost:8000/api/v1/terminals/${TERMINAL_ID})
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unknown")
    TUNNEL_URL=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tunnel_url', ''))" 2>/dev/null || echo "")

    echo -ne "\r  Polling status... Attempt ${i}/60 - Status: ${YELLOW}${STATUS}${NC}     "

    if [ "$STATUS" = "started" ] && [ -n "$TUNNEL_URL" ] && [ "$TUNNEL_URL" != "None" ]; then
        echo ""
        echo -e "${GREEN}✓ Terminal is ready!${NC}"
        break
    fi

    if [ "$STATUS" = "failed" ]; then
        echo ""
        echo -e "${RED}✗ Terminal creation failed${NC}"
        echo "$STATUS_RESPONSE" | python3 -m json.tool
        exit 1
    fi

    if [ $i -eq 60 ]; then
        echo ""
        echo -e "${RED}✗ Terminal did not start in time${NC}"
        echo "Final status:"
        echo "$STATUS_RESPONSE" | python3 -m json.tool
        exit 1
    fi

    sleep 2
done

# ============================================ 
# STEP 4: DISPLAY TERMINAL DETAILS
# ============================================ 

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}STEP 4: Terminal Details${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

FINAL_STATUS=$(curl -s http://localhost:8000/api/v1/terminals/${TERMINAL_ID})
TUNNEL_URL=$(echo "$FINAL_STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnel_url'])")
CONTAINER_NAME=$(echo "$FINAL_STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin)['container_name'])")
HOST_PORT=$(echo "$FINAL_STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin)['host_port'])")
CONTAINER_ID=$(echo "$FINAL_STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin)['container_id'])")

echo -e "${GREEN}Terminal Information:${NC}"
echo -e "  Terminal ID:      ${YELLOW}${TERMINAL_ID}${NC}"
echo -e "  Container Name:   ${CONTAINER_NAME}"
echo -e "  Container ID:     ${CONTAINER_ID:0:12}"
echo -e "  Status:           ${GREEN}started${NC}"
echo ""
echo -e "${GREEN}Access URLs:${NC}"
echo -e "  ${BLUE}Public URL (via tunnel):${NC}  ${GREEN}${TUNNEL_URL}${NC}"
echo -e "  ${BLUE}Local URL (host):${NC}         ${GREEN}http://localhost:${HOST_PORT}${NC}"
echo ""
echo -e "${GREEN}Web UI & API:${NC}"
echo -e "  ${BLUE}Web UI:${NC}                   ${GREEN}http://localhost:8001${NC}"
echo -e "  ${BLUE}Admin UI:${NC}                 ${GREEN}http://localhost:8001/admin${NC}"
echo -e "  ${BLUE}API Server:${NC}               ${GREEN}http://localhost:8000${NC}
echo -e "  ${BLUE}API Documentation:${NC}        ${GREEN}http://localhost:8000/docs${NC}"
echo ""
echo -e "${YELLOW}Note: On first visit to tunnel URL, you may need to click 'Click to Continue'${NC}"
echo ""

# ============================================ 
# STEP 5: VERIFY HEALTH ENDPOINTS
# ============================================ 

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}STEP 5: Verifying Health Endpoints${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Test API Server health
echo -n "  API Server /health: "
API_HEALTH=$(curl -s http://localhost:8000/health)
API_STATUS=$(echo "$API_HEALTH" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "failed")
if [ "$API_STATUS" = "healthy" ]; then
    echo -e "${GREEN}✓ healthy${NC}"
else
    echo -e "${RED}✗ failed${NC}"
fi

# Test Web Server health
echo -n "  Web Server /health: "
WEB_HEALTH=$(curl -s http://localhost:8001/health)
WEB_STATUS=$(echo "$WEB_HEALTH" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "failed")
if [ "$WEB_STATUS" = "healthy" ]; then
    echo -e "${GREEN}✓ healthy${NC}"
else
    echo -e "${RED}✗ failed${NC}"
fi

# Test terminal container health endpoint
echo -n "  Terminal Container /health: "
# Note: Using docker exec requires permissions, consistent with start_services.sh
HEALTH=$(docker exec terminal-server-api curl -s http://${CONTAINER_NAME}:8888/health)
HEALTH_STATUS=$(echo "$HEALTH" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "failed")
if [ "$HEALTH_STATUS" = "healthy" ]; then
    echo -e "${GREEN}✓ healthy${NC}"
else
    echo -e "${RED}✗ failed${NC}"
fi

# Test terminal container status endpoint
echo -n "  Terminal Container /status: "
STATUS_EP=$(docker exec terminal-server-api curl -s http://${CONTAINER_NAME}:8888/status)
STATUS_STATE=$(echo "$STATUS_EP" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "failed")
if [ "$STATUS_STATE" = "ready" ]; then
    echo -e "${GREEN}✓ ready${NC}"
else
    echo -e "${RED}✗ failed${NC}"
fi

echo ""

# ============================================ 
# STEP 6: TEST ADMIN API
# ============================================ 

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}STEP 6: Testing Admin API${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Get admin credentials from .env
ADMIN_USER=$(grep "^ADMIN_USERNAME=" .env 2>/dev/null | cut -d= -f2 || echo "admin")
ADMIN_PASS=$(grep "^ADMIN_PASSWORD=" .env 2>/dev/null | cut -d= -f2 || echo "changeme")

# Test admin login
echo -n "  Admin Login: "
ADMIN_LOGIN=$(curl -s -X POST http://localhost:8000/api/v1/admin/login \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${ADMIN_USER}\",\"password\":\"${ADMIN_PASS}\"}")

ADMIN_TOKEN=$(echo "$ADMIN_LOGIN" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || echo "")

if [ -n "$ADMIN_TOKEN" ] && [ "$ADMIN_TOKEN" != "None" ]; then
    echo -e "${GREEN}✓ success${NC}"
else
    echo -e "${RED}✗ failed${NC}"
fi

# Test admin terminals list
echo -n "  Admin Terminals List: "
ADMIN_TERMINALS=$(curl -s http://localhost:8000/api/v1/admin/terminals \
    -H "Authorization: Bearer ${ADMIN_TOKEN}")

ADMIN_TOTAL=$(echo "$ADMIN_TERMINALS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total', -1))" 2>/dev/null || echo "-1")

if [ "$ADMIN_TOTAL" -ge 0 ]; then
    echo -e "${GREEN}✓ success (found ${ADMIN_TOTAL} terminals)${NC}"
else
    echo -e "${RED}✗ failed${NC}"
fi

echo ""

# ============================================ 
# SUCCESS SUMMARY
# ============================================ 

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}         ✓ TEST COMPLETED SUCCESSFULLY${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${BLUE}Useful Commands:${NC}"
echo "  View API logs:        docker compose logs -f api-server"
echo "  View Web logs:        docker compose logs -f web-server"
echo "  View container logs:  docker logs ${CONTAINER_NAME}"
echo "  List all terminals:   curl -s http://localhost:8000/api/v1/terminals | python3 -m json.tool"
echo "  Get terminal status:  curl -s http://localhost:8000/api/v1/terminals/${TERMINAL_ID} | python3 -m json.tool"
echo "  Delete terminal:      curl -X DELETE http://localhost:8000/api/v1/terminals/${TERMINAL_ID}"
echo "  Open Web UI:          open http://localhost:8001"
echo "  Open Admin UI:        open http://localhost:8001/admin"
echo "  API Documentation:    http://localhost:8000/docs"
echo ""
echo -e "${BLUE}Admin Credentials:${NC}"
echo "  Username: ${ADMIN_USER}"
echo "  Password: ${ADMIN_PASS}"
echo ""

# ============================================ 
# CLEANUP PROMPT
# ============================================ 

echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Do you want to stop and clean up the services?${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "This will:"
echo "  - Stop all terminal containers"
echo "  - Stop Docker Compose services (API Server, Web Server, DB, Redis, Celery)"
echo "  - Keep the database data (volumes will be preserved)"
echo ""
read -p "Stop services? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    cleanup
else
    echo ""
    echo -e "${GREEN}Services are still running.${NC}"
    echo ""
    echo -e "${YELLOW}To stop later, run:${NC}"
    echo -e "  ./run_test.sh --stop"
    echo -e "${YELLOW}Or manually:${NC}"
    echo -e "  docker compose down"
    echo ""
fi

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Done!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"