#!/bin/bash
set -e

echo "===== Terminal Container Starting ====="
echo "Terminal ID: ${TERMINAL_ID}"
echo "API Callback URL: ${API_CALLBACK_URL}"
echo "Localtunnel Host: ${LOCALTUNNEL_HOST}"

# Function to report errors back to API
report_error() {
    local error_message="$1"
    echo "ERROR: $error_message"

    if [ -n "$API_CALLBACK_URL" ] && [ -n "$TERMINAL_ID" ]; then
        curl -X POST "${API_CALLBACK_URL}/status" \
            -H "Content-Type: application/json" \
            -d "{\"terminal_id\": \"${TERMINAL_ID}\", \"status\": \"failed\", \"error_message\": \"${error_message}\"}" \
            || echo "Failed to report error to API"
    fi
    exit 1
}

echo "Starting Terminado server..."
python /app/terminado_server.py &
TERMINADO_PID=$!

# Wait for Terminado to be ready
echo "Waiting for Terminado to start..."
for i in {1..30}; do
    if curl -s http://localhost:8888 > /dev/null; then
        echo "Terminado is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        report_error "Terminado failed to start within 30 seconds"
    fi
    sleep 1
done

# Start localtunnel
echo "Starting localtunnel..."
if [ -n "$LOCALTUNNEL_HOST" ] && [ "$LOCALTUNNEL_HOST" != "https://localtunnel.me" ]; then
    # Use custom localtunnel server
    lt --port 8888 --host "$LOCALTUNNEL_HOST" > /tmp/tunnel_output.txt 2>&1 &
else
    # Use public localtunnel
    lt --port 8888 > /tmp/tunnel_output.txt 2>&1 &
fi
LT_PID=$!

# Wait for tunnel URL
echo "Waiting for tunnel URL..."
TUNNEL_URL=""
for i in {1..60}; do
    if [ -f /tmp/tunnel_output.txt ]; then
        TUNNEL_URL=$(grep -oP 'https://[a-zA-Z0-9-]+\.loca\.lt' /tmp/tunnel_output.txt | head -1)
        if [ -z "$TUNNEL_URL" ]; then
            TUNNEL_URL=$(grep -oP 'your url is: \Khttps://.*' /tmp/tunnel_output.txt | head -1)
        fi

        if [ -n "$TUNNEL_URL" ]; then
            echo "Tunnel URL obtained: $TUNNEL_URL"
            break
        fi
    fi

    if [ $i -eq 60 ]; then
        cat /tmp/tunnel_output.txt
        report_error "Failed to obtain tunnel URL within 60 seconds"
    fi
    sleep 1
done

# Update container's own status endpoint with tunnel URL
echo "Updating container status with tunnel URL..."
curl -X POST "http://localhost:8888/status" \
    -H "Content-Type: application/json" \
    -d "{\"tunnel_url\": \"${TUNNEL_URL}\"}" \
    || echo "Warning: Failed to update container status"

# Also report to API callback if configured (for backwards compatibility)
if [ -n "$API_CALLBACK_URL" ] && [ -n "$TERMINAL_ID" ]; then
    echo "Reporting tunnel URL to API..."
    curl -X POST "${API_CALLBACK_URL}/tunnel" \
        -H "Content-Type: application/json" \
        -d "{\"terminal_id\": \"${TERMINAL_ID}\", \"tunnel_url\": \"${TUNNEL_URL}\"}" \
        || echo "Warning: Failed to report tunnel URL to API"
fi

echo "===== Terminal Container Ready ====="
echo "Tunnel URL: $TUNNEL_URL"
echo "Terminal ID: $TERMINAL_ID"
echo "Health endpoint: http://localhost:8888/health"
echo "Status endpoint: http://localhost:8888/status"

# Health check loop (optional - keeps container running and reports health)
while true; do
    sleep 60

    # Check if Terminado is still running
    if ! kill -0 $TERMINADO_PID 2>/dev/null; then
        report_error "Terminado process died unexpectedly"
    fi

    # Check if localtunnel is still running
    if ! kill -0 $LT_PID 2>/dev/null; then
        echo "Warning: Localtunnel process died, restarting..."
        lt --port 8888 > /tmp/tunnel_output.txt 2>&1 &
        LT_PID=$!
    fi
done