#!/bin/bash
# Simple benchmark script to measure terminal startup time

API_URL="http://localhost:8000/api/v1"

echo "========================================"
echo "Terminal Startup Benchmark"
echo "========================================"
echo ""

# Start timing
START_TIME=$(date +%s%N)

# Create terminal
echo "[$(date +%T)] Creating terminal..."
RESPONSE=$(curl -s -X POST "$API_URL/terminals" -H "Content-Type: application/json" -d '{}')
TERMINAL_ID=$(echo $RESPONSE | grep -o '"id":"[^"]*' | cut -d'"' -f4)

if [ -z "$TERMINAL_ID" ]; then
    echo "ERROR: Failed to create terminal"
    echo "Response: $RESPONSE"
    exit 1
fi

echo "[$(date +%T)] Terminal created: $TERMINAL_ID"
CREATE_TIME=$(date +%s%N)
CREATE_DURATION=$(awk "BEGIN {print ($CREATE_TIME - $START_TIME) / 1000000000}")
echo "  Time to create: ${CREATE_DURATION}s"
echo ""

# Poll for container creation
echo "[$(date +%T)] Waiting for container..."
CONTAINER_DETECTED=false
POLL_COUNT=0
MAX_POLLS=240  # 2 minutes with 0.5s intervals

while [ $POLL_COUNT -lt $MAX_POLLS ]; do
    TERMINAL_STATUS=$(curl -s "$API_URL/terminals/$TERMINAL_ID")
    CONTAINER_ID=$(echo $TERMINAL_STATUS | grep -o '"container_id":"[^"]*' | cut -d'"' -f4)
    STATUS=$(echo $TERMINAL_STATUS | grep -o '"status":"[^"]*' | cut -d'"' -f4)

    if [ ! -z "$CONTAINER_ID" ] && [ "$CONTAINER_ID" != "null" ] && [ ! $CONTAINER_DETECTED ]; then
        CONTAINER_DETECTED=true
        CONTAINER_TIME=$(date +%s%N)
        CONTAINER_DURATION=$(awk "BEGIN {print ($CONTAINER_TIME - $START_TIME) / 1000000000}")
        echo "[$(date +%T)] Container detected: ${CONTAINER_ID:0:12}"
        echo "  Time to container: ${CONTAINER_DURATION}s"
        echo "  Status: $STATUS"
        echo ""
    fi

    # Check if we have tunnel URL
    TUNNEL_URL=$(echo $TERMINAL_STATUS | grep -o '"tunnel_url":"[^"]*' | cut -d'"' -f4)
    if [ ! -z "$TUNNEL_URL" ] && [ "$TUNNEL_URL" != "null" ]; then
        READY_TIME=$(date +%s%N)
        READY_DURATION=$(awk "BEGIN {print ($READY_TIME - $START_TIME) / 1000000000}")
        
        # If we missed the container detection (fast startup), calculate it now
        if [ -z "$CONTAINER_DURATION" ]; then
            CONTAINER_DURATION=$READY_DURATION
        fi
        
        TUNNEL_TIME=$(awk "BEGIN {print ($READY_DURATION - $CONTAINER_DURATION)}")
        echo "[$(date +%T)] Tunnel URL ready!"
        echo "  URL: $TUNNEL_URL"
        echo "  Status: $STATUS"
        echo ""
        echo "========================================"
        echo "BENCHMARK RESULTS"
        echo "========================================"
        echo "API Create Time:      ${CREATE_DURATION}s"
        echo "Container Ready:      ${CONTAINER_DURATION}s"
        echo "Total Startup Time:   ${READY_DURATION}s"
        echo "Tunnel Acquisition:   ${TUNNEL_TIME}s"
        echo "========================================"

        # Cleanup
        echo ""
        echo "Cleaning up terminal $TERMINAL_ID..."
        curl -s -X DELETE "$API_URL/terminals/$TERMINAL_ID" > /dev/null
        exit 0
    fi

    POLL_COUNT=$((POLL_COUNT + 1))
    sleep 0.5
done

echo "TIMEOUT: Terminal did not become ready within 2 minutes"
echo "Final status: $STATUS"

# Cleanup
curl -s -X DELETE "$API_URL/terminals/$TERMINAL_ID" > /dev/null
exit 1
